from datetime import date, datetime

from sqlalchemy import ForeignKey, Index, Integer, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, id_pk, one_of


class JiraIssue(Base):
    __tablename__ = "jira_issues"
    __table_args__ = (
        one_of("kind", ("flaky_test", "product_bug", "rewrite"), "kind"),
        # lifecycle (SLA job): SELECT ... FROM jira_issues
        #   WHERE status <> 'Done' AND due_date < :today
        Index("ix_jira_issues_status_due_date", "status", "due_date"),
    )

    id: Mapped[int] = id_pk()
    issue_key: Mapped[str] = mapped_column(Text, unique=True)
    kind: Mapped[str] = mapped_column(Text)
    quarantine_record_id: Mapped[int | None] = mapped_column(
        ForeignKey("quarantine_records.id", ondelete="CASCADE"), index=True
    )
    failure_signature_id: Mapped[int | None] = mapped_column(
        ForeignKey("failure_signatures.id", ondelete="SET NULL")
    )
    related_issue_id: Mapped[int | None] = mapped_column(
        ForeignKey("jira_issues.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(Text)
    severity: Mapped[str | None] = mapped_column(Text)  # product bugs only
    due_date: Mapped[date | None]
    reopen_count: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    overdue_notified_at: Mapped[datetime | None]
    created_at: Mapped[datetime]
    resolved_at: Mapped[datetime | None]
