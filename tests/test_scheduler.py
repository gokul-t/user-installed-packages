import platform
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from user_installed_packages import scheduler


class SchedulerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_generate_systemd_service(self):
        content = scheduler.generate_systemd_service(
            command=["user-installed-packages", "report"],
            environment={"PATH": "/usr/bin:/bin"},
        )
        self.assertIn("[Unit]", content)
        self.assertIn("[Service]", content)
        self.assertIn("Type=oneshot", content)
        self.assertIn("ExecStart=", content)
        self.assertIn('Environment="PATH=/usr/bin:/bin"', content)
        self.assertIn("user-installed-packages", content)

    def test_generate_systemd_service_no_environment(self):
        content = scheduler.generate_systemd_service(
            command=["pytest", "-v"],
        )
        self.assertIn("[Service]", content)
        self.assertIn("ExecStart=", content)
        self.assertNotIn("Environment=", content)

    def test_generate_systemd_timer_default(self):
        content = scheduler.generate_systemd_timer()
        self.assertIn("[Unit]", content)
        self.assertIn("[Timer]", content)
        self.assertIn("OnCalendar=weekly", content)
        self.assertIn("Persistent=true", content)

    def test_generate_systemd_timer_custom(self):
        content = scheduler.generate_systemd_timer(on_calendar="daily")
        self.assertIn("OnCalendar=daily", content)

    def test_generate_launchd_plist_basic(self):
        content = scheduler.generate_launchd_plist(
            command=["user-installed-packages", "report", "--manifest-dir", "./ansible/packages"],
        )
        self.assertIn('<?xml version="1.0" encoding="UTF-8"?>', content)
        self.assertIn("<plist version=\"1.0\">", content)
        self.assertIn("<key>Label</key>", content)
        self.assertIn("<key>ProgramArguments</key>", content)
        self.assertIn("<string>com.dotfiles.package-report</string>", content)
        self.assertIn("<string>user-installed-packages</string>", content)

    def test_generate_launchd_plist_custom_label(self):
        content = scheduler.generate_launchd_plist(
            command=["test"],
            label="com.example.test",
        )
        self.assertIn("<string>com.example.test</string>", content)

    def test_generate_launchd_plist_custom_schedule(self):
        content = scheduler.generate_launchd_plist(
            command=["test"],
            schedule={"Weekday": 2, "Hour": 14, "Minute": 30},
        )
        self.assertIn("<integer>2</integer>", content)  # Weekday
        self.assertIn("<integer>14</integer>", content)  # Hour
        self.assertIn("<integer>30</integer>", content)  # Minute

    def test_generate_launchd_plist_with_environment(self):
        content = scheduler.generate_launchd_plist(
            command=["test"],
            environment={"PATH": "/usr/bin:/bin"},
        )
        self.assertIn("<key>EnvironmentVariables</key>", content)
        self.assertIn("<key>PATH</key>", content)
        self.assertIn("<string>/usr/bin:/bin</string>", content)

    def test_detect_scheduler_macos(self):
        with mock.patch.object(platform, "system", return_value="Darwin"):
            result = scheduler.detect_scheduler()
            self.assertEqual(result, "launchd")

    def test_detect_scheduler_linux_systemd(self):
        with mock.patch.object(platform, "system", return_value="Linux"):
            def mock_which(cmd):
                if cmd == "crontab":
                    return None
                return "/usr/bin/" + cmd
            
            with mock.patch.object(shutil, "which", side_effect=mock_which):
                with mock.patch.object(
                    scheduler.subprocess, "run",
                    return_value=mock.Mock(returncode=0, stdout="", stderr=""),
                ):
                    result = scheduler.detect_scheduler()
                    self.assertEqual(result, "systemd")

    def test_detect_scheduler_linux_cron_fallback(self):
        with mock.patch.object(platform, "system", return_value="Linux"):
            def mock_which(cmd):
                if cmd == "crontab":
                    return "/usr/bin/crontab"
                return None
            
            with mock.patch.object(shutil, "which", side_effect=mock_which):
                # systemctl --user returns error
                with mock.patch.object(
                    scheduler.subprocess, "run",
                    return_value=mock.Mock(returncode=1, stdout="", stderr=""),
                ):
                    result = scheduler.detect_scheduler()
                    self.assertEqual(result, "cron")

    def test_detect_scheduler_unsupported(self):
        # Test when neither systemd nor cron tools are available
        with mock.patch.object(platform, "system", return_value="Linux"):
            with mock.patch.object(shutil, "which", return_value=None):
                with mock.patch.object(
                    scheduler.subprocess, "run",
                    return_value=mock.Mock(returncode=1, stdout="", stderr=""),
                ):
                    result = scheduler.detect_scheduler()
                    # Should fallback to cron
                    self.assertEqual(result, "cron")  # Fallback

    def test_schedule_report_enables_systemd(self):
        with mock.patch.object(scheduler, "detect_scheduler", return_value="systemd"):
            with mock.patch.object(scheduler, "generate_systemd_service") as mock_service:
                with mock.patch.object(scheduler, "generate_systemd_timer") as mock_timer:
                    with mock.patch.object(
                        scheduler, "install_systemd_timer",
                        return_value=True
                    ) as mock_install:
                        result = scheduler.schedule_report(
                            command=["test", "cmd"],
                            enabled=True,
                        )
                        self.assertTrue(result)
                        mock_install.assert_called_once()
                        mock_service.assert_called_once()
                        mock_timer.assert_called_once()

    def test_schedule_report_disables_systemd(self):
        with mock.patch.object(scheduler, "detect_scheduler", return_value="systemd"):
            with mock.patch.object(
                scheduler, "disable_systemd_timer",
                return_value=True
            ) as mock_disable:
                result = scheduler.schedule_report(command=["test"], enabled=False)
                self.assertTrue(result)
                mock_disable.assert_called_once()

    def test_schedule_report_enables_launchd(self):
        with mock.patch.object(scheduler, "detect_scheduler", return_value="launchd"):
            with mock.patch.object(
                scheduler, "install_launchd_agent",
                return_value=True
            ) as mock_install:
                result = scheduler.schedule_report(
                    command=["test", "cmd"],
                    enabled=True,
                )
                self.assertTrue(result)
                mock_install.assert_called_once()

    def test_schedule_report_disables_launchd(self):
        with mock.patch.object(scheduler, "detect_scheduler", return_value="launchd"):
            with mock.patch.object(
                scheduler, "disable_launchd_agent",
                return_value=True
            ) as mock_disable:
                result = scheduler.schedule_report(command=["test"], enabled=False)
                self.assertTrue(result)
                mock_disable.assert_called_once()

    def test_schedule_report_enables_cron(self):
        with mock.patch.object(scheduler, "detect_scheduler", return_value="cron"):
            with mock.patch.object(
                scheduler, "install_cron_job",
                return_value=True
            ) as mock_install:
                result = scheduler.schedule_report(
                    command=["test", "cmd"],
                    enabled=True,
                )
                self.assertTrue(result)
                mock_install.assert_called_once()

    def test_schedule_report_disables_cron(self):
        with mock.patch.object(scheduler, "detect_scheduler", return_value="cron"):
            with mock.patch.object(
                scheduler, "disable_cron_job",
                return_value=True
            ) as mock_disable:
                result = scheduler.schedule_report(command=["test"], enabled=False)
                self.assertTrue(result)
                mock_disable.assert_called_once()

    def test_check_scheduler_enabled_systemd(self):
        with mock.patch.object(platform, "system", return_value="Linux"):
            with mock.patch.object(
                scheduler.subprocess, "run",
                return_value=mock.Mock(returncode=0, stdout="enabled\n", stderr=""),
            ):
                result = scheduler.check_scheduler_enabled()
                self.assertTrue(result)

    def test_check_scheduler_disabled_systemd(self):
        with mock.patch.object(platform, "system", return_value="Linux"):
            with mock.patch.object(
                scheduler.subprocess, "run",
                return_value=mock.Mock(returncode=3, stdout="", stderr=""),
            ):
                result = scheduler.check_scheduler_enabled()
                self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()