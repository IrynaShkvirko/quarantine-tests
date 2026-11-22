"""Pydantic models for the five config files (architecture.md §5, §4.2, §13).

These models are the single source of truth: the loader, the bot PR check and the committed
JSON Schemas in ``config-example/schemas/`` all derive from them.
"""

import re
from collections import Counter
from collections.abc import Iterable
from datetime import date
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
)


class Reason(StrEnum):
    TIMING = "timing"
    ORDER_DEPENDENCY = "order_dependency"
    CONCURRENCY = "concurrency"
    EXTERNAL_DEPENDENCY = "external_dependency"
    TEST_DATA_ENV = "test_data_env"
    NONDETERMINISM = "nondeterminism"
    CI_INFRA = "ci_infra"
    PRODUCT_BUG = "product_bug"
    UNTRIAGED = "untriaged"


class Level(StrEnum):
    UNIT = "unit"
    INTEGRATION = "integration"
    API = "api"
    E2E = "e2e"


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


TEST_ID_PATTERN = r"^(pytest|playwright|jest)::[^:]+::.+$"
NonEmpty = Annotated[str, StringConstraints(min_length=1)]
TestId = Annotated[str, StringConstraints(pattern=TEST_ID_PATTERN)]
JiraKey = Annotated[str, StringConstraints(pattern=r"^[A-Z][A-Z0-9]+-\d+$")]
JiraProjectKey = Annotated[str, StringConstraints(pattern=r"^[A-Z][A-Z0-9]+$")]
Ratio = Annotated[float, Field(gt=0, le=1)]
Days = Annotated[int, Field(ge=1, strict=True)]
Count = Annotated[int, Field(ge=1, strict=True)]


def _check_regex(value: str) -> str:
    try:
        re.compile(value)
    except re.error as exc:
        raise ValueError(f"invalid regex {value!r}: {exc}") from exc
    return value


def _check_glob(value: str) -> str:
    # shortcut: structural check only (fnmatch never rejects a pattern); tighten if a matcher
    # ever disagrees with what we accept here.
    if not value or value.startswith("/") or value.count("[") != value.count("]"):
        raise ValueError(f"invalid glob {value!r}")
    return value


Regex = Annotated[str, StringConstraints(min_length=1), AfterValidator(_check_regex)]
Glob = Annotated[str, StringConstraints(min_length=1), AfterValidator(_check_glob)]


def _unique(values: Iterable[str], what: str) -> None:
    dupes = sorted(v for v, n in Counter(values).items() if n > 1)
    if dupes:
        raise ValueError(f"duplicate {what}: {', '.join(dupes)}")


# --- teams.yaml (§5.1) ---------------------------------------------------------------------


class Jira(_Model):
    project_key: JiraProjectKey
    component: NonEmpty


class Slack(_Model):
    channel: NonEmpty
    lead_user_id: NonEmpty


class ProductArea(_Model):
    name: NonEmpty
    paths: dict[NonEmpty, list[Glob]]


class Team(_Model):
    slug: NonEmpty
    github_team: NonEmpty
    jira: Jira
    slack: Slack
    # The `unowned` team in §5.1 has no lead and no product areas.
    lead_jira_account_id: NonEmpty | None = None
    product_areas: list[ProductArea] = Field(default_factory=list)


class PathRule(_Model):
    glob: Glob
    level: Level


class JobRule(_Model):
    pattern: Regex
    level: Level


class Levels(_Model):
    path_rules: list[PathRule] = Field(default_factory=list)
    job_rules: list[JobRule] = Field(default_factory=list)


class VerificationRepetitions(_Model):
    unit: Count = 50
    api: Count = 50
    integration: Count = 25
    e2e: Count = 10
    unclassified: Count = 25  # D37


class MassFailure(_Model):
    ratio: Ratio = 0.20
    min_tests: Count = 50
    single_fingerprint_tests: Count = 25


class NightlyQuarantineJob(_Model):
    budget_minutes: Count = 60
    shards: Count = 4
    monitoring_repetitions: Count = 3


