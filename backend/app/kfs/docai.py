"""Sarvam Document Intelligence: reading a KFS PDF (build plan §10, §8.5, phase 11).

The flow the API defines, and the flow this implements:

    POST /doc-ai/v1/job/extract   (multipart: file + schema)  -> job_id
    GET  /doc-ai/v1/job/{id}/status   until status == completed
    GET  /doc-ai/v1/job/{id}/results  -> { result, annotations }

`result` is the extracted object; `annotations` carries per-field confidence and
the span each value was read from. Both are kept: the confidence is what directs
a human's attention on the dashboard, and the span is what lets them check a
figure against the page instead of trusting a score.

**This is offline work, so it is allowed to be slow.** Unlike a customer's turn
there is no four-second budget here - an admin uploaded a PDF and expects a
spinner - which is why the client's `docai` timeout is 120 s and why the poll
runs to a wall-clock deadline rather than a fixed number of attempts.

**It is never on the golden path.** Every failure mode - no key, a timeout, a
job that fails, a malformed result - falls back to `kfs/offline.py`, and the
dashboard says which engine read the document. A demo with no network still
ingests a PDF.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from app.ai.sarvam_client import SarvamError, client_for
from app.config import Settings
from app.kfs.schema import json_schema

log = logging.getLogger(__name__)

EXTRACT_PATH = "/doc-ai/v1/job/extract"

ENGINE = "sarvam_docai"

# How long to wait for a job, and how often to ask. Document Intelligence takes
# a few seconds on a two-page PDF; the ceiling exists so a stuck job becomes a
# fallback to offline extraction rather than a request that never answers.
POLL_INTERVAL_SECONDS = 2.0
POLL_DEADLINE_SECONDS = 90.0

_TERMINAL_FAILURES = frozenset({"failed", "error", "cancelled", "canceled"})


@dataclass(frozen=True, slots=True)
class Extraction:
    """What an engine read out of one document.

    @param raw_fields  The verbatim strings, before `kfs/parse.py` touches them.
    @param confidence  Per field, 0-1. Absent for a field the engine did not score.
    @param engine      'sarvam_docai' or 'pdfplumber'.
    @param job_id      The Document Intelligence job, for support questions.
    @param annotations The per-field source spans, kept so a human can check a
                       figure against the page rather than against a score.
    """

    raw_fields: dict[str, Any]
    confidence: dict[str, float]
    engine: str
    job_id: str | None = None
    annotations: dict[str, Any] = field(default_factory=dict)

    def as_metadata(self) -> dict[str, Any]:
        """The `kfs_documents.extraction` column."""
        return {
            "engine": self.engine,
            "jobId": self.job_id,
            "rawFields": {key: str(value) for key, value in self.raw_fields.items()},
            "confidence": self.confidence,
            "annotations": self.annotations,
        }


def _job_id(payload: dict[str, Any]) -> str:
    """The job id, under whichever key this deployment uses."""
    for key in ("job_id", "jobId", "id"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value

    # Some deployments nest it under `data`.
    data = payload.get("data")
    if isinstance(data, dict):
        return _job_id(data)

    raise SarvamError("malformed", "extract job did not return a job id")


def _status(payload: dict[str, Any]) -> str:
    for key in ("status", "job_status", "state"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value.lower()
    data = payload.get("data")
    if isinstance(data, dict):
        return _status(data)
    return "unknown"


def _confidence_from(annotations: Any) -> dict[str, float]:
    """Pull a per-field confidence out of `annotations`, whatever its shape.

    Written defensively on purpose: the annotation block is the part of this API
    most likely to gain a nesting level, and a confidence we cannot find should
    mean "unscored" on the dashboard, not a 500 on an upload an admin is
    watching.
    """
    scores: dict[str, float] = {}

    if isinstance(annotations, dict):
        for key, value in annotations.items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                scores[key] = float(value)
            elif isinstance(value, dict):
                for name in ("confidence", "score", "probability"):
                    inner = value.get(name)
                    if isinstance(inner, (int, float)) and not isinstance(inner, bool):
                        scores[key] = float(inner)
                        break

    elif isinstance(annotations, list):
        for entry in annotations:
            if not isinstance(entry, dict):
                continue
            name = entry.get("field") or entry.get("key") or entry.get("name")
            value = entry.get("confidence", entry.get("score"))
            if isinstance(name, str) and isinstance(value, (int, float)):
                scores[name] = float(value)

    return {key: max(0.0, min(1.0, value)) for key, value in scores.items()}


def _result_from(payload: dict[str, Any]) -> tuple[dict[str, Any], Any]:
    """The extracted object and its annotations, from a results response."""
    body: Any = payload
    if isinstance(payload.get("data"), dict):
        body = payload["data"]

    result = body.get("result") if isinstance(body, dict) else None
    if isinstance(result, str):
        # Some deployments return the object as a JSON string.
        try:
            result = json.loads(result)
        except ValueError:
            result = None

    if not isinstance(result, dict):
        raise SarvamError("malformed", "extract job returned no result object")

    return result, (body.get("annotations") if isinstance(body, dict) else None)


async def extract(pdf_bytes: bytes, filename: str, settings: Settings) -> Extraction:
    """Run one extraction job to completion.

    Raises `SarvamError` on anything that goes wrong, including a job that is
    still running at the deadline. The caller falls back to offline extraction.
    """
    client = client_for(settings)

    submitted = await client.post_multipart(
        EXTRACT_PATH,
        files={"file": (filename, pdf_bytes, "application/pdf")},
        data={"schema": json.dumps(json_schema(), ensure_ascii=False)},
        kind="docai",
    )
    job = _job_id(submitted.payload)
    log.info("document intelligence job submitted", extra={"job_id": job})

    deadline = time.monotonic() + POLL_DEADLINE_SECONDS
    status = "pending"

    while time.monotonic() < deadline:
        await asyncio.sleep(POLL_INTERVAL_SECONDS)
        polled = await client.get_json(f"{EXTRACT_PATH.rsplit('/', 1)[0]}/{job}/status")
        status = _status(polled.payload)

        if status in ("completed", "complete", "succeeded", "success"):
            break
        if status in _TERMINAL_FAILURES:
            raise SarvamError("status", f"extract job {job} finished as '{status}'")

    else:
        raise SarvamError("timeout", f"extract job {job} did not finish in time")

    results = await client.get_json(f"{EXTRACT_PATH.rsplit('/', 1)[0]}/{job}/results")
    result, annotations = _result_from(results.payload)

    log.info(
        "document intelligence job completed",
        extra={"job_id": job, "fields": len(result)},
    )

    return Extraction(
        raw_fields=result,
        confidence=_confidence_from(annotations),
        engine=ENGINE,
        job_id=job,
        annotations=annotations if isinstance(annotations, dict) else {},
    )
