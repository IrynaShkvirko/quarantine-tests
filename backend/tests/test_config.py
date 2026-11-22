import io
import json
import re
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import BaseModel
from ruamel.yaml import YAML
from typer.testing import CliRunner

from app.admin.cli import app
from app.config.loader import (
    ConfigError,
    load_config,
    load_masking_rules,
    load_policy,
    load_quarantine,
    load_reason_rules,
    load_teams,
    merge_policy,
    model_for,
)
from app.config.models import (
    Defaults,
    Level,
    MaskingRules,
    PolicyOverrides,
    QuarantineList,
    QuarantinePolicy,
    Reason,
    ReasonRules,
    TeamsConfig,
)


def _round_trip(data: object) -> object:
    buf = io.StringIO()
    yaml = YAML(typ="safe")
    # Block style, like real config files: ruamel's flow-style emitter writes `{a: :0}`,
    # which it can't read back (found by hypothesis).
    yaml.default_flow_style = False
    yaml.dump(data, buf)
    return yaml.load(buf.getvalue())


EXAMPLES = Path(__file__).parents[2] / "config-example"
VALID = sorted(EXAMPLES.glob("*.yaml"))
INVALID = sorted((EXAMPLES / "invalid").glob("*.yaml"))


@pytest.mark.parametrize("path", VALID, ids=lambda p: p.name)
def test_valid_examples_load(path: Path) -> None:
    load_config(path, model_for(path))


@pytest.mark.parametrize("path", INVALID, ids=lambda p: p.name)
def test_invalid_examples_name_file_line_and_field(path: Path) -> None:
    with pytest.raises(ConfigError) as exc:
        load_config(path, model_for(path))
    for problem in exc.value.problems:
        assert re.match(rf"{re.escape(str(path))}:[1-9]\d* \S+: .+", problem)


def test_error_points_at_the_offending_line() -> None:
    path = EXAMPLES / "invalid" / "quarantine.bad-jira-key.yaml"
    with pytest.raises(ConfigError, match=r"bad-jira-key.yaml:5 tests\.0\.jira:"):
        load_quarantine(path)


def test_syntax_error_is_a_config_error(tmp_path: Path) -> None:
    bad = tmp_path / "teams.yaml"
    bad.write_text("version: [1\n")
    with pytest.raises(ConfigError, match=r"teams.yaml:\d+ file: cannot read YAML"):
        load_teams(bad)


def test_missing_file_is_a_config_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="cannot read YAML"):
        load_teams(tmp_path / "teams.yaml")


def test_unknown_file_type_is_rejected() -> None:
    with pytest.raises(ConfigError, match="unknown config file type"):
        model_for(Path("other.yaml"))


def test_typed_loaders() -> None:
    assert load_teams(EXAMPLES / "teams.yaml").teams[0].slug == "payments"
    assert load_policy(EXAMPLES / "quarantine-policy.yaml").mode == "shadow"
    assert load_reason_rules(EXAMPLES / "reason_rules.yaml").rules
    assert load_masking_rules(EXAMPLES / "masking_rules.yaml").rules


def test_merge_policy_without_overrides_returns_defaults() -> None:
    assert merge_policy(Defaults(), PolicyOverrides()) == Defaults()


def test_merge_policy_applies_override() -> None:
    merged = merge_policy(Defaults(), PolicyOverrides(team_cap=0.1))
    assert merged.team_cap == 0.1
    assert merged.flakiness_threshold == Defaults().flakiness_threshold


def test_defaults_match_the_example_file() -> None:
    assert load_teams(EXAMPLES / "teams.yaml").defaults == Defaults()


_ids = st.builds(
    lambda fw, path, name: f"{fw}::{path}::{name}",
    st.sampled_from(["pytest", "playwright", "jest"]),
    st.from_regex(r"[a-z][a-z0-9_/]{0,20}\.py", fullmatch=True),
    st.from_regex(r"[A-Za-z][A-Za-z0-9_\[\] >-]{0,20}", fullmatch=True),
)
_entries = st.fixed_dictionaries(
    {
        "id": _ids,
        "jira": st.from_regex(r"[A-Z][A-Z0-9]{1,5}-[1-9][0-9]{0,4}", fullmatch=True),
        "since": st.dates().map(str),
        "reason_suggested": st.sampled_from([r.value for r in Reason]),
    }
)


_name = st.from_regex(r"[a-z][a-z0-9-]{0,10}", fullmatch=True)
_text = st.text(
    st.characters(codec="utf-8", exclude_categories=("Cs", "Cc")), min_size=1, max_size=20
)
_glob = st.sampled_from(["e2e/**", "**/tests/unit/**", "src/*.py", "tests/[ab]*/**"])
_regex = st.sampled_from(["timeout", r"\d+ms", "ECONN(RESET|REFUSED)", "waiting for .*"])
_ratio = st.floats(min_value=0.001, max_value=1, allow_nan=False)
_days = st.integers(min_value=1, max_value=365)
_defaults = st.fixed_dictionaries(
    {},
    optional={
        "reruns": st.integers(min_value=0, max_value=5),
        "flakiness_threshold": _ratio,
        "team_cap": _ratio,
        "rate_method": st.sampled_from(["simple", "wilson"]),
        "sla_days": _days,
        "sla_calendar": st.sampled_from(["calendar", "business"]),
        "mass_failure": st.fixed_dictionaries({"ratio": _ratio, "min_tests": _days}),
    },
)
_team = st.fixed_dictionaries(
    {
        "github_team": _text,
        "jira": st.fixed_dictionaries(
            {
                "project_key": st.from_regex(r"[A-Z][A-Z0-9]{1,5}", fullmatch=True),
                "component": _text,
            }
        ),
        "slack": st.fixed_dictionaries({"channel": _text, "lead_user_id": _text}),
    },
    optional={
        "lead_jira_account_id": _text,
        "product_areas": st.lists(
            st.fixed_dictionaries(
                {"name": _text, "paths": st.dictionaries(_name, st.lists(_glob), max_size=2)}
            ),
            max_size=2,
        ),
    },
)
_levels = st.sampled_from([lvl.value for lvl in Level])


