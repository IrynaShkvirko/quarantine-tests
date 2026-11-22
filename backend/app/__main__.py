"""``python -m app worker`` runs the Procrastinate worker."""

import sys

from app.logging import configure_logging
from app.settings import get_settings
from app.workers import queue


def main(argv: list[str]) -> int:
    if argv != ["worker"]:
        print("usage: python -m app worker", file=sys.stderr)
        return 2
    configure_logging(get_settings())
    queue.app.run_worker()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
