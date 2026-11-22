from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import ForeignKey, Index, Integer, Numeric, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, id_pk, one_of
from app.db.models._enums import LIFECYCLE_STATES


class QuarantineRecord(Base):
    __tablename__ = "quarantine_records"
    __table_args__ = (
        one_of("state", LIFECYCLE_STATES, "state"),
        one_of("decision", ("auto", "lead_approved", "shadow"), "decision"),
        one_of(
            "shadow_outcome",
            ("auto_quarantine", "needs_lead_approval", "protected_alert"),
            "shadow_outcome",
        ),
        # lifecycle: SELECT ... FROM quarantine_records WHERE test_id = :t AND exited_at IS NULL
        Index(
            "ix_quarantine_records_test_id_open",
            "test_id",
            postgresql_where=text("exited_at IS NULL"),
        ),
    )

    id: Mapped[int] = id_pk()
    test_id: Mapped[int] = mapped_column(ForeignKey("tests.id", ondelete="CASCADE"), index=True)
    state: Mapped[str] = mapped_column(Text)
    decision: Mapped[str] = mapped_column(Text)
    shadow_outcome: Mapped[str | None] = mapped_column(Text)
    rate_at_entry: Mapped[Decimal | None] = mapped_column(Numeric)
    occurrences_at_entry: Mapped[int | None] = mapped_column(Integer)
    reason_suggested: Mapped[str | None] = mapped_column(Text)
    reason_confirmed: Mapped[str | None] = mapped_column(Text)
    fix_sha: Mapped[str | None] = mapped_column(Text)
    add_pr_id: Mapped[int | None] = mapped_column(
        ForeignKey("bot_pull_requests.id", ondelete="SET NULL"), index=True
    )
    remove_pr_id: Mapped[int | None] = mapped_column(
        ForeignKey("bot_pull_requests.id", ondelete="SET NULL"), index=True
    )
    days_quarantined_total: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    entered_at: Mapped[datetime | None]
    probation_until: Mapped[datetime | None]
    exited_at: Mapped[datetime | None]


class QuarantineDecision(Base):
    __tablename__ = "quarantine_decisions"
    __table_args__ = (
        one_of("decision", ("fix", "rewrite", "delete", "keep_blocking"), "decision"),
    )

    id: Mapped[int] = id_pk()
    quarantine_record_id: Mapped[int] = mapped_column(
        ForeignKey("quarantine_records.id", ondelete="CASCADE"), index=True
    )
    decision: Mapped[str] = mapped_column(Text)
    decided_by: Mapped[str] = mapped_column(Text)
    extension_until: Mapped[date | None]
    decided_at: Mapped[datetime]


class VerificationRun(Base):
    __tablename__ = "verification_runs"
    __table_args__ = (one_of("result", ("passed", "failed", "carried_over"), "result"),)

    id: Mapped[int] = id_pk()
    quarantine_record_id: Mapped[int] = mapped_column(
        ForeignKey("quarantine_records.id", ondelete="CASCADE"), index=True
    )
    ci_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("ci_runs.id", ondelete="CASCADE"), index=True
    )
    commit_sha: Mapped[str] = mapped_column(Text)
    repetitions_planned: Mapped[int] = mapped_column(Integer)
    repetitions_run: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    passes: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    result: Mapped[str | None] = mapped_column(Text)
