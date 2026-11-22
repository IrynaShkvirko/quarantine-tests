"""Declarative base. The naming convention keeps constraint names stable across Alembic runs."""

from datetime import datetime
from typing import Any, ClassVar

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Identity, MetaData
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    # Every datetime is timestamptz (architecture §10).
    type_annotation_map: ClassVar[dict[type, Any]] = {datetime: DateTime(timezone=True)}


def include_object(_obj: object, name: str | None, *_: object) -> bool:
    """Alembic autogenerate/compare filter: skip what isn't a model (the queue's objects, and the
    monthly partitions of test_executions with their child indexes)."""
    return not (name or "").startswith(("procrastinate_", "idx_procrastinate_", "test_executions_"))


def id_pk() -> Mapped[int]:
    return mapped_column(BigInteger, Identity(always=True), primary_key=True)


def one_of(column: str, values: tuple[str, ...], name: str) -> CheckConstraint:
    """Free-text column limited to a known set. A CHECK, not an enum, so a new state needs no
    enum migration. NULLs pass, as with any CHECK."""
    quoted = ", ".join(f"'{v}'" for v in values)
    return CheckConstraint(f"{column} IN ({quoted})", name=name)
