"""Isolated source-fixture backend for the existing frontend refresh smoke test.

Run from backend/macro; all CSVs are written under ignored logs/, and this
process neither starts scheduled jobs nor contacts external data sources.
"""

import asyncio
import importlib.util
from pathlib import Path

import pytest
import uvicorn

from src.api import routes
from src.services.update_pipeline import UpdatePipeline
from src.services.update_registry import UPDATE_SPECS


if __name__ == "__main__":
    spec = importlib.util.spec_from_file_location(
        "update_acceptance", "tests/test_update_integration.py",
    )
    acceptance = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(acceptance)
    acceptance.SOURCE_DATE = acceptance.pd.Timestamp.now().normalize() - acceptance.pd.Timedelta(days=10)
    root = Path("logs/pipeline-preview-stale").resolve()
    root.mkdir(parents=True, exist_ok=True)
    patch = pytest.MonkeyPatch()
    fixture = acceptance.update_environment.__wrapped__(root, patch)
    environment = next(fixture)

    async def seed():
        for update_spec in UPDATE_SPECS.values():
            response = await UpdatePipeline.execute(update_spec, routes._update_context())
            assert response.success, response.message

    asyncio.run(seed())
    try:
        uvicorn.run(environment.app, host="127.0.0.1", port=18094, log_level="warning")
    finally:
        fixture.close()
        patch.undo()
