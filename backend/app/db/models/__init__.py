"""ORM models.

Importing this package imports every model module, so `Base.metadata` is
complete for Alembic autogenerate.
"""

from app.db.models.catalog import (
    KfsClause,
    KfsDocument,
    Lender,
    LoanOffer,
    TeachbackQuestion,
)
from app.db.models.journey import (
    AuditLog,
    Consent,
    ConversationTurn,
    Journey,
    OtpChallenge,
    RescueTask,
    TeachbackAttempt,
    TurnRequest,
)
from app.db.models.persona import AaStatement, CkycRecord, DigilockerRecord, Persona
from app.db.models.trust import DailyAnchor, LedgerHead, Receipt, SigningKey
from app.db.models.user import User

__all__ = [
    "AaStatement",
    "AuditLog",
    "CkycRecord",
    "Consent",
    "ConversationTurn",
    "DailyAnchor",
    "DigilockerRecord",
    "Journey",
    "KfsClause",
    "KfsDocument",
    "LedgerHead",
    "Lender",
    "LoanOffer",
    "OtpChallenge",
    "Persona",
    "Receipt",
    "RescueTask",
    "SigningKey",
    "TeachbackAttempt",
    "TeachbackQuestion",
    "TurnRequest",
    "User",
]
