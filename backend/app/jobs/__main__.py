import importlib
import sys

from app.jobs import JOBS


def main(argv: list[str]) -> int:
    if len(argv) != 1 or argv[0] not in JOBS:
        known = ", ".join(sorted(JOBS)) or "none yet"
        print(f"usage: python -m app.jobs <name>  (known jobs: {known})", file=sys.stderr)
        return 2
    module_path, _, func = JOBS[argv[0]].partition(":")
    getattr(importlib.import_module(module_path), func)()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
