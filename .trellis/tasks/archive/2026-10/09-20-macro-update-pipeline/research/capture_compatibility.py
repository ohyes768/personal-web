"""Capture original HTTP contracts and compare real CSV writes after extraction.

Run from backend/macro. This audit uses committed pre-migration code, never
the new implementation, to build the checked-in compatibility fixture.
"""
import ast
import faulthandler
import importlib.util
import json
import subprocess
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api import routes
from src.models import UpdateResponse
from src.services.update_pipeline import NoNewData, UpdateStages
from src.services.update_registry import UPDATE_SPECS


def test_capture_compatibility():
    BASELINE = "23ffeba"
    faulthandler.dump_traceback_later(30, repeat=False)
    spec = importlib.util.spec_from_file_location("update_acceptance", "tests/test_update_integration.py")
    acceptance = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(acceptance)


    def original_file(path):
        return subprocess.check_output(["git", "show", f"{BASELINE}:{path}"], encoding="utf-8", timeout=20)


    original_routes = ast.parse(original_file("backend/macro/src/api/routes.py"))
    original_registry = ast.parse(original_file("backend/macro/src/services/update_registry.py"))
    market_factory = next(node for node in original_registry.body if isinstance(node, ast.FunctionDef) and node.name == "_market_stages")
    snapshots = {}
    temporary_root = Path(".pytest-tmp").resolve()
    temporary_root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=temporary_root, prefix="compatibility-") as temporary:
        assert Path(temporary).resolve().is_relative_to(temporary_root)
        for key, update_spec in UPDATE_SPECS.items():
            environments = []
            responses = []
            for mode in ("original", "migrated"):
                patch = pytest.MonkeyPatch()
                task_root = Path(temporary) / key / mode
                task_root.mkdir(parents=True)
                fixture = acceptance.update_environment.__wrapped__(task_root, patch)
                environment = next(fixture)
                if mode == "original":
                    namespace = dict(vars(routes))
                    model_import = next(node for node in original_routes.body if isinstance(node, ast.ImportFrom) and node.module == "src.models")
                    exec(compile(ast.Module(body=[model_import], type_ignores=[]), "original_models", "exec"), namespace)
                    namespace["_NoNewData"] = NoNewData
                    namespace["UpdateStages"] = UpdateStages
                    exec(compile(ast.Module(body=[market_factory], type_ignores=[]), "original_market", "exec"), namespace)
                    namespace["UPDATE_SPECS"] = {
                        "volume": SimpleNamespace(build_stages=namespace["_market_stages"]("volume", "total_amount_yi", "volume", namespace["VolumeData"], namespace["VolumeUpdateData"])),
                        "turnover": SimpleNamespace(build_stages=namespace["_market_stages"]("turnover", "turnover_rate", "turnover", namespace["TurnoverData"], namespace["TurnoverUpdateData"])),
                        "margin": SimpleNamespace(build_stages=namespace["_market_stages"]("margin", "rzye", "margin", namespace["MarginData"], namespace["MarginUpdateData"])),
                    }
                    function = next(
                        node for node in original_routes.body if isinstance(node, ast.AsyncFunctionDef)
                        and any(isinstance(d, ast.Call) and d.args and isinstance(d.args[0], ast.Constant)
                                and d.args[0].value == update_spec.endpoint for d in node.decorator_list)
                    )
                    function.decorator_list = []
                    exec(compile(ast.Module(body=[function], type_ignores=[]), "original_routes", "exec"), namespace)
                    app = FastAPI()
                    app.add_api_route("/api" + update_spec.endpoint, namespace[function.name], methods=["POST"], response_model=UpdateResponse)
                else:
                    app = environment.app
                response = TestClient(app).post("/api" + update_spec.endpoint)
                assert response.status_code == 200 and response.json()["success"], response.json()
                responses.append(acceptance.normalize_response(response.json()))
                environments.append(environment)
                try:
                    next(fixture)
                except StopIteration:
                    pass
                patch.undo()
            assert responses[0] == responses[1], key
            for file_key in acceptance.EXPECTED_FILES[key]:
                frames = [pd.read_csv(env.store.files[file_key], index_col=0) for env in environments]
                pd.testing.assert_frame_equal(*frames)
            snapshots[key] = responses[0]
            print(f"{key}: original/migrated HTTP response and CSV match")
    destination = Path("tests/fixtures/update_success_responses.json")
    destination.parent.mkdir(exist_ok=True)
    destination.write_text(json.dumps(snapshots, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Captured {len(snapshots)} original response contracts from {BASELINE}.")
    faulthandler.cancel_dump_traceback_later()
