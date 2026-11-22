"""M0-09: schema v1 against the compose Postgres, never SQLite (partitions, partial indexes)."""

import json
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import psycopg
import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import select, text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from tests.conftest import migrate

from app.db import models as m
from app.db.base import Base, include_object

pytestmark = pytest.mark.integration

_FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "schema_v1.json").read_text())
# Fixed instant far from "now": lands in the default partition, so tests never read the clock.
_THEN = datetime(2024, 1, 15, 12, 0, tzinfo=UTC)
_UNIQUE_VIOLATION = "23505"


def _psycopg_url(url: str) -> str:
    return url.replace("+psycopg", "", 1)


def _columns(url: str) -> dict[str, set[str]]:
    with psycopg.connect(_psycopg_url(url)) as conn:
        rows = conn.execute(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = 'public'"
        ).fetchall()
    tables: dict[str, set[str]] = {}
    for table, column in rows:
        tables.setdefault(table, set()).add(column)
    return tables


def test_upgrade_creates_every_spec_table_and_downgrade_removes_them(
    scratch_database_url: str,
) -> None:
    migrate(scratch_database_url)
    created = _columns(scratch_database_url)
    for table, columns in _FIXTURE.items():
        assert created.get(table) == set(columns), table

    migrate(scratch_database_url, "base", downgrade=True)
    left = set(_columns(scratch_database_url)) - {"alembic_version"}
    assert left == set()
    with psycopg.connect(_psycopg_url(scratch_database_url)) as conn:
        leftovers = conn.execute(
            "SELECT count(*) FROM pg_proc WHERE proname = 'fq_ensure_partitions' "
            "UNION ALL SELECT count(*) FROM pg_type WHERE typname IN "
            "('outcome', 'evidence', 'job_kind', 'event')"
        ).fetchall()
    assert leftovers == [(0,), (0,)]


async def test_migrated_database_matches_the_models(test_database_url: str) -> None:
    engine = create_async_engine(test_database_url)

    def diff(connection: Connection) -> list[Any]:
        context = MigrationContext.configure(connection, opts={"include_object": include_object})
        return list(compare_metadata(context, Base.metadata))

    async with engine.connect() as connection:
        found = await connection.run_sync(diff)
    await engine.dispose()
    assert found == []


async def _seed_chain(session: AsyncSession) -> m.Repository:
    """One demo repository with a row in every table of its data chain."""
    repo = m.Repository(full_name=f"acme/{uuid4().hex}", ci_system="github_actions", is_demo=True)
    team = m.Team(slug=f"team-{uuid4().hex}")
    session.add_all([repo, team])
    await session.flush()
    area = m.ProductArea(team_id=team.id, name="checkout")
    test = m.Test(
        repository_id=repo.id, test_key="t::a", framework="pytest", name="a", team_id=team.id
    )
    run = m.CiRun(
        repository_id=repo.id,
        ci_system="github_actions",
        run_id="1",
        commit_sha="abc",
        event="push",
    )
    signature = m.FailureSignature(fingerprint=uuid4().hex)
    pr = m.BotPullRequest(repository_id=repo.id, url="https://example.test/pr/1", kind="add")
    session.add_all([area, test, run, signature, pr])
    await session.flush()
    record = m.QuarantineRecord(
        test_id=test.id, state="quarantined", decision="auto", add_pr_id=pr.id
    )
    session.add_all(
        [
            m.TestExecution(
                ci_run_id=run.id,
                test_id=test.id,
                job_kind="blocking",
                outcome="failed",
                failure_signature_id=signature.id,
                executed_at=_THEN,
            ),
            m.FlakyEvent(test_id=test.id, commit_sha="abc", evidence="rerun", detected_at=_THEN),
            m.ManualSkip(test_id=test.id, marker="skip", source="junit"),
            m.DailyTestStats(day=date(2024, 1, 15), test_id=test.id),
            m.RawUpload(
                upload_id=uuid4(),
                repository_id=repo.id,
                ci_system="github_actions",
                run_id="1",
                job_kind="blocking",
                framework="pytest",
                metadata_={},
            ),
            record,
        ]
    )
    await session.flush()
    session.add_all(
        [
            m.JiraIssue(
                issue_key=f"FQ-{uuid4().hex[:6]}",
                kind="flaky_test",
                quarantine_record_id=record.id,
                status="To Do",
                created_at=_THEN,
            ),
            m.QuarantineDecision(
                quarantine_record_id=record.id, decision="fix", decided_by="lead", decided_at=_THEN
            ),
            m.VerificationRun(
                quarantine_record_id=record.id,
                ci_run_id=run.id,
                commit_sha="abc",
                repetitions_planned=10,
            ),
        ]
    )
    await session.flush()
    return repo


