"""schema: personas, catalog, journeys, evidence tables and the receipt ledger

The rest of build plan section 6, plus the three things SQLAlchemy models cannot
express and that the product depends on:

1. **Append-only triggers.** A PL/pgSQL `forbid_update_delete()` runs BEFORE
   UPDATE OR DELETE on `receipts`, `consents`, `audit_log` and
   `teachback_attempts`. Evidence that the application itself can rewrite is not
   evidence. `TRUNCATE` is deliberately still allowed, because the dev-only
   `make demo-reset` needs it and it cannot be used to alter a single row
   unnoticed.
2. **The `kfs_clauses.tsv` trigger + GIN index.** Phase 8 answers KFS questions
   by full-text search, and maintaining the vector in the database means a row
   inserted by the seed, by a test, or by phase 11 ingestion is searchable
   without the inserter remembering to do anything.
3. **`users.persona_id` -> `personas.id`.** Phase 1 left it a bare string
   because `personas` did not exist yet.

Revision ID: 0004_schema
Revises: 0003_user_session
Create Date: 2026-10-30 18:14:48.251755
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
revision: str = '0004_schema'
down_revision: str | None = '0003_user_session'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('daily_anchors',
    sa.Column('day', sa.Date(), nullable=False),
    sa.Column('merkle_root', sa.String(length=64), nullable=False),
    sa.Column('receipt_count', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('day', name=op.f('pk_daily_anchors'))
    )
    op.create_table('ledger_head',
    sa.Column('id', sa.Integer(), autoincrement=False, nullable=False),
    sa.Column('last_seq', sa.BigInteger(), server_default='0', nullable=False),
    sa.Column('last_hash', sa.String(length=64), server_default='0000000000000000000000000000000000000000000000000000000000000000', nullable=False),
    sa.CheckConstraint('id = 1', name=op.f('ck_ledger_head_single_row')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ledger_head'))
    )
    op.create_table('lenders',
    sa.Column('id', sa.String(length=50), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('type', sa.String(length=10), nullable=False),
    sa.Column('reg_no_sample', sa.String(length=100), nullable=False),
    sa.Column('grievance_contact_sample', sa.String(length=200), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("type IN ('NBFC', 'Bank')", name=op.f('ck_lenders_type')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_lenders'))
    )
    op.create_table('personas',
    sa.Column('id', sa.String(length=50), nullable=False),
    sa.Column('full_name', sa.String(length=200), nullable=False),
    sa.Column('display_name_masked', sa.String(length=200), nullable=False),
    sa.Column('name_local', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('gender', sa.String(length=10), nullable=False),
    sa.Column('age', sa.Integer(), nullable=False),
    sa.Column('dob', sa.Date(), nullable=False),
    sa.Column('city', sa.String(length=100), nullable=False),
    sa.Column('locality', sa.String(length=200), nullable=False),
    sa.Column('occupation', sa.String(length=100), nullable=False),
    sa.Column('business_name', sa.String(length=200), nullable=True),
    sa.Column('language', sa.String(length=10), server_default='mr-IN', nullable=False),
    sa.Column('mobile_masked', sa.String(length=32), nullable=False),
    sa.Column('consent_callbacks', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('dnd', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_personas'))
    )
    op.create_table('signing_keys',
    sa.Column('key_id', sa.String(length=50), nullable=False),
    sa.Column('public_key_b64', sa.Text(), nullable=False),
    sa.Column('active', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('key_id', name=op.f('pk_signing_keys'))
    )
    op.create_table('teachback_questions',
    sa.Column('id', sa.String(length=60), nullable=False),
    sa.Column('kfs_fact_key', sa.String(length=60), nullable=False),
    sa.Column('sort_order', sa.Integer(), server_default='0', nullable=False),
    sa.Column('prompt', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('options', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('reexplain', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('rubric', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('active', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_teachback_questions'))
    )
    op.create_table('aa_statements',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('persona_id', sa.String(length=50), nullable=False),
    sa.Column('fip_name', sa.String(length=120), nullable=False),
    sa.Column('account_masked', sa.String(length=40), nullable=False),
    sa.Column('month', sa.Date(), nullable=False),
    sa.Column('total_credits', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('total_debits', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('avg_balance', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('bounce_count', sa.Integer(), server_default='0', nullable=False),
    sa.Column('existing_emi', sa.Numeric(precision=14, scale=2), server_default='0', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['persona_id'], ['personas.id'], name=op.f('fk_aa_statements_persona_id_personas'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_aa_statements'))
    )
    op.create_index(op.f('ix_aa_statements_persona_id'), 'aa_statements', ['persona_id'], unique=False)
    op.create_table('ckyc_records',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('persona_id', sa.String(length=50), nullable=False),
    sa.Column('ckyc_number_masked', sa.String(length=32), nullable=False),
    sa.Column('kyc_status', sa.String(length=30), nullable=False),
    sa.Column('last_updated', sa.Date(), nullable=False),
    sa.Column('data', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['persona_id'], ['personas.id'], name=op.f('fk_ckyc_records_persona_id_personas'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ckyc_records'))
    )
    op.create_index(op.f('ix_ckyc_records_persona_id'), 'ckyc_records', ['persona_id'], unique=False)
    op.create_table('digilocker_records',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('persona_id', sa.String(length=50), nullable=False),
    sa.Column('doc_type', sa.String(length=30), nullable=False),
    sa.Column('data', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('issuer', sa.String(length=120), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("doc_type IN ('aadhaar', 'pan', 'address_proof')", name=op.f('ck_digilocker_records_doc_type')),
    sa.ForeignKeyConstraint(['persona_id'], ['personas.id'], name=op.f('fk_digilocker_records_persona_id_personas'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_digilocker_records'))
    )
    op.create_index(op.f('ix_digilocker_records_persona_id'), 'digilocker_records', ['persona_id'], unique=False)
    op.create_table('kfs_documents',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('lender_id', sa.String(length=50), nullable=False),
    sa.Column('offer_id', sa.String(length=50), nullable=True),
    sa.Column('version', sa.String(length=20), nullable=False),
    sa.Column('file_path', sa.String(length=500), nullable=False),
    sa.Column('file_sha256', sa.String(length=64), nullable=False),
    sa.Column('facts', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('verified_by', sa.String(length=200), nullable=True),
    sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('source', sa.String(length=20), server_default='seed', nullable=False),
    sa.Column('status', sa.String(length=20), server_default='active', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("source IN ('seed', 'sarvam_docai')", name=op.f('ck_kfs_documents_source')),
    sa.CheckConstraint("status IN ('draft', 'verified', 'active', 'retired')", name=op.f('ck_kfs_documents_status')),
    sa.ForeignKeyConstraint(['lender_id'], ['lenders.id'], name=op.f('fk_kfs_documents_lender_id_lenders')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_kfs_documents'))
    )
    op.create_index(op.f('ix_kfs_documents_lender_id'), 'kfs_documents', ['lender_id'], unique=False)
    op.create_index(op.f('ix_kfs_documents_offer_id'), 'kfs_documents', ['offer_id'], unique=False)
    op.create_table('loan_offers',
    sa.Column('id', sa.String(length=50), nullable=False),
    sa.Column('lender_id', sa.String(length=50), nullable=False),
    sa.Column('product', sa.String(length=40), server_default='personal_loan', nullable=False),
    sa.Column('principal', sa.Integer(), nullable=False),
    sa.Column('tenure_months', sa.Integer(), nullable=False),
    sa.Column('rate_pa', sa.Numeric(precision=6, scale=2), nullable=False),
    sa.Column('rate_type', sa.String(length=20), server_default='reducing', nullable=False),
    sa.Column('processing_fee', sa.Integer(), server_default='0', nullable=False),
    sa.Column('gst_on_fee', sa.Integer(), server_default='0', nullable=False),
    sa.Column('emi', sa.Integer(), nullable=False),
    sa.Column('total_repay', sa.Integer(), nullable=False),
    sa.Column('total_interest', sa.Integer(), nullable=False),
    sa.Column('apr', sa.Numeric(precision=6, scale=2), nullable=False),
    sa.Column('late_fee', sa.Integer(), nullable=False),
    sa.Column('foreclosure_pct', sa.Numeric(precision=5, scale=2), nullable=False),
    sa.Column('cooling_off_days', sa.Integer(), server_default='3', nullable=False),
    sa.Column('insurance_optional', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('insurance_premium', sa.Integer(), server_default='0', nullable=False),
    sa.Column('kfs_document_id', sa.UUID(), nullable=True),
    sa.Column('active', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['kfs_document_id'], ['kfs_documents.id'], name=op.f('fk_loan_offers_kfs_document_id_kfs_documents'), use_alter=True),
    sa.ForeignKeyConstraint(['lender_id'], ['lenders.id'], name=op.f('fk_loan_offers_lender_id_lenders')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_loan_offers'))
    )
    op.create_index(op.f('ix_loan_offers_lender_id'), 'loan_offers', ['lender_id'], unique=False)
    op.create_table('journeys',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('persona_id', sa.String(length=50), nullable=True),
    sa.Column('product', sa.String(length=40), server_default='personal_loan', nullable=False),
    sa.Column('language', sa.String(length=10), server_default='mr-IN', nullable=False),
    sa.Column('step', sa.String(length=30), server_default='INTRO', nullable=False),
    sa.Column('status', sa.String(length=20), server_default='active', nullable=False),
    sa.Column('context', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('selected_offer_id', sa.String(length=50), nullable=True),
    sa.Column('kfs_document_id', sa.UUID(), nullable=True),
    sa.Column('version', sa.Integer(), server_default='1', nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('last_activity_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("status IN ('active', 'completed', 'abandoned', 'needs_human')", name=op.f('ck_journeys_status')),
    sa.ForeignKeyConstraint(['kfs_document_id'], ['kfs_documents.id'], name=op.f('fk_journeys_kfs_document_id_kfs_documents')),
    sa.ForeignKeyConstraint(['persona_id'], ['personas.id'], name=op.f('fk_journeys_persona_id_personas')),
    sa.ForeignKeyConstraint(['selected_offer_id'], ['loan_offers.id'], name=op.f('fk_journeys_selected_offer_id_loan_offers')),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_journeys_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_journeys'))
    )
    op.create_index('ix_journeys_status_activity', 'journeys', ['status', 'last_activity_at'], unique=False)
    op.create_index(op.f('ix_journeys_user_id'), 'journeys', ['user_id'], unique=False)
    op.create_index('ix_journeys_user_status', 'journeys', ['user_id', 'status'], unique=False)
    op.create_table('kfs_clauses',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('kfs_document_id', sa.UUID(), nullable=False),
    sa.Column('clause_key', sa.String(length=60), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('text_en', sa.Text(), nullable=False),
    sa.Column('tsv', postgresql.TSVECTOR(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['kfs_document_id'], ['kfs_documents.id'], name=op.f('fk_kfs_clauses_kfs_document_id_kfs_documents'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_kfs_clauses'))
    )
    op.create_index(op.f('ix_kfs_clauses_kfs_document_id'), 'kfs_clauses', ['kfs_document_id'], unique=False)
    op.create_table('audit_log',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('journey_id', sa.UUID(), nullable=True),
    sa.Column('actor', sa.String(length=20), nullable=False),
    sa.Column('event_type', sa.String(length=60), nullable=False),
    sa.Column('step', sa.String(length=30), nullable=True),
    sa.Column('data', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('request_id', sa.String(length=64), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("actor IN ('customer', 'demo', 'system', 'agent', 'admin')", name=op.f('ck_audit_log_actor')),
    sa.ForeignKeyConstraint(['journey_id'], ['journeys.id'], name=op.f('fk_audit_log_journey_id_journeys'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_audit_log'))
    )
    op.create_index('ix_audit_log_created', 'audit_log', ['created_at'], unique=False)
    op.create_index(op.f('ix_audit_log_event_type'), 'audit_log', ['event_type'], unique=False)
    op.create_index('ix_audit_log_journey', 'audit_log', ['journey_id', 'created_at'], unique=False)
    op.create_table('consents',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('journey_id', sa.UUID(), nullable=False),
    sa.Column('purpose', sa.String(length=40), nullable=False),
    sa.Column('granted', sa.Boolean(), nullable=False),
    sa.Column('default_value', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('method', sa.String(length=10), server_default='tap', nullable=False),
    sa.Column('evidence', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("method IN ('tap', 'voice', 'tap+otp')", name=op.f('ck_consents_method')),
    sa.CheckConstraint("purpose IN ('fetch_digilocker', 'fetch_account_aggregator', 'loan_terms', 'insurance_addon', 'callback')", name=op.f('ck_consents_purpose')),
    sa.ForeignKeyConstraint(['journey_id'], ['journeys.id'], name=op.f('fk_consents_journey_id_journeys'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_consents'))
    )
    op.create_index('ix_consents_journey', 'consents', ['journey_id', 'created_at'], unique=False)
    op.create_table('conversation_turns',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('journey_id', sa.UUID(), nullable=False),
    sa.Column('turn_no', sa.Integer(), nullable=False),
    sa.Column('role', sa.String(length=10), nullable=False),
    sa.Column('text_enc', sa.LargeBinary(), nullable=False),
    sa.Column('nonce', sa.LargeBinary(), nullable=False),
    sa.Column('language', sa.String(length=10), nullable=False),
    sa.Column('source', sa.String(length=20), nullable=False),
    sa.Column('stt_ms', sa.Integer(), nullable=True),
    sa.Column('llm_ms', sa.Integer(), nullable=True),
    sa.Column('tts_ms', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("role IN ('user', 'assistant')", name=op.f('ck_conversation_turns_role')),
    sa.ForeignKeyConstraint(['journey_id'], ['journeys.id'], name=op.f('fk_conversation_turns_journey_id_journeys'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_conversation_turns'))
    )
    op.create_index('ix_conversation_turns_journey', 'conversation_turns', ['journey_id', 'turn_no'], unique=False)
    op.create_table('otp_challenges',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('journey_id', sa.UUID(), nullable=False),
    sa.Column('code_hmac', sa.String(length=64), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('attempts', sa.Integer(), server_default='0', nullable=False),
    sa.Column('locked', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['journey_id'], ['journeys.id'], name=op.f('fk_otp_challenges_journey_id_journeys'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_otp_challenges'))
    )
    op.create_index(op.f('ix_otp_challenges_journey_id'), 'otp_challenges', ['journey_id'], unique=False)
    op.create_table('receipts',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('receipt_no', sa.String(length=20), nullable=False),
    sa.Column('seq', sa.BigInteger(), nullable=False),
    sa.Column('journey_id', sa.UUID(), nullable=False),
    sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('payload_canonical', sa.Text(), nullable=False),
    sa.Column('prev_hash', sa.String(length=64), nullable=False),
    sa.Column('hash', sa.String(length=64), nullable=False),
    sa.Column('signature', sa.Text(), nullable=False),
    sa.Column('signing_key_id', sa.String(length=50), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['journey_id'], ['journeys.id'], name=op.f('fk_receipts_journey_id_journeys'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_receipts')),
    sa.UniqueConstraint('hash', name=op.f('uq_receipts_hash')),
    sa.UniqueConstraint('journey_id', name=op.f('uq_receipts_journey_id')),
    sa.UniqueConstraint('seq', name=op.f('uq_receipts_seq'))
    )
    op.create_index('ix_receipts_created', 'receipts', ['created_at'], unique=False)
    op.create_index(op.f('ix_receipts_receipt_no'), 'receipts', ['receipt_no'], unique=True)
    op.create_table('rescue_tasks',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('journey_id', sa.UUID(), nullable=False),
    sa.Column('kind', sa.String(length=10), server_default='stuck', nullable=False),
    sa.Column('reason', sa.Text(), nullable=False),
    sa.Column('step', sa.String(length=30), nullable=False),
    sa.Column('status', sa.String(length=20), server_default='pending', nullable=False),
    sa.Column('contact_window_ok', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("kind IN ('stuck', 'human')", name=op.f('ck_rescue_tasks_kind')),
    sa.CheckConstraint("status IN ('pending', 'ringing', 'resumed', 'closed')", name=op.f('ck_rescue_tasks_status')),
    sa.ForeignKeyConstraint(['journey_id'], ['journeys.id'], name=op.f('fk_rescue_tasks_journey_id_journeys'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_rescue_tasks'))
    )
    op.create_index(op.f('ix_rescue_tasks_journey_id'), 'rescue_tasks', ['journey_id'], unique=False)
    op.create_index('ix_rescue_tasks_status', 'rescue_tasks', ['status', 'created_at'], unique=False)
    op.create_table('teachback_attempts',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('journey_id', sa.UUID(), nullable=False),
    sa.Column('question_id', sa.String(length=60), nullable=False),
    sa.Column('attempt_no', sa.Integer(), nullable=False),
    sa.Column('answer_type', sa.String(length=10), nullable=False),
    sa.Column('answer_value', sa.String(length=500), nullable=False),
    sa.Column('is_correct', sa.Boolean(), nullable=False),
    sa.Column('grader', sa.String(length=10), server_default='rule', nullable=False),
    sa.Column('confidence', sa.Numeric(precision=4, scale=3), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("answer_type IN ('option', 'voice', 'text')", name=op.f('ck_teachback_attempts_answer_type')),
    sa.CheckConstraint("grader IN ('rule', 'llm')", name=op.f('ck_teachback_attempts_grader')),
    sa.ForeignKeyConstraint(['journey_id'], ['journeys.id'], name=op.f('fk_teachback_attempts_journey_id_journeys'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['question_id'], ['teachback_questions.id'], name=op.f('fk_teachback_attempts_question_id_teachback_questions')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_teachback_attempts'))
    )
    op.create_index('ix_teachback_attempts_journey', 'teachback_attempts', ['journey_id', 'created_at'], unique=False)
    op.create_index(op.f('ix_teachback_attempts_question_id'), 'teachback_attempts', ['question_id'], unique=False)
    op.create_table('turn_requests',
    sa.Column('client_turn_id', sa.UUID(), nullable=False),
    sa.Column('journey_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('response', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['journey_id'], ['journeys.id'], name=op.f('fk_turn_requests_journey_id_journeys'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_turn_requests_user_id_users')),
    sa.PrimaryKeyConstraint('client_turn_id', name=op.f('pk_turn_requests'))
    )
    op.create_index('ix_turn_requests_created', 'turn_requests', ['created_at'], unique=False)
    op.create_index(op.f('ix_turn_requests_journey_id'), 'turn_requests', ['journey_id'], unique=False)

    # --- 1. users.persona_id becomes a real foreign key -------------------
    #
    # Phase 1 left this a plain string because `personas` did not exist. Any
    # value that is not a seeded persona is cleared first, otherwise creating
    # the constraint on a developer database fails.
    op.execute(
        "UPDATE users SET persona_id = NULL "
        "WHERE persona_id IS NOT NULL "
        "AND persona_id NOT IN (SELECT id FROM personas)"
    )
    op.create_foreign_key(
        op.f("fk_users_persona_id_personas"),
        "users",
        "personas",
        ["persona_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # --- 2. full-text search over KFS clauses ----------------------------
    #
    # 'english' because the KFS PDFs are in English (the RBI format); the
    # customer's question is translated to a keyword search by phase 8.
    op.execute(
        """
        CREATE FUNCTION kfs_clauses_tsv_update() RETURNS trigger AS $$
        BEGIN
            NEW.tsv :=
                setweight(to_tsvector('english', coalesce(NEW.title, '')), 'A') ||
                setweight(to_tsvector('english', coalesce(NEW.text_en, '')), 'B') ||
                setweight(to_tsvector('english', coalesce(NEW.clause_key, '')), 'C');
            RETURN NEW;
        END
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER kfs_clauses_tsv
        BEFORE INSERT OR UPDATE ON kfs_clauses
        FOR EACH ROW EXECUTE FUNCTION kfs_clauses_tsv_update()
        """
    )
    op.create_index(
        "ix_kfs_clauses_tsv", "kfs_clauses", ["tsv"], postgresql_using="gin"
    )

    # --- 3. append-only evidence tables ----------------------------------
    #
    # The message names the table so a developer who hits this in a test knows
    # immediately that it is a designed refusal, not a bug.
    op.execute(
        """
        CREATE FUNCTION forbid_update_delete() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION
                'table % is append-only: % is not permitted (build plan 6, 13.9)',
                TG_TABLE_NAME, TG_OP
                USING ERRCODE = 'restrict_violation';
        END
        $$ LANGUAGE plpgsql
        """
    )
    for table in ("receipts", "consents", "audit_log", "teachback_attempts"):
        op.execute(
            f"""
            CREATE TRIGGER {table}_append_only
            BEFORE UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION forbid_update_delete()
            """
        )

    # --- 4. the single ledger head row -----------------------------------
    #
    # Seeded here rather than by `make seed`: the first receipt append locks
    # this row, and a missing head would fail at the worst possible moment.
    op.execute(
        "INSERT INTO ledger_head (id, last_seq, last_hash) "
        f"VALUES (1, 0, '{'0' * 64}') ON CONFLICT (id) DO NOTHING"
    )


def downgrade() -> None:
    for table in ("receipts", "consents", "audit_log", "teachback_attempts"):
        op.execute(f"DROP TRIGGER IF EXISTS {table}_append_only ON {table}")
    op.execute("DROP FUNCTION IF EXISTS forbid_update_delete()")
    op.drop_index("ix_kfs_clauses_tsv", table_name="kfs_clauses")
    op.execute("DROP TRIGGER IF EXISTS kfs_clauses_tsv ON kfs_clauses")
    op.execute("DROP FUNCTION IF EXISTS kfs_clauses_tsv_update()")
    op.drop_constraint(op.f("fk_users_persona_id_personas"), "users", type_="foreignkey")
    op.drop_index(op.f('ix_turn_requests_journey_id'), table_name='turn_requests')
    op.drop_index('ix_turn_requests_created', table_name='turn_requests')
    op.drop_table('turn_requests')
    op.drop_index(op.f('ix_teachback_attempts_question_id'), table_name='teachback_attempts')
    op.drop_index('ix_teachback_attempts_journey', table_name='teachback_attempts')
    op.drop_table('teachback_attempts')
    op.drop_index('ix_rescue_tasks_status', table_name='rescue_tasks')
    op.drop_index(op.f('ix_rescue_tasks_journey_id'), table_name='rescue_tasks')
    op.drop_table('rescue_tasks')
    op.drop_index(op.f('ix_receipts_receipt_no'), table_name='receipts')
    op.drop_index('ix_receipts_created', table_name='receipts')
    op.drop_table('receipts')
    op.drop_index(op.f('ix_otp_challenges_journey_id'), table_name='otp_challenges')
    op.drop_table('otp_challenges')
    op.drop_index('ix_conversation_turns_journey', table_name='conversation_turns')
    op.drop_table('conversation_turns')
    op.drop_index('ix_consents_journey', table_name='consents')
    op.drop_table('consents')
    op.drop_index('ix_audit_log_journey', table_name='audit_log')
    op.drop_index(op.f('ix_audit_log_event_type'), table_name='audit_log')
    op.drop_index('ix_audit_log_created', table_name='audit_log')
    op.drop_table('audit_log')
    op.drop_index(op.f('ix_kfs_clauses_kfs_document_id'), table_name='kfs_clauses')
    op.drop_table('kfs_clauses')
    op.drop_index('ix_journeys_user_status', table_name='journeys')
    op.drop_index(op.f('ix_journeys_user_id'), table_name='journeys')
    op.drop_index('ix_journeys_status_activity', table_name='journeys')
    op.drop_table('journeys')
    op.drop_index(op.f('ix_loan_offers_lender_id'), table_name='loan_offers')
    op.drop_table('loan_offers')
    op.drop_index(op.f('ix_kfs_documents_offer_id'), table_name='kfs_documents')
    op.drop_index(op.f('ix_kfs_documents_lender_id'), table_name='kfs_documents')
    op.drop_table('kfs_documents')
    op.drop_index(op.f('ix_digilocker_records_persona_id'), table_name='digilocker_records')
    op.drop_table('digilocker_records')
    op.drop_index(op.f('ix_ckyc_records_persona_id'), table_name='ckyc_records')
    op.drop_table('ckyc_records')
    op.drop_index(op.f('ix_aa_statements_persona_id'), table_name='aa_statements')
    op.drop_table('aa_statements')
    op.drop_table('teachback_questions')
    op.drop_table('signing_keys')
    op.drop_table('personas')
    op.drop_table('lenders')
    op.drop_table('ledger_head')
    op.drop_table('daily_anchors')
