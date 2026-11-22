"""Cron job entrypoints. Run one with ``python -m app.jobs <name>``."""

JOBS: dict[str, str] = {}  # job name -> dotted path of its ``main()``; filled in by later tasks
