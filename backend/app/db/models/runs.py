from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    Integer,
    PrimaryKeyConstraint,
    SmallInteger,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, id_pk, one_of
from app.db.models._enums import EVENT, EVIDENCE, JOB_KIND, OUTCOME


class CiRun(Base):
    __tablename__ = "ci_runs"
    __table_args__ = (
        UniqueConstraint(
            "repository_id", "ci_system", "run_id", name="uq_ci_runs_repository_id_ci_system_run_id"
        ),
        one_of("ci_system", ("jenkins", "github_actions"), "ci_system"),
        # flaky detection (M2) cross-run evidence:
        #   SELECT id FROM ci_runs
        #   WHERE repository_id = :r AND commit_sha = :sha AND environment = :env
        # The spec (§10) puts repository_id first; the issue text omits it. Spec wins.
        Index(
            "ix_ci_runs_repository_id_commit_sha_environment",
            "repository_id", "commit_sha", "environment",
        ),
    )  # fmt: skip

    id: Mapped[int] = id_pk()
    repository_id: Mapped[int] = mapped_column(ForeignKey("repositories.id", ondelete="CASCADE"))
    ci_system: Mapped[str] = mapped_column(Text)
    run_id: Mapped[str] = mapped_column(Text)
    pipeline: Mapped[str | None] = mapped_column(Text)
    run_url: Mapped[str | None] = mapped_column(Text)
    commit_sha: Mapped[str] = mapped_column(Text)
    branch: Mapped[str | None] = mapped_column(Text)
    event: Mapped[str] = mapped_column(EVENT)
    # '' (not NULL) when unset: NULLs never collide in a unique key or match `= :env`.
    environment: Mapped[str] = mapped_column(Text, server_default="")
    is_environmental: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    test_count: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    failed_count: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    started_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]


class FailureSignature(Base):
    __tablename__ = "failure_signatures"
    __table_args__ = (one_of("category", ("infra", "test", "unknown"), "category"),)

    id: Mapped[int] = id_pk()
    fingerprint: Mapped[str] = mapped_column(Text, unique=True)
    exception_type: Mapped[str | None] = mapped_column(Text)
    normalized_message: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str] = mapped_column(Text, server_default="unknown")
    suggested_reason: Mapped[str | None] = mapped_column(Text)


class TestExecution(Base):
    """Partitioned monthly by ``executed_at`` (migration 0002 creates the partitions).

    The primary key includes the partition key because Postgres requires it. Every query on this
    table must filter ``executed_at`` (CLAUDE.md), or it scans every partition.
    """

    __tablename__ = "test_executions"
    __test__ = False  # not a pytest class
    __table_args__ = (
        PrimaryKeyConstraint("id", "executed_at", name="pk_test_executions"),
        ForeignKeyConstraint(
            ["ci_run_id"],
            ["ci_runs.id"],
            name="fk_test_executions_ci_run_id_ci_runs",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["test_id"], ["tests.id"], name="fk_test_executions_test_id_tests", ondelete="CASCADE"
        ),
        ForeignKeyConstraint(
            ["failure_signature_id"],
            ["failure_signatures.id"],
            name="fk_test_executions_failure_signature_id_failure_signatures",
            ondelete="SET NULL",
        ),
        # flaky detection: SELECT ... FROM test_executions
        #   WHERE test_id = :t AND executed_at >= :since ORDER BY executed_at
        Index("ix_test_executions_test_id_executed_at", "test_id", "executed_at"),
        Index("ix_test_executions_ci_run_id", "ci_run_id"),
        {"postgresql_partition_by": "RANGE (executed_at)"},
    )  # fmt: skip

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True))
    ci_run_id: Mapped[int] = mapped_column(BigInteger)
    test_id: Mapped[int] = mapped_column(BigInteger)
    run_attempt: Mapped[int] = mapped_column(SmallInteger, server_default=text("1"))  # CI re-run
    attempt: Mapped[int] = mapped_column(SmallInteger, server_default=text("1"))  # framework rerun
    shard: Mapped[str | None] = mapped_column(Text)
    job_kind: Mapped[str] = mapped_column(JOB_KIND)
    outcome: Mapped[str] = mapped_column(OUTCOME)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    failure_signature_id: Mapped[int | None] = mapped_column(BigInteger)
    message_excerpt: Mapped[str | None] = mapped_column(Text)  # masked
    was_quarantined: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    executed_at: Mapped[datetime]


class FlakyEvent(Base):
    __tablename__ = "flaky_events"
    __table_args__ = (
        # One flaky occurrence per execution group (§10 detection indexes).
        UniqueConstraint(
            "test_id",
            "commit_sha",
            "environment",
            name="uq_flaky_events_test_id_commit_sha_environment",
        ),
    )  # fmt: skip

    id: Mapped[int] = id_pk()
    test_id: Mapped[int] = mapped_column(ForeignKey("tests.id", ondelete="CASCADE"))
    commit_sha: Mapped[str] = mapped_column(Text)
    # '' (not NULL) when unset: NULLs never collide in a unique key or match `= :env`.
    environment: Mapped[str] = mapped_column(Text, server_default="")
    evidence: Mapped[str] = mapped_column(EVIDENCE)
    branch: Mapped[str | None] = mapped_column(Text)
    failure_signature_id: Mapped[int | None] = mapped_column(
        ForeignKey("failure_signatures.id", ondelete="SET NULL")
    )
    detected_at: Mapped[datetime]