# Round-trips test correctness, not speed; the 200 ms deadline fails randomly under coverage.
_no_deadline = settings(deadline=None)


def _assert_round_trips(model: BaseModel) -> None:
    assert type(model).model_validate(_round_trip(model.model_dump(mode="json"))) == model


@_no_deadline
@given(st.lists(_entries, max_size=5, unique_by=lambda e: e["id"]))
def test_quarantine_list_round_trips_through_yaml(entries: list[dict[str, str]]) -> None:
    _assert_round_trips(QuarantineList.model_validate({"version": 1, "tests": entries}))


@_no_deadline
@given(_defaults)
def test_defaults_round_trip_through_yaml(defaults: dict[str, object]) -> None:
    _assert_round_trips(Defaults.model_validate(defaults))


@_no_deadline
@given(
    st.lists(_name.filter(lambda s: s != "unowned"), max_size=3, unique=True),
    st.lists(_team, min_size=4, max_size=4),
    st.lists(st.fixed_dictionaries({"glob": _glob, "level": _levels}), max_size=3),
    st.lists(st.fixed_dictionaries({"pattern": _regex, "level": _levels}), max_size=3),
    _defaults,
)
def test_teams_config_round_trips_through_yaml(
    slugs: list[str],
    teams: list[dict[str, object]],
    path_rules: list[dict[str, str]],
    job_rules: list[dict[str, str]],
    defaults: dict[str, object],
) -> None:
    named = [{**t, "slug": s} for s, t in zip([*slugs, "unowned"], teams, strict=False)]
    data = {
        "version": 1,
        "teams": named,
        "levels": {"path_rules": path_rules, "job_rules": job_rules},
        "defaults": defaults,
    }
    _assert_round_trips(TeamsConfig.model_validate(data))


@_no_deadline
@given(
    st.sampled_from(["shadow", "enforce"]),
    st.lists(_glob, max_size=3),
    st.lists(_ids, max_size=3, unique=True),
    st.lists(_name, max_size=3),
    _defaults,
)
def test_quarantine_policy_round_trips_through_yaml(
    mode: str,
    paths: list[str],
    tests: list[str],
    markers: list[str],
    overrides: dict[str, object],
) -> None:
    data = {
        "version": 1,
        "mode": mode,
        "never_quarantine": {"paths": paths, "tests": tests, "markers": markers},
        "overrides": overrides,
    }
    _assert_round_trips(QuarantinePolicy.model_validate(data))


@_no_deadline
@given(
    st.lists(
        st.fixed_dictionaries(
            {
                "reason": st.sampled_from([r.value for r in Reason]),
                "exception_types": st.lists(_text, max_size=3),
                "message_patterns": st.lists(_regex, max_size=3),
            }
        ),
        max_size=4,
    )
)
def test_reason_rules_round_trip_through_yaml(rules: list[dict[str, object]]) -> None:
    _assert_round_trips(ReasonRules.model_validate({"version": 1, "rules": rules}))


@_no_deadline
@given(
    st.lists(
        st.fixed_dictionaries({"name": _name, "pattern": _regex, "replacement_type": _name}),
        max_size=4,
        unique_by=lambda r: r["name"],
    )
)
def test_masking_rules_round_trip_through_yaml(rules: list[dict[str, str]]) -> None:
    _assert_round_trips(MaskingRules.model_validate({"version": 1, "rules": rules}))


def test_export_schemas_writes_one_file_per_config(tmp_path: Path) -> None:
    result = CliRunner().invoke(app, ["export-schemas", "--out", str(tmp_path)])

    assert result.exit_code == 0
    assert {p.name for p in tmp_path.iterdir()} == {
        "teams.schema.json",
        "quarantine-policy.schema.json",
        "quarantine.schema.json",
        "reason_rules.schema.json",
        "masking_rules.schema.json",
    }
    assert json.loads((tmp_path / "teams.schema.json").read_text())["title"] == "TeamsConfig"


def test_validate_config_ok_and_failure() -> None:
    ok = CliRunner().invoke(app, ["validate-config", *map(str, VALID)])
    assert ok.exit_code == 0
    assert ok.stdout.strip() == "OK"

    bad = CliRunner().invoke(app, ["validate-config", *map(str, INVALID)])
    assert bad.exit_code == 1
    assert "teams.no-unowned.yaml:2 teams:" in bad.output


def test_merge_policy_replaces_a_nested_group_whole() -> None:
    defaults = Defaults.model_validate({"mass_failure": {"ratio": 0.3, "min_tests": 80}})
    overrides = PolicyOverrides.model_validate({"mass_failure": {"ratio": 0.5}})

    merged = merge_policy(defaults, overrides)

    assert merged.mass_failure.ratio == 0.5
    assert merged.mass_failure.min_tests == 50  # group replaced, not deep-merged


def test_policy_overrides_cover_every_default() -> None:
    assert PolicyOverrides.model_fields.keys() == Defaults.model_fields.keys()
