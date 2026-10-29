"""ORM models.

Importing this package imports every model module, so `Base.metadata` is
complete for Alembic autogenerate. More tables arrive in phase 2.
"""

from app.db.models.user import User

__all__ = ["User"]
