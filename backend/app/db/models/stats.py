from datetime import date

from sqlalchemy import BigInteger, ForeignKey, Index, Integer, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DailyTestStats(Base):
    __tablename__ = "daily_test_stats"
    # The PK leads with day, so deleting a test (cascade) needs its own test_id index.
    __table_args__ = (Index("ix_daily_test_stats_test_id", "test_id"),)

    day: Mapped[date] = mapped_column(primary_key=True)
    test_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tests.id", ondelete="CASCADE"), primary_key=True
    )
    executions: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    failures: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    flaky_occurrences: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    rerun_seconds: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    red_builds_caused: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    flips: Mapped[int] = mapped_column(
        Integer, server_default=text("0")
    )  # default-branch pass/fail changes
