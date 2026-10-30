"""Wipe journey data and re-seed (`make demo-reset`, build plan phase 2).

Between rehearsals the demo has to start from nothing: no half-finished journey
to resume, no receipts in the ledger, a clean funnel on the dashboard. This is
the only thing in the codebase that removes evidence rows, and it does so with
`TRUNCATE`, which the append-only triggers do not intercept (§6). That is
deliberate and it is also why this script refuses to run anywhere but dev:
`TRUNCATE` is exactly the operation the triggers exist to prevent.

What it keeps: personas, lenders, offers, KFS documents and the question bank -
the catalogue. What it clears: every journey and everything downstream of one,
plus the ledger chain, which is reset to genesis.
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import text  # noqa: E402

from app.config import settings  # noqa: E402
from app.db.models.trust import GENESIS_HASH  # noqa: E402
from app.db.session import engine  # noqa: E402
from app.seed.run import run as reseed  # noqa: E402

# Order does not matter: one TRUNCATE ... CASCADE statement handles the graph.
JOURNEY_TABLES = (
    "receipts",
    "daily_anchors",
    "rescue_tasks",
    "otp_challenges",
    "consents",
    "teachback_attempts",
    "conversation_turns",
    "turn_requests",
    "audit_log",
    "journeys",
)


def reset() -> None:
    """Truncate journey data, reset the ledger head, re-seed the catalogue."""
    if not settings.is_dev:
        raise SystemExit(
            f"refusing to run: APP_ENV is '{settings.app_env}', not 'dev'. "
            "demo-reset truncates evidence tables and exists only for rehearsals."
        )

    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {', '.join(JOURNEY_TABLES)} CASCADE"))

        # The chain starts again from genesis, so the first new receipt is seq 1
        # with a 64-zero prev_hash and verifies on its own.
        conn.execute(
            text("UPDATE ledger_head SET last_seq = 0, last_hash = :h WHERE id = 1"),
            {"h": GENESIS_HASH},
        )

        # Demo users are rebuilt on their next sign-in; real Google users keep
        # their row so the human does not have to log in again mid-rehearsal.
        conn.execute(text("DELETE FROM users WHERE firebase_uid LIKE 'demo:%'"))

    print("==> journey data cleared, ledger reset to genesis")
    for group, count in reseed().items():
        print(f"    {group:22} {count}")
    print("==> demo-reset complete")


if __name__ == "__main__":
    reset()
