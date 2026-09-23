import os
from pathlib import Path

from fastapi.testclient import TestClient


def test_health_endpoint(tmp_path: Path, monkeypatch):
    db = tmp_path / "test.db"
    monkeypatch.setenv("DRUG_EVIDENCE_DB", str(db))
    # Import after setting the env var because DB_PATH is created at import time.
    import importlib
    import app.main as main

    importlib.reload(main)
    client = TestClient(main.app)
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["version"] == "2.3.0"
