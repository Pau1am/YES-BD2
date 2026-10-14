"""The clone signs in to the account Windows says this user is (player
2026-10-14): a local account that also signed in to the Store / Xbox was
offered its Microsoft account, so the PC's own password never worked."""

import sys
import unittest
from unittest import mock

from src.utils import clone_desktop


class SignInAccountTest(unittest.TestCase):
    def _account(self, identity, machine="DESKTOP-ABC"):
        with (
            mock.patch.object(clone_desktop, "_windows_identity", return_value=identity),
            mock.patch.dict(clone_desktop.os.environ, {"COMPUTERNAME": machine}),
        ):
            return clone_desktop.sign_in_account()

    def test_local_account_signs_in_as_machine_user(self):
        # The Store e-mail Windows still knows about is not the Windows account.
        self.assertEqual("DESKTOP-ABC\\leo", self._account((False, "", "leo")))

    def test_microsoft_account_signs_in_with_its_e_mail(self):
        self.assertEqual(
            "MicrosoftAccount\\leo@outlook.com",
            self._account((True, "leo@outlook.com", "leo")),
        )

    def test_unsure_leaves_the_guess_to_the_viewer(self):
        self.assertIsNone(self._account(None))
        self.assertIsNone(self._account((True, "", "leo")))
        self.assertIsNone(self._account((False, "", "leo"), machine=""))

    def test_internet_identity_still_reads_the_link(self):
        linked = (True, "a@b.c", "x")
        with mock.patch.object(clone_desktop, "_windows_identity", return_value=linked):
            self.assertTrue(clone_desktop._internet_identity())
        with mock.patch.object(clone_desktop, "_windows_identity", return_value=None):
            self.assertIsNone(clone_desktop._internet_identity())

    def test_no_windows_no_identity(self):
        if sys.platform == "win32":
            self.skipTest("real Windows answers")
        self.assertIsNone(clone_desktop._windows_identity())

    def test_saved_sign_in_reads_the_viewer_target(self):
        for found in (0, 1):
            advapi = mock.Mock()
            advapi.CredReadW.return_value = found
            windll = mock.Mock(advapi32=advapi)
            with mock.patch.object(clone_desktop.ctypes, "windll", windll, create=True):
                self.assertEqual(bool(found), clone_desktop.saved_sign_in())
            self.assertEqual("bd2-auto/clone-desktop", advapi.CredReadW.call_args.args[0])
            self.assertEqual(found, advapi.CredFree.call_count)


class OpenViewerAccountTest(unittest.TestCase):
    def _args(self, *, saved, account="DESKTOP-ABC\\leo"):
        started = []
        with (
            mock.patch.object(clone_desktop, "update_viewer"),
            mock.patch.object(clone_desktop, "write_startup_list"),
            mock.patch.object(clone_desktop, "saved_sign_in", return_value=saved),
            mock.patch.object(clone_desktop, "sign_in_account", return_value=account),
            mock.patch.object(clone_desktop, "is_admin", return_value=True),
            mock.patch.object(
                clone_desktop.subprocess, "Popen", side_effect=lambda cmd, **_k: started.append(cmd)
            ),
        ):
            self.assertTrue(clone_desktop.open_viewer(launch_tool=False))
        return started[0][1:]

    def test_the_account_is_handed_to_the_sign_in_box(self):
        args = self._args(saved=False)
        self.assertEqual(["-user", "DESKTOP-ABC\\leo"], args[:2])

    def test_a_saved_sign_in_keeps_its_own_account(self):
        self.assertNotIn("-user", self._args(saved=True))

    def test_unknown_account_passes_nothing(self):
        self.assertNotIn("-user", self._args(saved=False, account=None))


if __name__ == "__main__":
    unittest.main()
