"""APT/dpkg backend: user-installed packages on Debian and Ubuntu.

`apt-mark showmanual` lists packages it considers manually installed, but on
installer-built systems the base OS is marked manual as well. The installer
records the initial set in /var/log/installer/initial-status[.gz], which is
subtracted to recover what the user actually asked for.
"""
import gzip
import re

from user_installed_packages.core import (
    APT_INITIAL_STATUS,
    Detection,
    lines,
    run,
)

INITIAL_STATUS_PACKAGE = re.compile(r"^Package: (\S+)", re.M)


def strip_arch(name):
    """Strip the optional :arch qualifier from a dpkg package name."""
    return name.split(":", 1)[0]


def dpkg_installed(runner):
    installed = set()
    query = ["dpkg-query", "-W", "-f", "${db:Status-Abbrev} ${Package}\n"]
    for line in lines(runner(query)):
        status, _, name = line.partition(" ")
        if status.startswith("ii"):
            installed.add(strip_arch(name.strip()))
    return installed


def apt_mark_manual(runner):
    return {strip_arch(name) for name in lines(runner(["apt-mark", "showmanual"]))}


def base_packages(paths):
    """Return (base package names, warning or None)."""
    for path in paths:
        try:
            opener = gzip.open if path.endswith(".gz") else open
            with opener(path, "rt", errors="replace") as handle:
                text = handle.read()
        except OSError:
            continue
        return (
            {strip_arch(m.group(1)) for m in INITIAL_STATUS_PACKAGE.finditer(text)},
            None,
        )
    return (
        set(),
        "no installer initial-status found at "
        + " or ".join(paths)
        + "; base OS packages cannot be excluded",
    )


def detect(runner=run, initial_status=APT_INITIAL_STATUS):
    installed = dpkg_installed(runner)
    manual = apt_mark_manual(runner)
    base, warning = base_packages(initial_status)
    warnings = [warning] if warning else []
    return Detection(
        backend="apt",
        packages=sorted((manual & installed) - base),
        image_packages=sorted(base),
        excluded_auto=[],
        warnings=warnings,
    )
