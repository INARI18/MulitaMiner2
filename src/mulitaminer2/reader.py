"""PDF text extraction with competing backends.

The scanner marker patterns are inherent to each scanner's report format and
survive any reasonable extractor; only layout-sensitive details differ between
backends. Both backends share the same text-cleanup pipeline, ported from
MulitaMiner v1 `readers/pdf_extraction.py` (footer removal, mojibake/CID glyph
restoration, soft-hyphen rejoining, page-continuation marker removal, NFKC).

v1's heuristic sentence-continuation merge (its "strategy 2") was intentionally
NOT ported: blocks span whole marker-to-marker ranges, so page boundaries fall
inside a block and the LLM reads across them. The v1/v2 parity run guards this
decision — if quality drops, revisit.

Everything stays in memory; no visual-layout cache files.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

log = logging.getLogger(__name__)

# CID glyphs pdfplumber leaves unresolved in OpenVAS reports (v1 _CID_MAP).
_CID_MAP = {16: '"', 17: '"', 27: "ff", 28: "fi", 29: "fl", 30: "ffi", 31: "ffl"}
# pypdfium2 emits the SAME broken glyphs as raw control characters instead of
# "(cid:N)" markers (bBWA lesson: "a\x1bected" = "affected"). Same map, then
# any leftover C0 control char (except \t \n) is stripped — a control char
# reaching an LLM response makes the JSON invalid by definition.
_CTRL_LIGATURES = str.maketrans({chr(cid): glyph for cid, glyph in _CID_MAP.items()})
_CTRL_STRIP_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")

# Report footers and page-continuation scaffolding (v1 lessons).
_FOOTER_RE = re.compile(r"Page \d+ of \d+")
_TENABLE_EXPORT_FOOTER_RE = re.compile(r"Web Application Scanning Detailed Scan Export:[^\n]*")
_CONTINUATION_RE = re.compile(
    r"^.*(?:\.\s?\.\s?\.\s?)?continue[sd] (?:on next|from previous) page.*$", re.IGNORECASE
)


@dataclass(frozen=True)
class ExtractedDoc:
    """Full cleaned report text, in memory."""

    text: str
    page_count: int
    backend: str


class PdfBackend(Protocol):
    name: str

    def extract_pages(self, path: Path) -> list[str]:
        """Raw text of each page, layout preserved as well as the lib allows."""
        ...


class PdfplumberBackend:
    """v1's reference backend — the layout regexes were calibrated on its output."""

    name = "pdfplumber"

    def extract_pages(self, path: Path) -> list[str]:
        import pdfplumber

        pages: list[str] = []
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                # Same knobs as v1: tight tolerances + blank chars keep the
                # tabular scanner layouts intact enough for the header regexes.
                text = page.extract_text(
                    layout=True, x_tolerance=1, y_tolerance=1, keep_blank_chars=True
                )
                pages.append(text or "")
        return pages


class Pdfium2Backend:
    """New candidate: pypdfium2 (PDFium). Fast, permissively licensed."""

    name = "pypdfium2"

    def extract_pages(self, path: Path) -> list[str]:
        import pypdfium2 as pdfium

        pages: list[str] = []
        doc = pdfium.PdfDocument(path)
        try:
            for page in doc:
                textpage = page.get_textpage()
                try:
                    pages.append(textpage.get_text_range() or "")
                finally:
                    textpage.close()
                page.close()
        finally:
            doc.close()
        return pages


BACKENDS: dict[str, PdfBackend] = {
    PdfplumberBackend.name: PdfplumberBackend(),
    Pdfium2Backend.name: Pdfium2Backend(),
}

# pypdfium2 won the bake-off (tools/compare_backends.py, 2026-07-20): marker
# counts identical to pdfplumber on all 5 baseline PDFs, 10-40x faster.
DEFAULT_BACKEND = "pypdfium2"


def _clean_page(text: str) -> str:
    lines = []
    for line in text.split("\n"):
        if _FOOTER_RE.search(line):
            continue
        if _CONTINUATION_RE.match(line.strip()):
            continue
        lines.append(line.replace("\t", "    "))
    cleaned = "\n".join(lines)
    # Windows-1252 mojibake seen in v1 reports.
    cleaned = (
        cleaned.replace("ÔåÆ", "->")
        .replace("ÔÇÖ", "'")
        .replace("ÔÇ£", '"')
        .replace("ÔÇØ", '"')
    )
    cleaned = re.sub(r"[ ]{2,}", " ", cleaned)
    return cleaned.rstrip() + "\n"


def _restore_cid_glyphs(text: str) -> str:
    # Wrap continuation: "word-part\n   (cid:44)→rest" is the same word split.
    text = re.sub(r"\n[ \t]*\(cid:44\)→", "", text)
    for cid, glyph in _CID_MAP.items():
        text = text.replace(f"(cid:{cid})", glyph)
    text = re.sub(r"\(cid:\d+\)", "", text)  # unknown CIDs: drop (v1 behavior)
    # De-hyphenate soft-wrapped words: "down-\n   loaded" -> "downloaded".
    text = re.sub(r"(\w)-\n[ \t]*(\w)", r"\1\2", text)
    return text


def extract_pdf(path: Path, backend: str = DEFAULT_BACKEND) -> ExtractedDoc:
    """Extract and clean the full report text using the chosen backend."""
    try:
        impl = BACKENDS[backend]
    except KeyError:
        raise ValueError(f"Unknown PDF backend '{backend}'. Available: {sorted(BACKENDS)}")
    raw_pages = impl.extract_pages(path)
    log.info("Extracted %d pages from %s with %s", len(raw_pages), path.name, backend)
    text = "".join(_clean_page(p) for p in raw_pages)
    text = _CTRL_STRIP_RE.sub("", text.translate(_CTRL_LIGATURES).replace("\r", ""))
    text = unicodedata.normalize("NFKC", text)
    text = _restore_cid_glyphs(text)
    text = _TENABLE_EXPORT_FOOTER_RE.sub("", text)
    if not text.strip():
        raise ValueError(
            f"No text extracted from {path} — the file may be corrupted or image-only."
        )
    return ExtractedDoc(text=text, page_count=len(raw_pages), backend=backend)
