from pathlib import Path

from app.uploading import has_pdf_signature, safe_name


def test_safe_name_removes_path_components():
    assert safe_name("../../unsafe name.pdf") == "unsafe name.pdf"


def test_pdf_signature(tmp_path: Path):
    good = tmp_path / "good.pdf"
    good.write_bytes(b"%PDF-1.7\nrest")
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"not a pdf")
    assert has_pdf_signature(good)
    assert not has_pdf_signature(bad)
