from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import hashlib, re
import fitz

@dataclass
class PDFPage:
    number: int
    text: str

@dataclass
class PDFDocument:
    path: Path
    pages: list[PDFPage]

    @property
    def text(self) -> str:
        return "\n\n".join(p.text for p in self.pages)

    @property
    def page_count(self) -> int:
        return len(self.pages)


def load_pdf(path: Path) -> PDFDocument:
    doc = fitz.open(path)
    pages = [PDFPage(i + 1, page.get_text("text")) for i, page in enumerate(doc)]
    return PDFDocument(path=path, pages=pages)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def clean(text: str | None, limit: int = 2000) -> str | None:
    if not text:
        return None
    out = re.sub(r"\s+", " ", text).strip()
    return out[:limit]


def find_page_for_text(pages: list[PDFPage], needle: str | None) -> int | None:
    if not needle:
        return None
    n = re.sub(r"\s+", " ", needle).strip().lower()[:120]
    if not n:
        return None
    for page in pages:
        t = re.sub(r"\s+", " ", page.text).lower()
        if n in t:
            return page.number
    # weaker anchor for long snippets
    tokens = [x for x in re.findall(r"[a-z0-9]+", n) if len(x) > 3][:8]
    if len(tokens) >= 3:
        best = None
        for page in pages:
            low = page.text.lower()
            score = sum(tok in low for tok in tokens)
            if best is None or score > best[0]:
                best = (score, page.number)
        if best and best[0] >= max(3, len(tokens)//2):
            return best[1]
    return None
