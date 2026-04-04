#!/usr/bin/env python3
from __future__ import annotations

import argparse

from mac_memory_guard.app import run_report_cycle, run_worker_cycle
from mac_memory_guard.logging_utils import log_line


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="compat wrapper for mac memory agent")
    parser.add_argument("--mode", choices=["combined", "report", "worker"], default="combined")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-publish", action="store_true")
    parser.add_argument("--force-event", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.dry_run:
        log_line("dry-run: no publish, no event, no remote task execution")
        return 0

    if args.mode == "report":
        return run_report_cycle(
            publish_enabled=not args.no_publish,
            force_event=args.force_event,
        )

    if args.mode == "worker":
        return run_worker_cycle()

    run_report_cycle(
        publish_enabled=not args.no_publish,
        force_event=args.force_event,
    )
    return run_worker_cycle()


if __name__ == "__main__":
    raise SystemExit(main())