async def test_deleting_a_repository_removes_every_row_of_its_chain(session: AsyncSession) -> None:
    repo = await _seed_chain(session)
    repo_tables = set(_FIXTURE) - {"teams", "product_areas", "failure_signatures"}
    for table in repo_tables - {"repositories"}:
        count = (await session.execute(text(f"SELECT count(*) FROM {table}"))).scalar_one()
        assert count >= 1, f"{table} was not seeded"

    await session.execute(text("DELETE FROM repositories WHERE id = :id"), {"id": repo.id})

    for table in sorted(repo_tables):
        count = (await session.execute(text(f"SELECT count(*) FROM {table}"))).scalar_one()
        assert count == 0, table


async def test_duplicate_test_key_in_one_repository_is_rejected(session: AsyncSession) -> None:
    repo = m.Repository(full_name=f"acme/{uuid4().hex}", ci_system="jenkins")
    session.add(repo)
    await session.flush()
    session.add(m.Test(repository_id=repo.id, test_key="k", framework="jest", name="k"))
    await session.flush()

    with pytest.raises(IntegrityError) as raised:
        async with session.begin_nested():
            session.add(m.Test(repository_id=repo.id, test_key="k", framework="jest", name="k"))
            await session.flush()
    assert raised.value.orig.sqlstate == _UNIQUE_VIOLATION  # type: ignore[union-attr]


async def test_duplicate_ingestion_idempotency_key_is_rejected(session: AsyncSession) -> None:
    repo = m.Repository(full_name=f"acme/{uuid4().hex}", ci_system="jenkins")
    session.add(repo)
    await session.flush()

    def upload() -> m.RawUpload:
        return m.RawUpload(
            upload_id=uuid4(),
            repository_id=repo.id,
            ci_system="jenkins",
            run_id="7",
            job_kind="blocking",
            framework="pytest",
            metadata_={},
        )

    session.add(upload())
    await session.flush()
    with pytest.raises(IntegrityError) as raised:
        async with session.begin_nested():
            session.add(upload())
            await session.flush()
    assert raised.value.orig.sqlstate == _UNIQUE_VIOLATION  # type: ignore[union-attr]


async def test_duplicate_flaky_event_without_environment_is_rejected(
    session: AsyncSession,
) -> None:
    repo = m.Repository(full_name=f"acme/{uuid4().hex}", ci_system="jenkins")
    session.add(repo)
    await session.flush()
    test = m.Test(repository_id=repo.id, test_key="k", framework="jest", name="k")
    session.add(test)
    await session.flush()

    def event() -> m.FlakyEvent:
        return m.FlakyEvent(test_id=test.id, commit_sha="abc", evidence="rerun", detected_at=_THEN)

    session.add(event())
    await session.flush()
    with pytest.raises(IntegrityError) as raised:
        async with session.begin_nested():
            session.add(event())
            await session.flush()
    assert raised.value.orig.sqlstate == _UNIQUE_VIOLATION  # type: ignore[union-attr]


