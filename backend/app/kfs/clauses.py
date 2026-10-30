"""Importing a KFS's terms as searchable clauses (build plan §6, §10.3, phase 11).

Phase 8 answers "what if I close the loan early?" by full-text searching
`kfs_clauses` and answering from the matched clause only. A newly ingested
document that has facts but no clauses would therefore extract and publish
correctly and then be unable to answer a question about itself.

The titles of an RBI-format KFS's terms section are conventional, so they are
matched directly. Anything that does not match a known title is still imported,
keyed by its position - a clause nobody anticipated is worth searching, and the
alternative is silently dropping the paragraph a customer asks about.

`tsv` is maintained by a database trigger (migration 0004), so nothing here has
to remember to build the search vector.
"""

from __future__ import annotations

import difflib
import logging
import re

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.db.models.catalog import KfsClause

log = logging.getLogger(__name__)

# The conventional titles, with the key each becomes. Phase 8's search is over
# the text, so a key is only a label - but a stable label means the dashboard
# and the seeded documents agree.
KNOWN_TITLES: dict[str, str] = {
    "repayment schedule": "emi_schedule",
    "rate of interest and apr": "interest_rate",
    "fees and other charges": "processing_fee",
    "penal charges for delayed payment": "late_fee",
    "prepayment and foreclosure": "foreclosure",
    "cooling-off / look-up period": "cooling_off",
    "cooling-off period": "cooling_off",
    "insurance": "insurance_optional",
    "grievance redressal": "grievance",
    "recovery practices": "recovery",
}

# Where the clauses start in an RBI-format KFS.
_TERMS_HEADING = re.compile(r"^\s*\d*\.?\s*terms and conditions\s*$", re.IGNORECASE)

# A clause title is a short line with no sentence-ending punctuation. The rest
# of the section is its body until the next such line.
_MAX_TITLE_WORDS = 7

_FOOTER = re.compile(r"(SAMPLE document for a concept|Page \d+ of \d+|Grievance:)", re.IGNORECASE)

# The SAMPLE watermark is drawn diagonally, so `pdfplumber` reads its glyphs as
# stray one- and two-character lines between the real ones. Dropped by length:
# no clause title or body line in a KFS is two characters long.
_MIN_LINE_CHARS = 3

# A watermark glyph can also land *inside* a line ("Recovery practicSes"), so a
# title is matched by similarity rather than equality. 0.85 recognises one
# inserted character in a short title and still separates "Insurance" from
# "Grievance redressal".
_TITLE_SIMILARITY = 0.85


def match_title(title: str) -> str | None:
    """The conventional key for a title, allowing for one stray glyph."""
    flat = re.sub(r"[^a-z]+", " ", title.lower()).strip()
    if not flat:
        return None

    best_key: str | None = None
    best_ratio = _TITLE_SIMILARITY

    for known, key in KNOWN_TITLES.items():
        known_flat = re.sub(r"[^a-z]+", " ", known).strip()
        ratio = difflib.SequenceMatcher(None, flat, known_flat).ratio()
        if ratio >= best_ratio:
            best_key, best_ratio = key, ratio

    return best_key


def split_clauses(text: str) -> list[tuple[str, str, str]]:
    """Split a KFS's text into `(clause_key, title, body)`.

    Returns an empty list when the document has no recognisable terms section,
    which is a fact about the document rather than a failure: the facts are
    still verifiable and publishable, and the dashboard reports the clause count.
    """
    lines = [raw.strip() for raw in text.splitlines()]

    start = next((index for index, line in enumerate(lines) if _TERMS_HEADING.match(line)), None)
    if start is None:
        return []

    clauses: list[tuple[str, str, str]] = []
    title: str | None = None
    body: list[str] = []

    def flush() -> None:
        if title is None:
            return
        joined = re.sub(r"\s+", " ", " ".join(body)).strip()
        if not joined:
            return
        key = match_title(title) or f"clause_{len(clauses) + 1}"
        clauses.append((key, title[:200], joined))

    for line in lines[start + 1 :]:
        if len(line) < _MIN_LINE_CHARS or _FOOTER.search(line):
            continue

        words = line.split()
        looks_like_title = (
            len(words) <= _MAX_TITLE_WORDS
            and not line.endswith((".", ",", ";", ":"))
            and line[0].isupper()
        )

        if looks_like_title:
            flush()
            title, body = line, []
        elif title is not None:
            body.append(line)

    flush()
    return clauses


def replace_clauses(db: Session, document_id: object, text: str) -> int:
    """Import a document's clauses, replacing whatever was there.

    Replaced wholesale rather than merged: a re-extraction describes the same
    file, so a half-updated clause set would mean search hitting text that is
    not in the PDF the receipt's hash commits to.
    """
    clauses = split_clauses(text)

    db.execute(delete(KfsClause).where(KfsClause.kfs_document_id == document_id))
    for key, title, body in clauses:
        db.add(KfsClause(kfs_document_id=document_id, clause_key=key, title=title, text_en=body))

    log.info("kfs clauses imported", extra={"count": len(clauses)})
    return len(clauses)
