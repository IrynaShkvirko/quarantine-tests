"""create reporting schema

Grafana reads only the reporting.* views (architecture §12). Local Postgres already gets the
schema and the grafana_ro grants from docker/postgres/init.sh; CI and real deployments don't run
that script, so the schema has to come from the migrations too.

Revision ID: cb650922192f
Revises:
Create Date: 2026-11-22 14:46:26.710721
"""

from collections.abc import Sequence

from alembic import op

revision: str = "cb650922192f"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS reporting")


def downgrade() -> None:
    # Deliberately keeps the schema: on local databases init.sh created it with the grafana_ro
    # default privileges, and dropping it would silently lose those grants. upgrade() is
    # idempotent, so upgrading again after this downgrade works.
    pass
