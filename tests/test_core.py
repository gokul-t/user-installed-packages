import unittest

from user_installed_packages import backend_from_ids


class BackendFromIdsTest(unittest.TestCase):
    def test_fedora_family(self):
        for ids in (["fedora"], ["rhel"], ["centos", "rhel"], ["rocky"], ["almalinux"]):
            self.assertEqual(backend_from_ids(ids), "dnf")

    def test_debian_family(self):
        for ids in (["debian"], ["ubuntu"], ["linuxmint", "ubuntu"]):
            self.assertEqual(backend_from_ids(ids), "apt")

    def test_unknown_returns_none(self):
        self.assertIsNone(backend_from_ids(["arch"]))
        self.assertIsNone(backend_from_ids([]))


if __name__ == "__main__":
    unittest.main()
