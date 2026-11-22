# config-example

Example `teams.yaml`, `quarantine-policy.yaml`, `quarantine.yaml`, `reason_rules.yaml`, `masking_rules.yaml`.

- `schemas/`: JSON Schemas generated from `backend/app/config/models.py` (`uv run fq-admin export-schemas`). Don't edit by hand; CI regenerates them and fails on a diff.
- `invalid/`: one broken file per validator, named `<type>.<defect>.yaml`. Used by the tests.
- Check a file: `uv run fq-admin validate-config <file>...` (type is taken from the name before the first dot).
