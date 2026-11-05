"""Command-line interface.

Prints the packages the user explicitly installed, one name per line, or a
JSON object with the full detection result. Exit status 0 on success, 2 on
error (unsupported distro, missing tools, backend failure).
"""
import argparse
import json
import os
import shlex
import sys
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version
from pathlib import Path

from user_installed_packages.core import BackendError, detect

PROG = "user-installed-packages"
FALLBACK_VERSION = "0.5.0"


def cli_version():
    try:
        return package_version(PROG)
    except PackageNotFoundError:
        return FALLBACK_VERSION


def build_parser():
    parser = argparse.ArgumentParser(
        prog=PROG,
        description=(
            "Print packages the user explicitly installed, excluding the OS "
            "image base and automatically installed updates."
        ),
    )
    parser.add_argument("--distro", choices=["auto", "dnf", "apt"], default="auto",
                        help="package backend to use (default: auto-detect)")
    parser.add_argument("--json", action="store_true",
                        help="emit a JSON object instead of one name per line")
    parser.add_argument("--version", action="version",
                        version=f"%(prog)s {cli_version()}")
    parser.epilog = (
        "Run 'user-installed-packages report --help' for package manifest reporting."
    )
    return parser


def build_schedule_parser():
    parser = argparse.ArgumentParser(
        prog="user-installed-packages schedule",
        description=(
            "Schedule or unschedule the package drift report to run automatically."
        ),
    )
    parser.add_argument("--manifest-dir", type=Path, default=Path("ansible/packages"),
                        help="directory containing package manifests (default: ./ansible/packages)")
    parser.add_argument("--output", type=Path,
                        help="output file for written report (default: print to stdout)")
    parser.add_argument("--no-flatpak", dest="flatpak", action="store_false",
                        help="disable Flatpak package checking")
    parser.add_argument("--no-snap", dest="snap", action="store_false",
                        help="disable Snap package checking")
    parser.add_argument("--skip", action="append", default=[],
                        help="package to ignore (repeatable)")
    parser.add_argument("--enable", action="store_true", default=True,
                        help="enable the scheduler (default)")
    parser.add_argument("--disable", action="store_true",
                        help="disable the scheduler")
    parser.add_argument("--schedule", default="weekly",
                        help="schedule expression (default: weekly; systemd calendar format)")
    parser.add_argument("--label", default="com.dotfiles.package-report",
                        help="label/identifier for the scheduled job")
    return parser


def schedule_main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    from user_installed_packages import report

    parser = build_schedule_parser()
    args = parser.parse_args(argv)

    # Determine enable/disable
    enabled = not args.disable

    # Build report command
    cmd = ["user-installed-packages", "report",
           "--manifest-dir", str(args.manifest_dir)]
    if args.output:
        cmd.extend(["--output", str(args.output)])
    if not args.flatpak:
        cmd.append("--no-flatpak")
    if not args.snap:
        cmd.append("--no-snap")
    for skip in args.skip:
        cmd.extend(["--skip", skip])

    # Set default output path for scheduled runs
    if enabled and not args.output:
        output_path = Path.home() / ".local" / "state" / "dotfiles" / "package-report.txt"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        cmd.extend(["--output", str(output_path)])

    try:
        from user_installed_packages import schedule_report
        from user_installed_packages.scheduler import detect_scheduler

        # Build environment for the command
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin")}

        result = schedule_report(
            command=cmd,
            environment=env,
            enabled=enabled,
            on_calendar=args.schedule,
            label=args.label,
        )

        if result:
            scheduler_type = detect_scheduler()
            if enabled:
                print(f"Package drift report scheduled via {scheduler_type}", file=sys.stderr)
            else:
                print(f"Package drift report scheduler disabled ({scheduler_type})", file=sys.stderr)
        else:
            print(f"Failed to {'enable' if enabled else 'disable'} scheduler", file=sys.stderr)
            return 2
    except Exception as error:
        print(f"Schedule error: {error}", file=sys.stderr)
        return 2

    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        args = build_parser().parse_args([])
        try:
            result = detect()
        except BackendError as error:
            print(f"{PROG}: error: {error}", file=sys.stderr)
            return 2
        for name in result.packages:
            print(name)
        for warning in result.warnings:
            print(f"{PROG}: warning: {warning}", file=sys.stderr)
        return 0

    if argv[0] == "report":
        from user_installed_packages.report import main as report_main
        return report_main(argv[1:])

    if argv[0] == "schedule":
        return schedule_main(argv[1:])

    args = build_parser().parse_args(argv)
    try:
        result = detect(backend=args.distro)
    except BackendError as error:
        print(f"{PROG}: error: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        for name in result.packages:
            print(name)
    for warning in result.warnings:
        print(f"{PROG}: warning: {warning}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
