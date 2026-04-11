#!/usr/bin/env python3
from __future__ import annotations

import argparse

from agents.mac_memory_guard.cycles import run_report_cycle, run_worker_cycle
from mac_memory_guard.collectors import collect_metrics
from mac_memory_guard.evaluate import evaluate, normalize_app_name
from mac_memory_guard.logging_utils import log_line


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="mac memory agent CLI")
    parser.add_argument("--mode", choices=["combined", "report", "worker"], default="combined")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-publish", action="store_true")
    parser.add_argument("--force-event", action="store_true")
    parser.add_argument("--print-stats", action="store_true")
    return parser.parse_args()


def print_stats() -> int:
    metrics = collect_metrics()
    evaluation = evaluate(metrics)
    top = metrics.top_processes[0] if metrics.top_processes else None
    top_name = normalize_app_name(top.command) if top else "none"
    top_rss_mb = f"{top.rss_mb:.0f}" if top else "n/a"

    print(f"status={evaluation.status}")
    print(f"reasons={', '.join(evaluation.reasons)}")
    print(f"memory_free_percent={metrics.memory_free_percent if metrics.memory_free_percent is not None else 'n/a'}")
    print(f"swap_used_mb={metrics.swap_used_mb if metrics.swap_used_mb is not None else 'n/a'}")
    print(f"uptime_days={metrics.uptime_days if metrics.uptime_days is not None else 'n/a'}")
    print(f"disk_used_percent={metrics.disk_used_percent if metrics.disk_used_percent is not None else 'n/a'}")
    print(f"top_app={top_name}")
    print(f"top_rss_mb={top_rss_mb}")
    print(f"timestamp_utc={metrics.timestamp_utc}")
    return 0


def main() -> int:
    args = parse_args()

    if args.print_stats:
        return print_stats()

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
