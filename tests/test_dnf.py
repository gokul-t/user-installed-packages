import unittest

from user_installed_packages import BackendError
from user_installed_packages import dnf

DNF_HISTORY_LIST = """ID Command line                            Date and time       Action(s) Altered
2 dnf5 --config /kiwi_dnf5.conf -y install  2025-04-09 12:06:00              286
1 dnf5 --config /kiwi_dnf5.conf -y install  2025-04-09 12:05:10             1722
3 dnf install fedy -y                        2025-08-24 17:36:20                2
4 dnf install vim-enhanced                   2025-12-22 18:01:59                4
"""

DNF_HISTORY_INFO_1 = """Transaction ID : 1
Begin time     : 2025-04-09 12:05:10
End time       : 2025-04-09 12:05:10
Status         : Ok
Packages altered:
  Action   Package                          Reason Repository
  Install  glibc-0:2.41-10.fc44.x86_64       Group  updates
  Install  kernel-core-0:7.0.0-1.fc44.x86_64  Group  updates
"""

DNF_HISTORY_INFO_2 = """Transaction ID : 2
Begin time     : 2025-04-09 12:06:00
End time       : 2025-04-09 12:06:00
Status         : Ok
Packages altered:
  Action   Package                          Reason Repository
  Install  fedora-release-workstation-0:44-18.noarch Group fedora
"""

DNF_HISTORY_INFO_3 = """Transaction ID : 3
Begin time     : 2025-08-24 17:36:20
Packages altered:
  Action   Package                          Reason Repository
  Install  fedy-0:5.1.18-1.fc44.noarch      User   copr
"""

DNF_HISTORY_INFO_4 = """Transaction ID : 4
Begin time     : 2025-12-22 18:01:59
Packages altered:
  Action   Package                          Reason Repository
  Install  vim-enhanced-2:9.2.1202-1.fc44.x86_64 User updates
"""

DNF_REPOQUERY = """glibc Group
kernel-core User
kernel-devel User
kernel-modules User
kernel-modules-core User
kernel-modules-extra User
kernel User
gpu-firmware Group
fedora-release-workstation Group
fedy User
vim-enhanced User
subversion Group
extra-user User
"""

DNF_INSTALLED = """glibc
kernel-core
kernel-devel
kernel-modules
kernel-modules-core
kernel-modules-extra
kernel
gpu-firmware
fedora-release-workstation
fedy
vim-enhanced
subversion
extra-user
git
neovim
"""


def fixture_runner(overrides=None):
    mapping = {
        ("rpm", "-qa"): DNF_INSTALLED,
        ("dnf", "repoquery"): DNF_REPOQUERY,
        ("dnf", "history", "list"): DNF_HISTORY_LIST,
        ("dnf", "history", "info", "1"): DNF_HISTORY_INFO_1,
        ("dnf", "history", "info", "2"): DNF_HISTORY_INFO_2,
        ("dnf", "history", "info", "3"): DNF_HISTORY_INFO_3,
        ("dnf", "history", "info", "4"): DNF_HISTORY_INFO_4,
    }
    mapping.update(overrides or {})

    def runner(argv):
        for size in range(len(argv), 1, -1):
            key = tuple(argv[:size])
            if key in mapping:
                value = mapping[key]
                if isinstance(value, Exception):
                    raise value
                return value
        raise BackendError(f"unexpected command: {argv}")

    return runner


DNF4_HISTORY_LIST = """ID     | Command line             | Date and time    | Action(s)      | Altered
-------------------------------------------------------------------------------
     2 | dnf install fedy         | 2025-08-24 17:36 | Install        |  1 EE
     1 | --config kiwi_dnf4.conf  | 2025-04-09 12:05 | Install        |  144 EE
"""

DNF4_HISTORY_INFO_1 = """Transaction ID : 1
Begin time     : Tue Apr 09 12:05:10 2025
Packages Altered:
    Install glibc-2.41-10.fc44.x86_64 @56c10ddcfae84956be9b699009cafa5b
    Install basesystem-11-20.fc40.noarch @56c10ddcfae84956be9b699009cafa5b
"""

DNF4_HISTORY_INFO_2 = """Transaction ID : 2
Begin time     : Sun Aug 24 17:36:20 2025
Packages Altered:
    Install fedy-5.1.18-1.fc44.noarch @coprid
"""


DNF4_REPOQUERY = DNF_REPOQUERY.lower()


class Dnf4DetectTest(unittest.TestCase):
    def test_pipe_table_history_is_parsed(self):
        def runner(argv):
            mapping = {
                ("dnf", "history", "list"): DNF4_HISTORY_LIST,
                ("dnf", "history", "info", "1"): DNF4_HISTORY_INFO_1,
                ("dnf", "history", "info", "2"): DNF4_HISTORY_INFO_2,
                ("dnf", "repoquery"): DNF4_REPOQUERY,
            }
            for size in range(len(argv), 1, -1):
                if tuple(argv[:size]) in mapping:
                    return mapping[tuple(argv[:size])]
            raise BackendError(f"unexpected command: {argv}")

        result = dnf.detect(runner=runner)
        self.assertIn("glibc", result.image_packages)
        self.assertIn("basesystem", result.image_packages)
        self.assertNotIn("glibc", result.packages)
        self.assertEqual(result.warnings, [])


class DetectTest(unittest.TestCase):
    def test_image_packages_and_auto_updates_are_excluded(self):
        result = dnf.detect(runner=fixture_runner())
        self.assertEqual(result.packages, ["extra-user", "fedy", "vim-enhanced"])
        self.assertIn("glibc", result.image_packages)
        self.assertIn("fedora-release-workstation", result.image_packages)
        self.assertIn("kernel-core", result.excluded_auto)
        self.assertEqual(result.warnings, [])

    def test_history_unavailable_falls_back_to_install_time_window(self):
        rpm_qa_times = "glibc 100\nold-base 100\nextra-user 1000000\n"

        def runner(argv):
            if tuple(argv) == ("rpm", "-qa", "--qf", "%{NAME} %{INSTALLTIME}\\n"):
                return rpm_qa_times
            if argv[:2] == ["dnf", "history"]:
                raise BackendError("history unavailable")
            return fixture_runner()(argv)

        result = dnf.detect(runner=runner)
        self.assertIn("extra-user", result.packages)
        self.assertNotIn("glibc", result.packages)
        self.assertNotIn("old-base", result.packages)
        self.assertTrue(result.warnings)

    def test_history_info_failure_skips_that_transaction(self):
        result = dnf.detect(runner=fixture_runner({("dnf", "history", "info", "2"): BackendError("boom")}))
        # fedora-release-workstation (tx 2) is lost, but tx 1 still excludes glibc/kernel-core
        self.assertNotIn("glibc", result.packages)

    def test_to_dict_round_trip(self):
        result = dnf.detect(runner=fixture_runner())
        data = result.to_dict()
        self.assertEqual(data["backend"], "dnf")
        self.assertEqual(set(data), {"backend", "packages", "image_packages", "excluded_auto", "warnings"})


class RpmPackageNameTest(unittest.TestCase):
    def test_strips_epoch_version_and_arch(self):
        self.assertEqual(
            dnf.rpm_package_name("vim-enhanced-2:9.2.1202-1.fc44.x86_64"),
            "vim-enhanced",
        )

    def test_package_without_epoch(self):
        self.assertEqual(
            dnf.rpm_package_name("fedy-5.1.18-1.fc44.noarch"),
            "fedy",
        )

    def test_plain_name_survives(self):
        self.assertEqual(dnf.rpm_package_name("glibc"), "glibc")


if __name__ == "__main__":
    unittest.main()
