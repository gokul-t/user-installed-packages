"""Scheduler management for package drift reports.

Provides cross-platform scheduling using systemd (Linux), LaunchAgent (macOS),
or cron (Linux fallback). Never installs, removes, or edits packages.
"""
import json
import os
import platform
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from user_installed_packages.core import ToolMissingError

# Default label for systemd/launchd
DEFAULT_LABEL = "com.dotfiles.package-report"

# Default systemd/onetime schedule
DEFAULT_ON_CALENDAR = "weekly"


class SchedulerError(Exception):
    """A scheduler operation failed."""

    pass


def detect_scheduler() -> str:
    """Detect the best available scheduler for this platform.

    Returns:
        One of "systemd", "cron", or "launchd"
    """
    system = platform.system()
    if system == "Darwin":
        return "launchd"
    if system == "Linux":
        # Check for systemd user manager first
        try:
            proc = subprocess.run(
                ["systemctl", "--user", "show-environment"],
                capture_output=True, text=True, check=False,
            )
            if proc.returncode == 0:
                try:
                    shutil.which("systemctl")
                    return "systemd"
                except (FileNotFoundError, OSError):
                    pass
        except FileNotFoundError:
            pass
        # Check for cron as fallback
        if shutil.which("crontab"):
            return "cron"
    return "cron"  # Fallback for unknown systems


def escape_arg(arg: str) -> str:
    """Escape an argument for shell commands."""
    # Use shlex.quote for proper escaping
    import shlex
    return shlex.quote(arg)


def generate_systemd_service(
    command: list,
    environment: Optional[dict] = None,
) -> str:
    """Generate systemd service unit file content.

    Args:
        command: List of command and arguments
        environment: Optional dict of environment variables

    Returns:
        Service unit file content
    """
    env_lines = ""
    if environment:
        for key, value in environment.items():
            # Escape quotes and backslashes in values
            escaped_value = value.replace("\\", "\\\\").replace('"', '\\"')
            env_lines += f'Environment="{key}={escaped_value}"\n'

    args = " ".join(escape_arg(arg) for arg in command)
    return f"""[Unit]
Description=Package drift report
After=network.target

[Service]
Type=oneshot
{env_lines}ExecStart={args}
"""


def generate_systemd_timer(on_calendar: str = DEFAULT_ON_CALENDAR) -> str:
    """Generate systemd timer unit file content.

    Args:
        on_calendar: systemd calendar event expression (default: weekly)

    Returns:
        Timer unit file content
    """
    return f"""[Unit]
Description=Weekly package drift report timer

[Timer]
OnCalendar={on_calendar}
Persistent=true

[Install]
WantedBy=timers.target
"""


def generate_launchd_plist(
    command: list,
    environment: Optional[dict] = None,
    schedule: Optional[dict] = None,
    label: str = DEFAULT_LABEL,
) -> str:
    """Generate LaunchAgent plist file content.

    Args:
        command: List of command and arguments
        environment: Optional dict of environment variables
        schedule: Optional dict with Weekday, Hour, Minute (default: Mon 9:00)
        label: LaunchAgent label

    Returns:
        plist XML content
    """
    if schedule is None:
        schedule = {"Weekday": 1, "Hour": 9, "Minute": 0}

    # Escape arguments for plist strings
    def escape_plist_string(s):
        s = s.replace("\\", "\\\\")
        s = s.replace('"', '\\"')
        return s

    args_xml = "\n".join(
        f'    <string>{escape_plist_string(arg)}</string>'
        for arg in command
    )

    env_xml = ""
    if environment:
        env_entries = "\n".join(
            f'    <key>{key}</key>\n    <string>{escape_plist_string(value)}</string>'
            for key, value in environment.items()
        )
        env_xml = f"""<key>EnvironmentVariables</key>
    <dict>
{env_entries}
    </dict>"""

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "apple.com/DTDs/Plist1.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>{label}</string>
  <key>ProgramArguments</key>
  <array>
{args_xml}
  </array>
  {env_xml}
  <key>StartCalendarInterval</key>
  <dict>
    <key>Weekday</key>
    <integer>{schedule.get('Weekday', 1)}</integer>
    <key>Hour</key>
    <integer>{schedule.get('Hour', 9)}</integer>
    <key>Minute</key>
    <integer>{schedule.get('Minute', 0)}</integer>
  </dict>
  <key>StandardOutPath</key>
  <string>/dev/null</string>
  <key>StandardErrorPath</key>
  <string>/dev/null</string>
