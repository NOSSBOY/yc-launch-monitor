"""Command-line interface for YC Launch Monitor."""

from __future__ import annotations

import argparse
import sys

from yc_launch_monitor.config import load_settings
from yc_launch_monitor.logging_config import configure_logging
from yc_launch_monitor.monitors.linkedin.monitor import LinkedInMonitor
from yc_launch_monitor.monitors.x.monitor import XMonitor
from yc_launch_monitor.monitors.yc_directory.monitor import YCDirectoryMonitor
from yc_launch_monitor.monitors.yc_speedrun.monitor import YCSpeedrunMonitor
from yc_launch_monitor.scheduler import MonitorScheduler


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="yc-launch-monitor",
        description="Monitor Y Combinator sources for founder and launch activity.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    yc_directory = subparsers.add_parser(
        "yc-directory",
        help="Run the YC Directory monitor (https://www.ycombinator.com/companies).",
    )
    yc_directory.add_argument(
        "action",
        choices=["run"],
        help="Action to perform.",
    )

    yc_speedrun = subparsers.add_parser(
        "yc-speedrun",
        help="Run the YC Speedrun monitor (https://www.ycombinator.com/speedrun).",
    )
    yc_speedrun.add_argument(
        "action",
        choices=["run"],
        help="Action to perform.",
    )

    x_parser = subparsers.add_parser(
        "x",
        help="Run the X (Twitter) monitor for early founder announcements.",
    )
    x_parser.add_argument(
        "action",
        choices=["run"],
        help="Action to perform.",
    )

    linkedin_parser = subparsers.add_parser(
        "linkedin",
        help="Run the LinkedIn monitor for founder announcements and launch posts.",
    )
    linkedin_parser.add_argument(
        "action",
        choices=["run"],
        help="Action to perform.",
    )

    scheduler_parser = subparsers.add_parser(
        "scheduler",
        help="Run all monitors continuously on a recurring schedule.",
    )
    scheduler_parser.add_argument(
        "action",
        nargs="?",
        choices=["run"],
        default="run",
        help="Action to perform (default: run).",
    )
    scheduler_parser.add_argument(
        "--interval",
        type=int,
        default=None,
        help="Override interval between cycles in seconds.",
    )
    scheduler_parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single monitoring cycle across all sources and exit.",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = load_settings()
    configure_logging(settings.log_level)

    if args.command == "yc-directory" and args.action == "run":
        result = YCDirectoryMonitor(settings).run()
        print(
            "YC Directory monitor summary: "
            f"discovered={result.discovered} "
            f"new={result.new} "
            f"already_seen={result.already_seen} "
            f"failed={result.failed}"
        )
        return 0

    if args.command == "yc-speedrun" and args.action == "run":
        result = YCSpeedrunMonitor(settings).run()
        print(
            "YC Speedrun monitor summary: "
            f"discovered={result.discovered} "
            f"new={result.new} "
            f"already_seen={result.already_seen} "
            f"failed={result.failed}"
        )
        return 0

    if args.command == "x" and args.action == "run":
        try:
            result = XMonitor(settings).run()
            print(
                "X monitor summary: "
                f"discovered={result.discovered} "
                f"relevant_signals={result.relevant_signals} "
                f"early_signals={result.early_signals} "
                f"already_seen={result.already_seen} "
                f"failed={result.failed}"
            )
            return 0
        except Exception as exc:
            print(f"Error running X monitor: {exc}", file=sys.stderr)
            return 1

    if args.command == "linkedin" and args.action == "run":
        try:
            result = LinkedInMonitor(settings).run()
            print(
                "LinkedIn monitor summary: "
                f"discovered={result.discovered} "
                f"relevant_signals={result.relevant_signals} "
                f"early_signals={result.early_signals} "
                f"speedrun_signals={result.speedrun_signals} "
                f"confirmed_yc={result.confirmed_yc} "
                f"already_seen={result.already_seen} "
                f"failed={result.failed}"
            )
            return 0
        except Exception as exc:
            print(f"Error running LinkedIn monitor: {exc}", file=sys.stderr)
            return 1

    if args.command == "scheduler" and args.action == "run":
        scheduler = MonitorScheduler(settings)
        scheduler.start(
            interval_seconds=args.interval,
            max_cycles=1 if args.once else None,
        )
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
