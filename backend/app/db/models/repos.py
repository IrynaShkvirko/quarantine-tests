from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    SmallInteger,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, id_pk, one_of
from app.db.models._enums import JOB_KIND


class Repository(Base):
    __tablename__ = "repositories"
    __table_args__ = (
        one_of("ci_system", ("jenkins", "github_actions"), "ci_system"),
        one_of("mode", ("shadow", "enforce"), "mode"),
    )

    id: Mapped[int] = id_pk()
    full_name: Mapped[str] = mapped_column(Text, unique=True)
    ci_system: Mapped[str] = mapped_column(Text)
    default_branch: Mapped[str] = mapped_column(Text, server_default="main")
    is_monorepo: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    mode: Mapped[str] = mapped_column(Text, server_default="shadow")
    is_demo: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    token_hash: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[int] = id_pk()
    slug: Mapped[str] = mapped_column(Text, unique=True)
    github_team: Mapped[str | None] = mapped_column(Text)
    jira_project_key: Mapped[str | None] = mapped_column(Text)
    jira_component: Mapped[str | None] = mapped_column(Text)
    slack_channel: Mapped[str | None] = mapped_column(Text)
    lead_slack_id: Mapped[str | None] = mapped_column(Text)
    lead_jira_account_id: Mapped[str | None] = mapped_column(Text)


class ProductArea(Base):
    __tablename__ = "product_areas"

    id: Mapped[int] = id_pk()
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(Text)


class BotPullRequest(Base):
    __tablename__ = "bot_pull_requests"
    __table_args__ = (
        one_of("kind", ("add", "remove", "rename", "orphan_cleanup"), "kind"),
        one_of("status", ("open", "merged", "closed"), "status"),
    )

    id: Mapped[int] = id_pk()
    repository_id: Mapped[int] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), index=True
    )
    url: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(Text)
    auto_merge: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    head_sha: Mapped[str | None] = mapped_column(Text)  # merge only at this SHA
    status: Mapped[str] = mapped_column(Text, server_default="open")
    merged_at: Mapped[datetime | None]


class RawUpload(Base):
    __tablename__ = "raw_uploads"
    __table_args__ = (
        one_of("status", ("queued", "parsed", "failed"), "status"),
        # M0-08 idempotency key: a second upload with the same key is the same upload.
        Index(
            "uq_raw_uploads_idempotency_key",
            "repository_id", "ci_system", "run_id", "run_attempt", "shard", "job_kind", "framework",
            unique=True,
        ),
    )  # fmt: skip

    id: Mapped[int] = id_pk()
    upload_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), unique=True)
    repository_id: Mapped[int] = mapped_column(ForeignKey("repositories.id", ondelete="CASCADE"))
    # Idempotency key columns. shard is '' (not NULL) when unsharded, so the unique index applies.
    ci_system: Mapped[str] = mapped_column(Text)
    run_id: Mapped[str] = mapped_column(Text)
    run_attempt: Mapped[int] = mapped_column(SmallInteger, server_default=text("1"))
    shard: Mapped[str] = mapped_column(Text, server_default="")
    job_kind: Mapped[str] = mapped_column(JOB_KIND)
    framework: Mapped[str] = mapped_column(Text)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB)
    payload: Mapped[bytes | None] = mapped_column(
        LargeBinary
    )  # masked; null if failed before masking
    status: Mapped[str] = mapped_column(Text, server_default="queued")
    error_summary: Mapped[str | None] = mapped_column(Text)
    payload_sha256: Mapped[str | None] = mapped_column(Text)
    duplicate_mismatches: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    last_duplicate_mismatch_at: Mapped[datetime | None]
    received_at: Mapped[datetime] = mapped_column(server_default=func.now())
