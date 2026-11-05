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

# Scheduler module exports
from user_installed_packages.scheduler import (
    DEFAULT_LABEL,
    DEFAULT_ON_CALENDAR,
    SchedulerError,
    check_scheduler_enabled,
    detect_scheduler,
    disable_cron_job,
    disable_launchd_agent,
    disable_systemd_timer,
    generate_launchd_plist,
    generate_systemd_service,
    generate_systemd_timer,
    install_cron_job,
    install_launchd_agent,
    install_systemd_timer,
    schedule_report,
)

__all__.extend([
    "DEFAULT_LABEL",
    "DEFAULT_ON_CALENDAR",
    "SchedulerError",
    "check_scheduler_enabled",
    "detect_scheduler",
    "disable_cron_job",
    "disable_launchd_agent",
    "disable_systemd_timer",
    "generate_launchd_plist",
    "generate_systemd_service",
    "generate_systemd_timer",
    "install_cron_job",
    "install_launchd_agent",
    "install_systemd_timer",
    "schedule_report",
])
