"""Serving the sample KFS PDF (build plan §8.2).

The app opens this in an in-app PDF viewer and the KFS card links to it. It is
behind auth because it is part of a loan journey, not because the document is
secret - every copy is watermarked SAMPLE and the lenders are fictional.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse

from app.config import BACKEND_DIR
from app.db.models.catalog import KfsDocument
from app.deps import CurrentUser, DbDep
from app.errors import not_found
from app.security.ratelimit import client_identity, limiter

log = logging.getLogger(__name__)

router = APIRouter(tags=["kfs"], prefix="/kfs")


@router.get("/{document_id}/file")
def get_kfs_file(
    document_id: uuid.UUID, request: Request, user: CurrentUser, db: DbDep
) -> FileResponse:
    """The KFS PDF for a document id."""
    limiter.enforce("public", client_identity(request, str(user.id)))

    document = db.get(KfsDocument, document_id)
    if document is None:
        raise not_found("Key Fact Statement not found")

    # `file_path` is ours, written by the seed, never client-supplied - but it
    # is resolved and bounded anyway, so a future ingestion path that stores a
    # relative path cannot be turned into an arbitrary file read.
    path = (BACKEND_DIR / document.file_path).resolve()
    allowed_root = (BACKEND_DIR / "app" / "assets").resolve()
    if not path.is_file() or not path.is_relative_to(allowed_root):
        log.warning(
            "KFS file missing or outside the asset root",
            extra={"document_id": str(document_id)},
        )
        raise not_found("Key Fact Statement file is not available")

    return FileResponse(
        path,
        media_type="application/pdf",
        filename=f"KFS-{document.version}-SAMPLE.pdf",
        headers={
            # It is a sample document for one journey; a shared cache holding it
            # buys nothing and a stale copy would misstate the terms.
            "Cache-Control": "private, max-age=300",
            "Content-Disposition": f'inline; filename="KFS-{document.version}-SAMPLE.pdf"',
        },
    )
