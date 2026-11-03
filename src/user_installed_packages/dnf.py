"""DNF/RPM backend: user-installed packages on Fedora and RHEL-likes.

The rpmdb only records the last install time, so an install-time window
misclassifies every base package that was later upgraded. dnf history keeps
the original transaction times, so the image base is detected from the
transactions that ran first (e.g. the image build). If history is unusable,
the install-time window is used as a fallback and reported as a warning.

Group installs recorded on image builds (e.g. kiwi) are indistinguishable
from packages the user requested; anything installed as a dependency, weak
dependency or group member is deliberately not reported.
"""
import re
from datetime import datetime

from user_installed_packages.core import (
    BASE_INSTALL_WINDOW_SECONDS,
    BackendError,
    Detection,
    lines,
    run,
)

# Installed automatically as versioned packages during system updates; never a
# manifest concern.
DNF_AUTO_PACKAGES = {
    "kernel", "kernel-core", "kernel-devel",
    "kernel-modules", "kernel-modules-core", "kernel-modules-extra",
}
RPM_ARCH_SUFFIX = re.compile(
    r"\.(x86_64|i386|i586|i686|aarch64|armhfp|riscv64|noarch|src|nosrc)$"
)
# dnf5 prints "94 cmd-line ... 2026-11-03 10:35:07"; dnf4 prints a pipe-separated
# table with minute precision: "     1 | --config ... | 2025-05-13 07:48 |".
HISTORY_LIST_ROW = re.compile(
    r"^\s*(\d+)\s.*?(\d{4}-\d{2}-\d{2} \d{2}:\d{2})(:\d{2})?\s"
)
HISTORY_INSTALL_ROW = re.compile(r"^\s+(?:Install|Reinstall)\s+(\S+)", re.M)


def rpm_package_name(token):
    """Strip the arch and version-release (-epoch included) from an NVRA."""
    token = RPM_ARCH_SUFFIX.sub("", token.strip())
    parts = token.rsplit("-", 2)
    return parts[0] if len(parts) == 3 else token


def dnf_history(runner):
    """Parse `dnf history list`; return [(timestamp, id)] sorted by time."""
    out = runner(["dnf", "history", "list"])
    stamps = {}
    for line in lines(out):
        match = HISTORY_LIST_ROW.match(line)
        if match:
            stamp = match.group(2) + (match.group(3) or ":00")
            parsed = datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S")
            stamps[int(match.group(1))] = parsed.timestamp()
    return sorted(((stamp, tid) for tid, stamp in stamps.items()))


def dnf_transaction_installs(runner, tid):
    out = runner(["dnf", "history", "info", str(tid)])
    return {rpm_package_name(m.group(1)) for m in HISTORY_INSTALL_ROW.finditer(out)}


def dnf_explicit_packages(runner):
    """Names requested by the user at the command line (reason 'User')."""
    out = runner(
        ["dnf", "repoquery", "--installed", "--qf", "%{name} %{reason}\n"]
    )
    explicit = set()
    for line in lines(out):
        name, sep, reason = line.partition(" ")
        # dnf5 reports "User", dnf4 reports "user"
        if sep and reason.strip().lower() == "user":
            explicit.add(name)
    return explicit


def dnf_base_packages(runner):
    """Return (image base package names, warnings)."""
    warnings = []
    try:
        transactions = dnf_history(runner)
    except BackendError:
        transactions = []
    if transactions:
        start = transactions[0][0]
        base = set()
        for stamp, tid in transactions:
            if stamp > start + BASE_INSTALL_WINDOW_SECONDS:
                break
            try:
                base |= dnf_transaction_installs(runner, tid)
            except BackendError:
                continue
        return base, warnings
    warnings.append(
        "dnf history is unavailable; fell back to the rpm INSTALLTIME window "
        "(may misclassify upgraded image packages as user-installed)"
    )
    times = {}
    for line in lines(runner(["rpm", "-qa", "--qf", "%{NAME} %{INSTALLTIME}\n"])):
        name, _, stamp = line.rpartition(" ")
        if stamp.isdigit():
            times[name] = min(int(stamp), times.get(name, int(stamp)))
    if not times:
        return set(), warnings
    cutoff = min(times.values()) + BASE_INSTALL_WINDOW_SECONDS
    return {name for name, stamp in times.items() if stamp <= cutoff}, warnings


def detect(runner=run):
    explicit = dnf_explicit_packages(runner)
    base, warnings = dnf_base_packages(runner)
    packages = sorted(explicit - base - DNF_AUTO_PACKAGES)
    return Detection(
        backend="dnf",
        packages=packages,
        image_packages=sorted(base),
        excluded_auto=sorted(DNF_AUTO_PACKAGES & explicit),
        warnings=warnings,
    )
