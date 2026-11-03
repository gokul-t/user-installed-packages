"""Shared plumbing: tool runner, result model, distro auto-detection."""
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

TIMEOUT_SECONDS = 120
BASE_INSTALL_WINDOW_SECONDS = 6 * 3600
APT_INITIAL_STATUS = (
    "/var/log/installer/initial-status.gz",
    "/var/log/installer/initial-status",
)


class BackendError(Exception):
    """A backend failed to gather package data."""


class ToolMissingError(BackendError):
    """A required system tool is not installed."""


class UnsupportedDistroError(BackendError):
    """No backend exists for this operating system."""


@dataclass
class Detection:
    """The packages a user explicitly installed on this system."""

    backend: str
    packages: list  # user-installed names, sorted, image/auto excluded
    image_packages: list  # OS image base package names, sorted
    excluded_auto: list  # automatically installed updates (e.g. kernels), sorted
    warnings: list = field(default_factory=list)

    def to_dict(self):
        return {
            "backend": self.backend,
            "packages": self.packages,
            "image_packages": self.image_packages,
            "excluded_auto": self.excluded_auto,
            "warnings": self.warnings,
        }


def lines(text):
    return [line.strip() for line in text.splitlines() if line.strip()]


def run(argv):
    """Run argv with the locale pinned to C so output formats are stable."""
    env = dict(os.environ)
    env["LC_ALL"] = "C"
    try:
        proc = subprocess.run(
            argv, capture_output=True, text=True,
            timeout=TIMEOUT_SECONDS, check=False, env=env,
        )
    except FileNotFoundError:
        raise ToolMissingError(f"{argv[0]} not found") from None
    except subprocess.TimeoutExpired:
        raise BackendError(f"{' '.join(argv)} timed out") from None
    if proc.returncode != 0:
        raise BackendError(
            f"{' '.join(argv)} exited {proc.returncode}: {proc.stderr.strip()[:200]}"
        )
    return proc.stdout


def read_os_release(path="/etc/os-release"):
    info = {}
    try:
        text = Path(path).read_text(errors="replace")
    except OSError:
        return info
    for line in text.splitlines():
        key, sep, value = line.partition("=")
        if not sep:
            continue
        info[key.strip()] = value.strip().strip('"')
    return info


def backend_from_ids(ids):
    ids = {i.lower() for i in ids if i}
    if ids & {"fedora", "rhel", "centos", "rocky", "almalinux"}:
        return "dnf"
    if ids & {"debian", "ubuntu"}:
        return "apt"
    return None


def detect_backend_name(requested="auto"):
    if requested != "auto":
        return requested
    info = read_os_release()
    ids = {info.get("ID", "")} | set(info.get("ID_LIKE", "").split())
    backend = backend_from_ids(ids)
    if backend:
        return backend
    # Fall back to the tools present (minimal or container systems may lack os-release).
    if shutil.which("rpm") and shutil.which("dnf"):
        return "dnf"
    if shutil.which("dpkg-query") and shutil.which("apt-mark"):
        return "apt"
    raise UnsupportedDistroError(
        "unsupported or unrecognized system; pass --distro dnf|apt explicitly"
    )


def detect(backend="auto", runner=run):
    name = detect_backend_name(backend)
    if name == "dnf":
        from user_installed_packages import dnf

        return dnf.detect(runner=runner)
    if name == "apt":
        from user_installed_packages import apt

        return apt.detect(runner=runner)
    raise UnsupportedDistroError(f"no backend for distro {name!r}")
