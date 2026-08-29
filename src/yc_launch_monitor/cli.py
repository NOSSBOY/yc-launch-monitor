"""Command-line interface for YC Launch Monitor."""

from __future__ import annotations

import argparse
import sys

from yc_launch_monitor.config import load_settings
from yc_launch_monitor.logging_config import configure_logging
from yc_launch_monitor.monitors.yc_directory.monitor import YCDirectoryMonitor
from yc_launch_monitor.monitors.yc_speedrun.monitor import YCSpeedrunMonitor


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

    return 1


if __name__ == "__main__":
    sys.exit(main())
