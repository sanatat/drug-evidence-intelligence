from app.db import connect


def test_schema_creation(tmp_path):
    con = connect(str(tmp_path / "evidence.db"))
    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    con.close()
    assert "drugs" in tables
    assert "documents" in tables
    assert "quality_parameters" in tables
    assert "clinical_endpoints" in tables
    assert "upload_events" in tables
