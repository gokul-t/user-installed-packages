import gzip
import tempfile
import unittest
from pathlib import Path

from user_installed_packages import apt

DPKG_QUERY = """ii  git
ii  zsh
ii  code:amd64
rc  old-removed
un  never
ii  curl
ii  apt
"""

APT_MARK_MANUAL = """git
zsh
code
old-removed
curl:amd64
"""

INITIAL_STATUS = """Package: git
Status: install ok installed
Architecture: amd64

Package: apt
Status: install ok installed

Package: curl
Status: install ok installed
"""


def fixture_runner(dpkg=DPKG_QUERY, manual=APT_MARK_MANUAL):
    def runner(argv):
        if argv[0] == "dpkg-query":
            return dpkg
        if argv[0] == "apt-mark":
            return manual
        raise AssertionError(f"unexpected command: {argv}")

    return runner


class BasePackagesTest(unittest.TestCase):
    def test_plain_initial_status_is_parsed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "initial-status"
            path.write_text(INITIAL_STATUS)
            base, warning = apt.base_packages((str(path),))
        self.assertEqual(base, {"git", "apt", "curl"})
        self.assertIsNone(warning)

    def test_gzipped_initial_status_is_parsed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "initial-status.gz"
            with gzip.open(path, "wt") as handle:
                handle.write(INITIAL_STATUS)
            base, warning = apt.base_packages((str(path),))
        self.assertEqual(base, {"git", "apt", "curl"})
        self.assertIsNone(warning)

    def test_missing_initial_status_warns_and_returns_empty(self):
        base, warning = apt.base_packages(("/nonexistent/initial-status.gz",))
        self.assertEqual(base, set())
        self.assertIn("initial-status", warning)


class DetectTest(unittest.TestCase):
    def test_base_image_packages_are_excluded(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "initial-status"
            path.write_text(INITIAL_STATUS)
            result = apt.detect(runner=fixture_runner(), initial_status=(str(path),))
        # git and curl are in the base image; zsh and code were installed by the user
        self.assertEqual(result.packages, ["code", "zsh"])
        self.assertEqual(sorted(result.image_packages), ["apt", "curl", "git"])
        self.assertEqual(result.warnings, [])

    def test_arch_qualifiers_are_stripped(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "initial-status"
            path.write_text("")  # empty base: everything manual is a candidate
            result = apt.detect(runner=fixture_runner(), initial_status=(str(path),))
        self.assertEqual(result.packages, ["code", "curl", "git", "zsh"])

    def test_only_fully_installed_packages_are_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "initial-status"
            path.write_text("")
            result = apt.detect(runner=fixture_runner(), initial_status=(str(path),))
        # rc (removed) and un (unknown) states are not 'ii' and must not appear
        self.assertNotIn("old-removed", result.packages)

    def test_missing_installer_log_keeps_candidates_and_warns(self):
        result = apt.detect(
            runner=fixture_runner(),
            initial_status=("/nonexistent/initial-status.gz",),
        )
        self.assertEqual(result.packages, ["code", "curl", "git", "zsh"])
        self.assertTrue(result.warnings)

    def test_to_dict_shape(self):
        result = apt.detect(runner=fixture_runner(), initial_status=("/nonexistent",))
        data = result.to_dict()
        self.assertEqual(data["backend"], "apt")
        self.assertEqual(
            set(data),
            {"backend", "packages", "image_packages", "excluded_auto", "warnings"},
        )


if __name__ == "__main__":
    unittest.main()
