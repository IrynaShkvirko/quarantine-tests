"""The models must match the §10 table and column list kept in fixtures/schema_v1.json."""

import json
from pathlib import Path

import app.db.models  # noqa: F401  registers the tables
from app.db.base import Base

_FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "schema_v1.json").read_text())


def test_model_tables_and_columns_match_the_spec_fixture() -> None:
    actual = {name: [c.name for c in t.columns] for name, t in Base.metadata.tables.items()}
    assert {k: sorted(v) for k, v in actual.items()} == {k: sorted(v) for k, v in _FIXTURE.items()}
