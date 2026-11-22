from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Index, Numeric, Text, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, id_pk, one_of
from app.db.models._enums import LIFECYCLE_STATES


class Test(Base):
    __tablename__ = "tests"
    __test__ = False  # not a pytest class
    __table_args__ = (
        UniqueConstraint("repository_id", "test_key", name="uq_tests_repository_id_test_key"),
        one_of("framework", ("pytest", "playwright", "jest"), "framework"),
        one_of("level", ("unit", "integration", "api", "e2e", "unclassified"), "level"),
        one_of("state", LIFECYCLE_STATES, "state"),
        # inventory: SELECT ... FROM tests WHERE repository_id = :r ORDER BY last_seen_at DESC
        Index("ix_tests_repository_id_last_seen_at", "repository_id", "last_seen_at"),
        # inventory: SELECT ... FROM tests WHERE team_id = :t AND state = 'quarantined'
        Index("ix_tests_team_id_state", "team_id", "state"),
    )

    id: Mapped[int] = id_pk()
    repository_id: Mapped[int] = mapped_column(ForeignKey("repositories.id", ondelete="CASCADE"))
    test_key: Mapped[str] = mapped_column(Text)
    framework: Mapped[str] = mapped_column(Text)
    file_path: Mapped[str | None] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    level: Mapped[str] = mapped_column(Text, server_default="unclassified")
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id", ondelete="SET NULL"))
    product_area_id: Mapped[int | None] = mapped_column(
        ForeignKey("product_areas.id", ondelete="SET NULL")
    )
    is_protected: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    state: Mapped[str] = mapped_column(Text, server_default="healthy")
    renamed_to_id: Mapped[int | None] = mapped_column(
        ForeignKey("tests.id", ondelete="SET NULL"), index=True
    )
    cost_score: Mapped[Decimal | None] = mapped_column(Numeric)
    first_seen_at: Mapped[datetime] = mapped_column(server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(server_default=func.now())


class ManualSkip(Base):
    __tablename__ = "manual_skips"
    __table_args__ = (
        one_of("marker", ("skip", "xfail", "fixme", "it.skip"), "marker"),
        one_of("source", ("junit", "static_scan"), "source"),
    )

    id: Mapped[int] = id_pk()
    test_id: Mapped[int] = mapped_column(ForeignKey("tests.id", ondelete="CASCADE"), index=True)
    marker: Mapped[str] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text)
    allow_ticket: Mapped[str | None] = mapped_column(Text)  # fq-allow-skip key
    first_seen_at: Mapped[datetime] = mapped_column(server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(server_default=func.now())