_PARTITIONS = """
SELECT count(*) FROM pg_inherits i JOIN pg_class c ON c.oid = i.inhrelid
WHERE i.inhparent = 'test_executions'::regclass AND c.relname <> 'test_executions_default'
"""
_MONTH_PARTITIONS_EXIST = """
SELECT count(*) FROM generate_series(0, :n) AS i
WHERE to_regclass('test_executions_p'
    || to_char((now() AT TIME ZONE 'UTC') + make_interval(months => i), 'YYYYMM')) IS NOT NULL
"""


async def test_ensure_partitions_is_idempotent_and_fills_gaps(session: AsyncSession) -> None:
    # now() is fixed for the transaction, so every month below is computed from one instant; the
    # first call covers a run that crossed into a new month after the migration ran.
    await session.execute(text("SELECT fq_ensure_partitions(2)"))
    assert (await session.execute(text(_MONTH_PARTITIONS_EXIST), {"n": 3})).scalar_one() == 3

    await session.execute(text("SELECT fq_ensure_partitions(3)"))
    assert (await session.execute(text(_MONTH_PARTITIONS_EXIST), {"n": 3})).scalar_one() == 4
    before = (await session.execute(text(_PARTITIONS))).scalar_one()
    await session.execute(text("SELECT fq_ensure_partitions(3)"))
    assert (await session.execute(text(_PARTITIONS))).scalar_one() == before

    # A missing month in the middle comes back. Dropping the next month's partition is safe: empty.
    await session.execute(
        text(
            "DO $$ BEGIN EXECUTE format('DROP TABLE %I', 'test_executions_p' || to_char("
            "(now() AT TIME ZONE 'UTC') + interval '1 month', 'YYYYMM')); END $$"
        )
    )
    assert (await session.execute(text(_MONTH_PARTITIONS_EXIST), {"n": 3})).scalar_one() == 3
    await session.execute(text("SELECT fq_ensure_partitions(3)"))
    assert (await session.execute(text(_MONTH_PARTITIONS_EXIST), {"n": 3})).scalar_one() == 4


async def test_ensure_partitions_moves_waiting_rows_out_of_the_default_partition(
    session: AsyncSession,
) -> None:
    await _seed_chain(session)
    # A row dated 5 months ahead has no partition yet, so it sits in the default one.
    await session.execute(
        text(
            "UPDATE test_executions SET executed_at = "
            "date_trunc('month', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC' "
            "+ interval '5 months 1 day'"
        )
    )

    await session.execute(text("SELECT fq_ensure_partitions(5)"))

    where, expected = (
        await session.execute(
            text(
                "SELECT tableoid::regclass::text, 'test_executions_p' || "
                "to_char((now() AT TIME ZONE 'UTC') + interval '5 months', 'YYYYMM') "
                "FROM test_executions"
            )
        )
    ).one()
    assert where == expected


async def test_grafana_role_can_read_the_reporting_schema_only(session: AsyncSession) -> None:
    role = "SELECT EXISTS (SELECT FROM pg_roles WHERE rolname = 'grafana_ro')"
    if not (await session.execute(text(role))).scalar_one():
        pytest.skip("grafana_ro exists only on the compose Postgres (docker/postgres/init.sh)")
    # init.sh grants nothing on fq_test, so these privileges come from the migration. A table made
    # later (each dashboard task's view) must be readable through the default privileges.
    await session.execute(text("CREATE TABLE reporting.v_probe (x int)"))
    allowed = (
        await session.execute(
            text(
                "SELECT has_schema_privilege('grafana_ro', 'reporting', 'USAGE'), "
                "has_table_privilege('grafana_ro', 'reporting.v_probe', 'SELECT'), "
                "has_table_privilege('grafana_ro', 'public.tests', 'SELECT')"
            )
        )
    ).one()
    assert tuple(allowed) == (True, True, False)


async def test_rows_outside_the_monthly_partitions_go_to_the_default_partition(
    session: AsyncSession,
) -> None:
    await _seed_chain(session)
    where = (
        await session.execute(select(text("tableoid::regclass::text")).select_from(m.TestExecution))
    ).scalar_one()
    assert where == "test_executions_default"


