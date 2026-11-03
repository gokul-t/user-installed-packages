"""Command-line interface.

Prints the packages the user explicitly installed, one name per line, or a
JSON object with the full detection result. Exit status 0 on success, 2 on
error (unsupported distro, missing tools, backend failure).
"""
import argparse
import json
import sys
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version

from user_installed_packages.core import BackendError, detect

PROG = "user-installed-packages"
FALLBACK_VERSION = "0.3.0"


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


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["report"]:
        from user_installed_packages.report import main as report_main

        return report_main(argv[1:])

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
