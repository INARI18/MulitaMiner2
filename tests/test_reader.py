"""Reader tests against a real baseline PDF (no network, no LLM)."""
import re
from pathlib import Path

import pytest

from mulitaminer2.reader import BACKENDS, extract_pdf

BASELINE_PDF = Path("resources/openvas/OpenVAS_JuiceShop.pdf")
OPENVAS_MARKER = re.compile(r"^\s*(?:Critical|High|Medium|Low|Log)\s+\(CVSS:", re.MULTILINE)


@pytest.mark.parametrize("backend", sorted(BACKENDS))
def test_backend_extracts_marker_lines(backend):
    doc = extract_pdf(BASELINE_PDF, backend=backend)
    assert doc.page_count > 0
    assert len(doc.text) > 1000
    assert OPENVAS_MARKER.search(doc.text), f"{backend}: no OpenVAS marker line survived extraction"


def test_cleanup_removes_footers_and_continuations():
    doc = extract_pdf(BASELINE_PDF)
    assert "continues on next page" not in doc.text.lower()
    assert not re.search(r"Page \d+ of \d+", doc.text)


def test_unknown_backend_raises():
    with pytest.raises(ValueError, match="Unknown PDF backend"):
        extract_pdf(BASELINE_PDF, backend="nope")


def test_no_control_characters_survive_extraction():
    """pypdfium2 emits broken ligatures as raw control chars
    ("a\\x1bected" = "affected"); one control char in a field makes the LLM's
    JSON invalid by definition. The reader must map them (CID table) or strip."""
    import re as _re

    doc = extract_pdf(Path("resources/openvas/OpenVAS_bBWA.pdf"))
    assert not _re.search(r"[\x00-\x08\x0b-\x1f\x7f]", doc.text)
    assert "affected" in doc.text  # the \x1b ligature was restored, not dropped
