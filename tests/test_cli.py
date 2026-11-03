import contextlib
import io
import unittest
from unittest import mock

from user_installed_packages import cli
from user_installed_packages.core import BackendError, Detection

FAKE = Detection(
    backend="dnf",
    packages=["fedy", "vim-enhanced"],
    image_packages=["glibc"],
    excluded_auto=["kernel"],
    warnings=["sample warning"],
)


def run_cli(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main(argv)
    return code, out.getvalue(), err.getvalue()


class CliTest(unittest.TestCase):
    def test_plain_output_lists_packages_one_per_line(self):
        with mock.patch.object(cli, "detect", return_value=FAKE):
            code, out, err = run_cli([])
        self.assertEqual(code, 0)
        self.assertEqual(out, "fedy\nvim-enhanced\n")
        self.assertIn("sample warning", err)

    def test_json_output_contains_full_result(self):
        with mock.patch.object(cli, "detect", return_value=FAKE):
            code, out, err = run_cli(["--json"])
        self.assertEqual(code, 0)
        import json

        data = json.loads(out)
        self.assertEqual(data["packages"], ["fedy", "vim-enhanced"])
        self.assertEqual(data["backend"], "dnf")
        self.assertEqual(data["warnings"], ["sample warning"])

    def test_distro_flag_is_forwarded(self):
        with mock.patch.object(cli, "detect", return_value=FAKE) as call:
            run_cli(["--distro", "apt"])
        self.assertEqual(call.call_args.kwargs["backend"], "apt")

    def test_backend_error_exits_2_without_stdout_packages(self):
        with mock.patch.object(cli, "detect", side_effect=BackendError("nope")):
            code, out, err = run_cli([])
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("nope", err)

    def test_report_subcommand_is_dispatched(self):
        from user_installed_packages import report

        with mock.patch.object(report, "main", return_value=2) as report_main:
            code, out, err = run_cli(["report", "--manifest-dir", "/tmp/manifests"])
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertEqual(err, "")
        report_main.assert_called_once_with(["--manifest-dir", "/tmp/manifests"])


if __name__ == "__main__":
    unittest.main()