# Detection queries from the task (M2 will run these) and the index each must use.
_EXPLAIN_CASES = [
    pytest.param(
        "SELECT id FROM test_executions WHERE test_id = :test_id "
        "AND executed_at >= '2023-12-01' AND executed_at < '2024-02-01' ORDER BY executed_at",
        "test_id_executed_at",
        id="executions-by-test",
    ),
    pytest.param(
        "SELECT id FROM ci_runs WHERE repository_id = :repo_id AND commit_sha = :sha "
        "AND environment = 'staging'",
        "ix_ci_runs_repository_id_commit_sha_environment",
        id="cross-run-evidence",
    ),
    pytest.param(
        "SELECT id FROM quarantine_records WHERE test_id = :test_id AND exited_at IS NULL",
        "ix_quarantine_records_test_id_open",
        id="open-quarantine-record",
    ),
]


@pytest.fixture
async def seeded(session: AsyncSession) -> AsyncIterator[dict[str, object]]:
    """A few thousand rows, then ANALYZE, so the planner has real statistics."""
    repo = m.Repository(full_name=f"acme/{uuid4().hex}", ci_system="github_actions")
    session.add(repo)
    await session.flush()
    await session.execute(
        text(
            "INSERT INTO tests (repository_id, test_key, framework, name) "
            "SELECT :r, 'k' || g, 'pytest', 'n' || g FROM generate_series(1, 500) g"
        ),
        {"r": repo.id},
    )
    await session.execute(
        text(
            "INSERT INTO ci_runs "
            "(repository_id, ci_system, run_id, commit_sha, event, environment) "
            "SELECT :r, 'github_actions', g, 'sha' || g, 'push', 'staging' "
            "FROM generate_series(1, 1000) g"
        ),
        {"r": repo.id},
    )
    await session.execute(
        text(
            "INSERT INTO test_executions "
            "(ci_run_id, test_id, job_kind, outcome, executed_at) "
            "SELECT r.id, t.id, 'blocking', 'passed', "
            "       '2024-01-01'::timestamptz + (r.id % 28) * interval '1 day' "
            "FROM (SELECT id FROM ci_runs WHERE repository_id = :r) r "
            "CROSS JOIN LATERAL (SELECT id FROM tests WHERE repository_id = :r "
            "                    ORDER BY id OFFSET (r.id * 7) % 495 LIMIT 5) t"
        ),
        {"r": repo.id},
    )
    first_test = (
        await session.execute(
            text("SELECT min(id) FROM tests WHERE repository_id = :r"), {"r": repo.id}
        )
    ).scalar_one()
    await session.execute(
        text(
            "INSERT INTO quarantine_records (test_id, state, decision, exited_at) "
            "SELECT id, 'quarantined', 'auto', CASE WHEN id % 10 = 0 THEN NULL ELSE now() END "
            "FROM tests WHERE repository_id = :r"
        ),
        {"r": repo.id},
    )
    for table in ("tests", "ci_runs", "test_executions", "quarantine_records"):
        await session.execute(text(f"ANALYZE {table}"))
    yield {"repo_id": repo.id, "test_id": first_test, "sha": "sha1"}


@pytest.mark.parametrize(("query", "index_fragment"), _EXPLAIN_CASES)
async def test_hot_queries_use_their_index(
    session: AsyncSession, seeded: dict[str, object], query: str, index_fragment: str
) -> None:
    # With seq scans off the planner can only pick an index that actually matches the query, so a
    # missing or wrongly ordered index fails here even though 5k rows would favour a seq scan.
    await session.execute(text("SET LOCAL enable_seqscan = off"))
    params = {k: v for k, v in seeded.items() if f":{k}" in query}
    plan = "\n".join(
        row[0] for row in (await session.execute(text(f"EXPLAIN {query}"), params)).all()
    )
    assert "Seq Scan" not in plan, plan
    assert index_fragment in plan, plan
