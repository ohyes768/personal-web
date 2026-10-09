"""Bidirectional model/route registry and collected HTTP contract coverage.

Collection is performed in a subprocess so focused registry runs still inspect
the real parametrized cases without rerunning source calls or polluting pytest.
"""

import json
import subprocess
import sys
from pathlib import Path
from typing import get_args, get_type_hints

import pytest

from src.models import (
    MacroData,
    MacroDataWithRatesAndVIX,
    MarginHistoryUpdateData,
    UpdateResponse,
    VolumeTurnoverHistoryUpdateData,
)
from src.services.update_registry import UPDATE_SPECS

# UpdateResponse also serves historical fetches. Preserve these explicit
# compatibility schemas rather than silently shrinking its public OpenAPI union.
NON_INCREMENTAL_PAYLOADS = {
    VolumeTurnoverHistoryUpdateData: "/fetch/volume-turnover/history",
    MarginHistoryUpdateData: "/fetch/margin/history",
    MacroData: "retained legacy schema; no active incremental producer",
    MacroDataWithRatesAndVIX: "retained legacy schema; no active incremental producer",
}


def response_payload_types():
    return set(get_args(get_type_hints(UpdateResponse)["data"])) - {type(None)}


def assert_payload_coverage(specs, response_types):
    registered = {spec.payload_type for spec in specs.values()}
    assert registered <= response_types, (
        "registered payload missing from response union"
    )
    assert response_types == registered | NON_INCREMENTAL_PAYLOADS.keys(), (
        "response union contains an unregistered incremental payload"
    )


def assert_contract_coverage(specs, items):
    coverage = set()
    for item in items:
        for key, outcome in item["contracts"]:
            assert key in specs, f"contract names an unregistered source: {key}"
            assert outcome in {"success", "failure"}
            assert item["file"] == specs[key].contract_test_file
            coverage.add((key, outcome))
    required = {(key, outcome) for key in specs for outcome in ("success", "failure")}
    assert required <= coverage, (
        f"missing collected HTTP contracts: {sorted(required - coverage)}"
    )


@pytest.fixture(scope="module")
def collected_contracts(tmp_path_factory):
    destination = tmp_path_factory.mktemp("contracts") / "collected.json"
    test_files = sorted({spec.contract_test_file for spec in UPDATE_SPECS.values()})
    script = """
import json, sys
from pathlib import Path
import pytest
class Collector:
    def pytest_collection_finish(self, session):
        items = [
            {"file": item.path.name, "nodeid": item.nodeid,
             "contracts": [list(mark.args) for mark in item.iter_markers("update_contract")]}
            for item in session.items
        ]
        Path(sys.argv[1]).write_text(json.dumps(items), encoding="utf-8")
raise SystemExit(pytest.main(["--collect-only", "-q", *sys.argv[2:]], plugins=[Collector()]))
"""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            script,
            str(destination),
            *["tests/" + name for name in test_files],
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(destination.read_text(encoding="utf-8"))


def test_response_union_and_registry_cover_each_other():
    assert_payload_coverage(UPDATE_SPECS, response_payload_types())


def test_every_source_has_collected_success_and_failure_http_contracts(
    collected_contracts,
):
    assert_contract_coverage(UPDATE_SPECS, collected_contracts)


@pytest.mark.parametrize("key", list(UPDATE_SPECS))
def test_missing_union_member_is_rejected(key):
    with pytest.raises(AssertionError, match="missing from response union"):
        assert_payload_coverage(
            UPDATE_SPECS,
            response_payload_types() - {UPDATE_SPECS[key].payload_type},
        )


@pytest.mark.parametrize("key", list(UPDATE_SPECS))
def test_deleted_registration_is_rejected(key):
    reduced = {k: spec for k, spec in UPDATE_SPECS.items() if k != key}
    with pytest.raises(AssertionError, match="unregistered incremental payload"):
        assert_payload_coverage(reduced, response_payload_types())


@pytest.mark.parametrize("key", list(UPDATE_SPECS))
@pytest.mark.parametrize("outcome", ["success", "failure"])
def test_deleted_contract_case_is_rejected_even_when_file_remains(
    collected_contracts,
    key,
    outcome,
):
    # First ensure the original collection is complete; otherwise the mutation
    # could pass simply because an unrelated source was already missing.
    assert_contract_coverage(UPDATE_SPECS, collected_contracts)
    reduced = [
        item for item in collected_contracts if [key, outcome] not in item["contracts"]
    ]
    with pytest.raises(AssertionError, match="missing collected HTTP contracts"):
        assert_contract_coverage(UPDATE_SPECS, reduced)
