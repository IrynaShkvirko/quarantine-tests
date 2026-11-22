# Database schema v1

Tables, keys and partition rules for the Postgres schema (M0-09). The design is `docs/architecture.md` §10; this page records what the migrations create.

## Tables

Generated from the models in `backend/app/db/models/` (regenerate when a model changes):

```bash
uv run --directory backend python -c "import app.db.models; from app.db.base import Base; [print(f'| \`{n}\` | ' + ', '.join(c.name for c in t.columns) + ' |') for n, t in sorted(Base.metadata.tables.items())]"
```

| Table | Columns |
|-------|---------|
| `bot_pull_requests` | id, repository_id, url, kind, auto_merge, head_sha, status, merged_at |
| `ci_runs` | id, repository_id, ci_system, run_id, pipeline, run_url, commit_sha, branch, event, environment, is_environmental, test_count, failed_count, started_at, finished_at |
| `daily_test_stats` | day, test_id, executions, failures, flaky_occurrences, rerun_seconds, red_builds_caused, flips |
| `failure_signatures` | id, fingerprint, exception_type, normalized_message, category, suggested_reason |
| `flaky_events` | id, test_id, commit_sha, environment, evidence, branch, failure_signature_id, detected_at |
| `jira_issues` | id, issue_key, kind, quarantine_record_id, failure_signature_id, related_issue_id, status, severity, due_date, reopen_count, overdue_notified_at, created_at, resolved_at |
| `manual_skips` | id, test_id, marker, reason, source, allow_ticket, first_seen_at, last_seen_at |
| `product_areas` | id, team_id, name |
| `quarantine_decisions` | id, quarantine_record_id, decision, decided_by, extension_until, decided_at |
| `quarantine_records` | id, test_id, state, decision, shadow_outcome, rate_at_entry, occurrences_at_entry, reason_suggested, reason_confirmed, fix_sha, add_pr_id, remove_pr_id, days_quarantined_total, entered_at, probation_until, exited_at |
| `raw_uploads` | id, upload_id, repository_id, ci_system, run_id, run_attempt, shard, job_kind, framework, metadata, payload, status, error_summary, payload_sha256, duplicate_mismatches, last_duplicate_mismatch_at, received_at |
| `repositories` | id, full_name, ci_system, default_branch, is_monorepo, mode, is_demo, token_hash, created_at |
| `teams` | id, slug, github_team, jira_project_key, jira_component, slack_channel, lead_slack_id, lead_jira_account_id |
| `test_executions` | id, ci_run_id, test_id, run_attempt, attempt, shard, job_kind, outcome, duration_ms, failure_signature_id, message_excerpt, was_quarantined, executed_at |
| `tests` | id, repository_id, test_key, framework, file_path, name, level, team_id, product_area_id, is_protected, state, renamed_to_id, cost_score, first_seen_at, last_seen_at |
| `verification_runs` | id, quarantine_record_id, ci_run_id, commit_sha, repetitions_planned, repetitions_run, passes, result |

`backend/tests/fixtures/schema_v1.json` is the hand-kept §10 list; a test fails when the models drift from it.

## Conventions

- Primary keys are `BIGINT GENERATED ALWAYS AS IDENTITY`; every timestamp is `timestamptz`.
- Postgres enums only for sets that never grow: `outcome`, `evidence`, `job_kind`, `event`. Every other fixed set (lifecycle `state`, `ci_system`, `mode`, ...) is `text` with a `CHECK`, so a new value needs no enum migration.
- Every foreign key in a repository's data chain is `ON DELETE CASCADE`, so deleting a repository removes all its rows (§15). Links to shared rows (`failure_signatures`, `teams`, `product_areas`, `bot_pull_requests`) use `SET NULL`.
- `raw_uploads` carries the ingestion idempotency key `(repository_id, ci_system, run_id, run_attempt, shard, job_kind, framework)` as a unique index. `shard` is `''`, not NULL, when unsharded. Likewise `environment` on `ci_runs` and `flaky_events` is `''` when unset, because NULLs never collide in a unique key or match `environment = :env`.

## `test_executions` partitions and retention

- Range-partitioned by month on `executed_at`; the primary key is `(id, executed_at)` because Postgres requires the partition key in it. Name pattern: `test_executions_pYYYYMM` (UTC months).
- Migration `0002_schema_v1` creates the parent, `test_executions_default` and the current month plus the next two.
- `fq_ensure_partitions(months_ahead int)` creates every missing month from the current one through `months_ahead` ahead. It is idempotent. The retention job (M6-04) calls it daily.
- Rows outside every monthly partition go to the default partition. When `fq_ensure_partitions` later creates their month, it moves those rows out of the default partition into the new one, in the same transaction.
- Retention (D31): partitions older than 90 days are dropped (M6-04). Every query on this table filters `executed_at`, or it scans every partition.

## Grafana

`grafana_ro` gets `USAGE` and `SELECT` on the `reporting` schema only. The schema is empty until each dashboard task adds its view (§10 lists them). The grant is skipped on databases where the role doesn't exist (CI).
