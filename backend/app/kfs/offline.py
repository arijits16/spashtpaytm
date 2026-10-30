"""The offline extraction fallback (build plan phase 11, item 4).

`pdfplumber` over our own generated PDFs. It exists for three reasons, in order
of how often each one matters:

1. **The demo has to work with no network.** Document Intelligence is a remote
   call on venue Wi-Fi; `make demo-reset` and the KFS library must still do
   something real when it is unreachable (§10.6).
2. **The tests must not call a paid API.**
3. **It is a control on the model.** Two independent readings of the same
   document that agree is worth more than one confident reading.

It reads label/value rows, which is what an RBI-format KFS is: a label on the
left, a figure right-aligned on the same line. That makes it reliable on the
documents `scripts/generate_kfs_pdf.py` produces and honest about its own limits
on anything else - a row it cannot find is reported missing rather than guessed,
and every field it does return carries a lower confidence than the model's.
"""

from __future__ import annotations

import io
import logging
import re

from app.kfs.schema import FIELDS

log = logging.getLogger(__name__)

# Lower than anything Document Intelligence returns, on purpose: a regex over a
# label is a weaker reading than a model that saw the page, and the dashboard
# sorts a human's attention by confidence.
OFFLINE_CONFIDENCE = 0.55

ENGINE = "pdfplumber"


def _normalise(text: str) -> str:
    """Collapse whitespace so a wrapped label still matches."""
    return re.sub(r"\s+", " ", text).strip().lower()


def extract_text(pdf_bytes: bytes) -> str:
    """All text of a PDF, one line per line. Empty string if it cannot be read."""
    try:
        import pdfplumber
    except ImportError:  # pragma: no cover - pdfplumber is a declared dependency
        log.warning("pdfplumber is not installed; offline extraction is unavailable")
        return ""

    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            pages = [page.extract_text() or "" for page in pdf.pages]
        return "\n".join(pages)
    except Exception:  # noqa: BLE001 - a corrupt upload must not 500
        log.warning("pdfplumber could not read the upload")
        return ""


def extract(pdf_bytes: bytes) -> tuple[dict[str, str], dict[str, float], str]:
    """Read the KFS rows out of a PDF.

    Returns the raw string per field, the confidence per field, and the text the
    reading came from (kept so a clause importer can reuse it).
    """
    text = extract_text(pdf_bytes)
    if not text:
        return {}, {}, ""

    lines = [line for line in (raw.strip() for raw in text.splitlines()) if line]
    normalised = [(_normalise(line), line) for line in lines]

    raw_fields: dict[str, str] = {}
    confidence: dict[str, float] = {}

    for field in FIELDS:
        for label in field.labels:
            needle = _normalise(label)
            hit = next((original for flat, original in normalised if flat.startswith(needle)), None)
            if hit is None:
                continue

            # Everything after the label is the value. Matching on the
            # normalised prefix and then slicing the *original* keeps "INR
            # 1,00,000" intact including its digit grouping.
            value = hit[len(label) :].strip(" :\t.·") or hit
            raw_fields[field.key] = value
            confidence[field.key] = OFFLINE_CONFIDENCE
            break

    log.info(
        "offline extraction finished",
        extra={"fields": len(raw_fields), "lines": len(lines)},
    )
    return raw_fields, confidence, text
