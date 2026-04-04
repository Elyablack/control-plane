#!/usr/bin/env python3
from __future__ import annotations

import argparse

from mac_memory_guard.app import run_worker_cycle
from mac_memory_guard.logging_utils import log_line


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="mac memory worker agent")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.dry_run:
        log_line("worker dry-run: skipping task polling")
        return 0

    return run_worker_cycle()


if __name__ == "__main__":
    raise SystemExit(main())
