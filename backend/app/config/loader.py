"""Load and validate config files; every problem is reported as ``file:line field: message``."""

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from ruamel.yaml.error import YAMLError

from app.config.models import (
    Defaults,
    MaskingRules,
    PolicyOverrides,
    QuarantineList,
    QuarantinePolicy,
    ReasonRules,
    TeamsConfig,
)

# File stem (the part of the name before the first dot) -> model.
MODELS: dict[str, type[BaseModel]] = {
    "teams": TeamsConfig,
    "quarantine-policy": QuarantinePolicy,
    "quarantine": QuarantineList,
    "reason_rules": ReasonRules,
    "masking_rules": MaskingRules,
}


class ConfigError(Exception):
    def __init__(self, problems: list[str]) -> None:
        super().__init__("\n".join(problems))
        self.problems = problems


def model_for(path: Path) -> type[BaseModel]:
    stem = path.name.partition(".")[0]
    if stem not in MODELS:
        raise ConfigError([f"{path}:1 file: unknown config file type, expected {sorted(MODELS)}"])
    return MODELS[stem]


def _line(data: Any, loc: tuple[int | str, ...]) -> int:
    """Line of the deepest node on ``loc`` that exists in the YAML (1-based)."""
    line = 1
    for part in loc:
        if isinstance(data, CommentedMap) and part in data:
            line = data.lc.key(part)[0] + 1
        elif isinstance(data, CommentedSeq) and isinstance(part, int) and part < len(data):
            line = data.lc.item(part)[0] + 1
        else:
            break
        data = data[part]
    return line


def load_config[M: BaseModel](path: Path, model: type[M]) -> M:
    try:
        data = YAML(typ="rt").load(path.read_text(encoding="utf-8"))
    except (YAMLError, OSError, UnicodeDecodeError) as exc:
        mark = getattr(exc, "problem_mark", None)
        line = mark.line + 1 if mark else 1
        raise ConfigError([f"{path}:{line} file: cannot read YAML: {exc}"]) from exc
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        problems = []
        for e in exc.errors():
            field = ".".join(map(str, e["loc"])) or "file"
            problems.append(f"{path}:{_line(data, e['loc'])} {field}: {e['msg']}")
        raise ConfigError(problems) from exc


def load_teams(path: Path) -> TeamsConfig:
    return load_config(path, TeamsConfig)


def load_policy(path: Path) -> QuarantinePolicy:
    return load_config(path, QuarantinePolicy)


def load_quarantine(path: Path) -> QuarantineList:
    return load_config(path, QuarantineList)


def load_reason_rules(path: Path) -> ReasonRules:
    return load_config(path, ReasonRules)


def load_masking_rules(path: Path) -> MaskingRules:
    return load_config(path, MaskingRules)


def merge_policy(defaults: Defaults, overrides: PolicyOverrides) -> Defaults:
    """Settings for one repo: ``defaults`` with every override that is set applied on top."""
    merged = {**defaults.model_dump(), **overrides.model_dump(exclude_none=True)}
    return Defaults.model_validate(merged)