class Defaults(_Model):
    reruns: Annotated[int, Field(ge=0, strict=True)] = 2
    flakiness_threshold: Ratio = 0.05
    min_flaky_occurrences: Count = 2
    rate_method: Literal["simple", "wilson"] = "simple"
    window_days: Days = 14
    window_min_executions: Count = 30
    team_cap: Ratio = 0.05
    team_cap_min_tests: Count = 1  # D38
    verification_repetitions: VerificationRepetitions = VerificationRepetitions()
    probation_days: Days = 7
    sla_days: Days = 4
    sla_calendar: Literal["calendar", "business"] = "calendar"
    max_quarantine_days: Days = 30
    fix_extension_days: Days = 14
    mass_failure: MassFailure = MassFailure()
    orphan_days: Days = 7
    inventory_stale_days: Days = 30
    nightly_quarantine_job: NightlyQuarantineJob = NightlyQuarantineJob()


class TeamsConfig(_Model):
    version: Literal[1]
    teams: list[Team]
    levels: Levels = Levels()
    defaults: Defaults = Defaults()

    @field_validator("teams")
    @classmethod
    def _teams(cls, teams: list[Team]) -> list[Team]:
        slugs = [t.slug for t in teams]
        _unique(slugs, "team slug")
        if slugs.count("unowned") != 1:
            raise ValueError("exactly one team must have the slug 'unowned' (D17)")
        return teams


# --- quarantine-policy.yaml (§5.2) ---------------------------------------------------------


class NeverQuarantine(_Model):
    paths: list[Glob] = Field(default_factory=list)
    tests: list[TestId] = Field(default_factory=list)
    markers: list[NonEmpty] = Field(default_factory=list)

    @field_validator("tests")
    @classmethod
    def _unique_tests(cls, tests: list[str]) -> list[str]:
        _unique(tests, "test id")
        return tests


class PolicyOverrides(_Model):
    """A subset of ``Defaults``. A nested group (e.g. ``mass_failure``) is replaced whole."""

    reruns: Annotated[int, Field(ge=0, strict=True)] | None = None
    flakiness_threshold: Ratio | None = None
    min_flaky_occurrences: Count | None = None
    rate_method: Literal["simple", "wilson"] | None = None
    window_days: Days | None = None
    window_min_executions: Count | None = None
    team_cap: Ratio | None = None
    team_cap_min_tests: Count | None = None
    verification_repetitions: VerificationRepetitions | None = None
    probation_days: Days | None = None
    sla_days: Days | None = None
    sla_calendar: Literal["calendar", "business"] | None = None
    max_quarantine_days: Days | None = None
    fix_extension_days: Days | None = None
    mass_failure: MassFailure | None = None
    orphan_days: Days | None = None
    inventory_stale_days: Days | None = None
    nightly_quarantine_job: NightlyQuarantineJob | None = None


class QuarantinePolicy(_Model):
    version: Literal[1]
    mode: Literal["shadow", "enforce"]
    never_quarantine: NeverQuarantine = NeverQuarantine()
    overrides: PolicyOverrides = PolicyOverrides()


# --- quarantine.yaml (§5.3) ----------------------------------------------------------------


class QuarantinedTest(_Model):
    id: TestId
    jira: JiraKey
    since: date
    reason_suggested: Reason


class QuarantineList(_Model):
    version: Literal[1]
    tests: list[QuarantinedTest]

    @field_validator("tests")
    @classmethod
    def _unique_ids(cls, tests: list[QuarantinedTest]) -> list[QuarantinedTest]:
        _unique((t.id for t in tests), "test id")
        return tests


# --- reason_rules.yaml (§4.2) and masking_rules.yaml (§13) ---------------------------------


class ReasonRule(_Model):
    reason: Reason
    exception_types: list[NonEmpty] = Field(default_factory=list)
    message_patterns: list[Regex] = Field(default_factory=list)


class ReasonRules(_Model):
    version: Literal[1]
    rules: list[ReasonRule]


class MaskingRule(_Model):
    name: NonEmpty
    pattern: Regex
    replacement_type: NonEmpty  # becomes `[MASKED:<replacement_type>]`


class MaskingRules(_Model):
    version: Literal[1]
    rules: list[MaskingRule]

    @field_validator("rules")
    @classmethod
    def _unique_names(cls, rules: list[MaskingRule]) -> list[MaskingRule]:
        _unique((r.name for r in rules), "rule name")
        return rules