</dict>
</plist>"""


def install_systemd_timer(
    service_content: str,
    timer_content: str,
    label: str = DEFAULT_LABEL,
    user: bool = True,
) -> bool:
    """Install and enable a systemd user timer.

    Args:
        service_content: Service unit file content
        timer_content: Timer unit file content
        label: Base name for the unit files
        user: If True, install as user service

    Returns:
        True if installation succeeded and changes were made
        False if already configured correctly or installation failed
    """
    # Determine systemd unit directory
    if user:
        unit_dir = Path.home() / ".config" / "systemd" / "user"
    else:
        unit_dir = Path("/etc/systemd/system")

    unit_dir.mkdir(parents=True, exist_ok=True)

    service_path = unit_dir / f"{label}.service"
    timer_path = unit_dir / f"{label}.timer"

    # Check if already configured identically (idempotent check)
    if (service_path.exists() and timer_path.exists()):
        if (service_path.read_text() == service_content and
            timer_path.read_text() == timer_content):
            return False  # No changes needed

    # Write files
    service_path.write_text(service_content)
    timer_path.write_text(timer_content)

    # Reload and enable
    scope = "user" if user else "system"
    try:
        subprocess.run(
            ["systemctl", "--user", "daemon-reload"],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["systemctl", "--user", "enable", "--now", f"{label}.timer"],
            check=True, capture_output=True,
        )
        return True
    except subprocess.CalledProcessError:
        return False


def disable_systemd_timer(label: str = DEFAULT_LABEL, user: bool = True) -> bool:
    """Disable and remove a systemd user timer.

    Args:
        label: Base name for the unit files
        user: If True, manage user service

    Returns:
        True if removal succeeded
    """
    if user:
        unit_dir = Path.home() / ".config" / "systemd" / "user"
    else:
        unit_dir = Path("/etc/systemd/system")

    service_path = unit_dir / f"{label}.service"
    timer_path = unit_dir / f"{label}.timer"

    try:
        subprocess.run(
            ["systemctl", "--user", "stop", f"{label}.timer"],
            check=False, capture_output=True,
        )
        subprocess.run(
            ["systemctl", "--user", "disable", f"{label}.timer"],
            check=False, capture_output=True,
        )
    except FileNotFoundError:
        pass

    # Remove files
    if service_path.exists():
        service_path.unlink()
    if timer_path.exists():
        timer_path.unlink()

    # Reload daemon
    try:
        subprocess.run(
            ["systemctl", "--user", "daemon-reload"],
            check=True, capture_output=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    return True


def install_launchd_agent(
    plist_content: str,
    label: str = DEFAULT_LABEL,
) -> bool:
    """Install a LaunchAgent plist.

    Args:
        plist_content: The plist XML content
        label: LaunchAgent label (also used for filename)

    Returns:
        True if installation succeeded and changes were made
        False if already configured correctly or installation failed
    """
    launch_agent_dir = Path.home() / "Library" / "LaunchAgents"
    launch_agent_dir.mkdir(parents=True, exist_ok=True)

    plist_path = launch_agent_dir / f"{label}.plist"

    # Check if already configured identically (idempotent check)
    if plist_path.exists() and plist_path.read_text() == plist_content:
        return False  # No changes needed

    plist_path.write_text(plist_content)

    # Load the agent
    try:
        subprocess.run(
            ["launchctl", "bootout", f"gui/{os.getuid()}/{label}"],
            check=False, capture_output=True,
        )
        subprocess.run(
            ["launchctl", "bootstrap", f"gui/{os.getuid()}", str(plist_path)],
            check=True, capture_output=True,
        )
        return True
    except subprocess.CalledProcessError:
        return False


def disable_launchd_agent(label: str = DEFAULT_LABEL) -> bool:
    """Disable and remove a LaunchAgent.

    Args:
        label: LaunchAgent label

    Returns:
        True if removal succeeded
    """
    launch_agent_path = Path.home() / "Library" / "LaunchAgents" / f"{label}.plist"

    try:
        subprocess.run(
            ["launchctl", "bootout", f"gui/{os.getuid()}/{label}"],
            check=False, capture_output=True,
        )
    except FileNotFoundError:
        pass

    if launch_agent_path.exists():
        launch_agent_path.unlink()

    return True


def install_cron_job(
    name: str,
    command: str,
    schedule: str = "weekly",
) -> bool:
    """Install a cron job.

    Args:
        name: Name identifier for the job
        command: Full command to run
        schedule: cron schedule expression or special time (e.g., "weekly")

    Returns:
        True if installation succeeded and changes were made
        False if already configured correctly or installation failed
    """
    expected_job_line = f"{schedule} {command}  # {name}"
    
    try:
        # Get current crontab
        result = subprocess.run(
            ["crontab", "-l"],
            capture_output=True, text=True, check=False,
        )
        current = result.stdout if result.returncode == 0 else ""
    except FileNotFoundError:
        return False

    # Check if job already exists with same content
    for line in current.splitlines():
        if name in line and line.strip() == expected_job_line.strip():
            return False  # Already configured identically

    # Remove any existing job with this name
    lines = [
        line for line in current.splitlines()
        if name not in line
    ]

    # Add new job
    lines.append(expected_job_line)

    # Install new crontab
    try:
        proc = subprocess.run(
            ["crontab", "-"],
            input="\n".join(lines) + "\n",
            capture_output=True, text=True, check=True,
        )
        return True
    except subprocess.CalledProcessError:
        return False


def disable_cron_job(name: str) -> bool:
    """Disable and remove a cron job by name.

    Args:
        name: Name identifier for the job

    Returns:
        True if removal succeeded
    """
    try:
        result = subprocess.run(
            ["crontab", "-l"],
            capture_output=True, text=True, check=False,
        )
        if result.returncode != 0:
            return True  # No crontab, job doesn't exist
        current = result.stdout
    except FileNotFoundError:
        return True

    # Remove lines with this name
    lines = [
        line for line in current.splitlines()
        if name not in line
    ]

    if len(lines) < len(current.splitlines()):
        # Something changed, update crontab
        try:
            subprocess.run(
                ["crontab", "-"],
                input="\n".join(lines) + "\n" if lines else "",
                capture_output=True, text=True, check=True,
            )
        except subprocess.CalledProcessError:
            pass

    return True


def schedule_report(
    command: list,
    environment: Optional[dict] = None,
    enabled: bool = True,
    on_calendar: str = DEFAULT_ON_CALENDAR,
    label: str = DEFAULT_LABEL,
    schedule: Optional[dict] = None,
) -> bool:
    """Schedule or unschedule a package drift report.

    This is the main entry point for scheduling. It detects the available
    scheduler and performs the appropriate actions.

    Args:
        command: Command and arguments to run (e.g., ["user-installed-packages", "report", "--manifest-dir", "./ansible/packages"])
        environment: Environment variables for the command
        enabled: If True, enable scheduling; if False, disable it
        on_calendar: systemd calendar expression (default: "weekly")
        label: Identifier for the scheduled job
        schedule: For launchd, dict with Weekday/Hour/Minute (default: Mon 9:00)

    Returns:
        True if the operation succeeded

    Raises:
        SchedulerError: If the scheduler type is unknown or operation failed
    """
    scheduler = detect_scheduler()

    # Build command string for cron
    command_str = " ".join(escape_arg(str(arg)) for arg in command)
    if environment:
        # Prepend environment variables
        env_parts = []
        for key, value in environment.items():
            env_parts.append(f'{key}={escape_arg(str(value))}')
        command_str = " ".join(env_parts) + " " + command_str

    if enabled:
        if scheduler == "systemd":
            service_content = generate_systemd_service(command, environment)
            timer_content = generate_systemd_timer(on_calendar)
            return install_systemd_timer(
                service_content, timer_content, label
            )
        elif scheduler == "launchd":
            plist_content = generate_launchd_plist(
                command, environment, schedule, label
            )
            return install_launchd_agent(plist_content, label)
        elif scheduler == "cron":
            return install_cron_job(label, command_str)
    else:
        if scheduler == "systemd":
            return disable_systemd_timer(label)
        elif scheduler == "launchd":
            return disable_launchd_agent(label)
        elif scheduler == "cron":
            return disable_cron_job(label)

    raise SchedulerError(f"Unknown scheduler type: {scheduler}")


def check_scheduler_enabled(label: str = DEFAULT_LABEL) -> Optional[bool]:
    """Check if a scheduled report is enabled.

    Args:
        label: The scheduler label/identifier

    Returns:
        True if enabled, False if disabled, None if unknown/not found
    """
    scheduler = detect_scheduler()

    if scheduler == "systemd":
        try:
            result = subprocess.run(
                ["systemctl", "--user", "is-enabled", f"{label}.timer"],
                capture_output=True, text=True, check=False,
            )
            if result.returncode == 0:
                return result.stdout.strip() == "enabled"
            return False
        except FileNotFoundError:
            return None
    elif scheduler == "launchd":
        plist_path = Path.home() / "Library" / "LaunchAgents" / f"{label}.plist"
        return plist_path.exists()
    elif scheduler == "cron":
        try:
            result = subprocess.run(
                ["crontab", "-l"],
                capture_output=True, text=True, check=False,
            )
            if result.returncode != 0:
                return False
            return label in result.stdout
        except FileNotFoundError:
            return None
    return None