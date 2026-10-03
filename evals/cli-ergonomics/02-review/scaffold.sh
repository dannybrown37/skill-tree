#!/usr/bin/env bash
# Three executable scripts plus a hook. sync-users and deploy carry the
# seeded violations; report is clean; notify_hook.py prompts unguarded but
# is a harness callback, not a CLI, so flagging it is a false positive.
set -euo pipefail

mkdir -p scripts

cat >scripts/sync-users <<'PY'
#!/usr/bin/env python3
import argparse
import sys


def main() -> int:
    parser = argparse.ArgumentParser(prog="sync-users")
    parser.add_argument("environment", choices=["dev", "staging", "prod"])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(f"syncing users to {args.environment} (dry run: {args.dry_run})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
PY

cat >scripts/deploy <<'PY'
#!/usr/bin/env python3
import argparse
import sys

VERSION = "2.1.0"


def main() -> int:
    parser = argparse.ArgumentParser(prog="deploy")
    parser.add_argument("--version", action="version", version=VERSION)
    parser.add_argument("--service")
    args = parser.parse_args()
    service = args.service or input("Service to deploy: ")
    confirm = input(f"Deploy {service}? [y/N] ")
    if confirm.lower() != "y":
        return 1
    print(f"deploying {service}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
PY

cat >scripts/report <<'PY'
#!/usr/bin/env python3
import argparse
import sys
import tomllib
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


def own_version() -> str:
    try:
        return version("opskit")
    except PackageNotFoundError:
        pass
    try:
        return tomllib.loads(PYPROJECT.read_text())["project"]["version"]
    except (OSError, KeyError, tomllib.TOMLDecodeError):
        return "unknown"


def main() -> int:
    parser = argparse.ArgumentParser(prog="report")
    parser.add_argument("--version", action="version", version=own_version())
    parser.add_argument("month", nargs="?")
    args = parser.parse_args()
    if args.month is None:
        parser.print_help()
        return 2
    print(f"report for {args.month}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
PY

cat >scripts/notify_hook.py <<'PY'
#!/usr/bin/env python3
import json
import sys

event = json.loads(input())
print(f"notified: {event.get('type', 'unknown')}", file=sys.stderr)
PY

chmod +x scripts/*

cat >pyproject.toml <<'TOML'
[project]
name = "opskit"
version = "2.1.0"
requires-python = ">=3.11"
TOML

cat >README.md <<'MD'
# opskit

Operator scripts. Run them from `scripts/`.
MD

git init -q -b main
git -c user.name=eval -c user.email=eval@example.invalid add -A
git -c user.name=eval -c user.email=eval@example.invalid commit -qm 'chore: init'
