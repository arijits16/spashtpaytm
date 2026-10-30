"""Daily Merkle anchors (build plan §11.4).

The hash chain makes editing one receipt detectable. It does not make rewriting
*every* receipt detectable - someone with full database access could recompute
the whole chain forward from the first row they changed.

A daily anchor closes that: one SHA-256 root over the day's receipt hashes. In
production the root would be published somewhere we do not control (a tweet, a
Git commit, a timestamping service), so a rewritten chain would no longer match
a root the world already saw. Here it is stored in `daily_anchors` and shown as
"Today's anchor", with the publication step documented rather than implemented.

A binary tree, leaves in `seq` order, duplicating the last leaf when a level has
an odd count - the standard construction, written out because an anchor that
depends on an undocumented tree shape cannot be checked by anyone else.
"""

from __future__ import annotations

import hashlib
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.trust import DailyAnchor, Receipt


def _pair_hash(left: str, right: str) -> str:
    return hashlib.sha256((left + right).encode("utf-8")).hexdigest()


def merkle_root(leaves: list[str]) -> str | None:
    """The root over `leaves`, or None when there are none.

    Leaves are the receipts' hex hashes, combined as strings for the same reason
    the chain does (§11.2): one documented convention beats a clever one.
    """
    if not leaves:
        return None

    level = list(leaves)
    while len(level) > 1:
        if len(level) % 2 == 1:
            # Duplicate the last leaf so the level pairs up. Standard, and it
            # keeps the root defined for any count.
            level.append(level[-1])
        level = [_pair_hash(level[i], level[i + 1]) for i in range(0, len(level), 2)]
    return level[0]


def receipt_hashes_for(db: Session, day: date) -> list[str]:
    """That day's receipt hashes in `seq` order (UTC day boundaries)."""
    return list(
        db.scalars(
            select(Receipt.hash)
            .where(Receipt.created_at >= datetime.combine(day, datetime.min.time()))
            .where(Receipt.created_at < datetime.combine(day, datetime.max.time()))
            .order_by(Receipt.seq)
        ).all()
    )


def compute_anchor(db: Session, day: date) -> tuple[str | None, int]:
    """`(root, count)` for a day, without storing anything."""
    hashes = receipt_hashes_for(db, day)
    return merkle_root(hashes), len(hashes)


def upsert_anchor(db: Session, day: date) -> DailyAnchor | None:
    """Compute and store a day's anchor.

    `daily_anchors` is not append-only, because the day's root legitimately
    changes as more receipts are added to it. It settles once the day is over,
    which is when it would be published.
    """
    root, count = compute_anchor(db, day)
    if root is None:
        return None

    anchor = db.get(DailyAnchor, day)
    if anchor is None:
        anchor = DailyAnchor(day=day, merkle_root=root, receipt_count=count)
        db.add(anchor)
    else:
        anchor.merkle_root = root
        anchor.receipt_count = count
    db.flush()
    return anchor


def recent_anchors(db: Session, limit: int = 7) -> list[DailyAnchor]:
    return list(db.scalars(select(DailyAnchor).order_by(DailyAnchor.day.desc()).limit(limit)).all())
