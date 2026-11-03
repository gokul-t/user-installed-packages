"""List packages the user explicitly installed, excluding the OS image base.

Never installs, removes, or edits anything. See README.md for how the
per-distro detection works and what its limits are.
"""
from user_installed_packages.core import (
    APT_INITIAL_STATUS,
    BASE_INSTALL_WINDOW_SECONDS,
    BackendError,
    Detection,
    ToolMissingError,
    UnsupportedDistroError,
    backend_from_ids,
    detect,
    detect_backend_name,
    lines,
    read_os_release,
    run,
)

__all__ = [
    "APT_INITIAL_STATUS",
    "BASE_INSTALL_WINDOW_SECONDS",
    "BackendError",
    "Detection",
    "ToolMissingError",
    "UnsupportedDistroError",
    "backend_from_ids",
    "detect",
    "detect_backend_name",
    "lines",
    "read_os_release",
    "run",
]
