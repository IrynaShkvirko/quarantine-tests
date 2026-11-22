"""The only Postgres enums: sets that are fixed by design (architecture §10, M0-09).

Everything else is text with a CHECK, so adding a state needs no enum migration.
"""

from sqlalchemy.dialects.postgresql import ENUM

# create_type=False: the migration creates/drops each type once (tables share them).
OUTCOME = ENUM("passed", "failed", "error", "skipped", name="outcome", create_type=False)
EVIDENCE = ENUM("rerun", "cross_run", name="evidence", create_type=False)
JOB_KIND = ENUM("blocking", "quarantine", "stress", name="job_kind", create_type=False)
EVENT = ENUM(
    "push", "pull_request", "nightly", "quarantine", "stress", name="event", create_type=False
)

ENUMS = (OUTCOME, EVIDENCE, JOB_KIND, EVENT)

# Lifecycle states (architecture §11), shared by tests.state and quarantine_records.state.
LIFECYCLE_STATES = (
    "healthy", "watching", "candidate", "protected_flaky", "needs_decision",
    "pending_quarantine", "quarantined", "decision_required", "product_bug",
    "verifying", "releasing", "probation", "orphaned", "deleted",
)  # fmt: skip
