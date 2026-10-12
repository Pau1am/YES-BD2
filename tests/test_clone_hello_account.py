import sys
import types
import unittest
from unittest import mock

from src.utils import clone_desktop

SID = "S-1-5-21-1-2-3-1001"


class _Key:
    def __init__(self, subkeys):
        self.subkeys = subkeys

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def _winreg(user_extended=None, error=None):
    """A fake winreg: ``user_extended`` = number of HKCU identity subkeys, or
    None when the key is missing; ``error`` raised on opening instead."""
    fake = types.SimpleNamespace(HKEY_CURRENT_USER="HKCU")

    def open_key(_root, _path):
        if error is not None:
            raise error
        if user_extended is None:
            raise FileNotFoundError(_path)
        return _Key(user_extended)

    fake.OpenKey = open_key
    fake.QueryInfoKey = lambda key: (key.subkeys, 0, 0)
    return fake


class HelloOnlyAccountTest(unittest.TestCase):
    """The Windows Hello-only setting only matters for a Microsoft account
    (clone thread 2026-10-10): a local account has no switch to turn off."""

    def _run(
        self, *, policy=2, provider=None, user_extended=None, sid=SID, error=None,
        linked=None,
    ):
        def read_hklm(path, name):
            if name == "DevicePasswordLessBuildVersion":
                return policy
            if name == "ProviderName" and sid and sid in path:
                return provider
            return None

        with (
            mock.patch.dict(sys.modules, {"winreg": _winreg(user_extended, error)}),
            mock.patch.object(clone_desktop, "_read_hklm", side_effect=read_hklm),
            mock.patch.object(clone_desktop, "_current_user_sid", return_value=sid),
            mock.patch.object(clone_desktop, "_internet_identity", return_value=linked),
        ):
            return clone_desktop.microsoft_account(), clone_desktop.hello_only()

    def test_microsoft_account_with_the_setting_is_stopped(self):
        self.assertEqual((True, True), self._run(provider="MicrosoftAccount"))

    def test_local_account_is_not_stopped(self):
        self.assertEqual((False, False), self._run(provider=None, user_extended=None))

    def test_identity_store_says_local_wins_over_hkcu(self):
        self.assertEqual((False, False), self._run(provider="Local", user_extended=1))

    def test_hkcu_identity_counts_without_identity_store(self):
        self.assertEqual((True, True), self._run(provider=None, user_extended=1))
        self.assertEqual((True, True), self._run(sid=None, user_extended=2))

    def test_empty_hkcu_identity_is_local(self):
        self.assertEqual((False, False), self._run(user_extended=0))

    def test_cannot_tell_still_stops(self):
        self.assertEqual((None, True), self._run(error=PermissionError("denied")))

    def test_setting_off_never_stops(self):
        self.assertEqual((True, False), self._run(policy=0, provider="MicrosoftAccount"))
        self.assertEqual((True, False), self._run(policy=None, provider="MicrosoftAccount"))

    def test_windows_answer_comes_first(self):
        # B站 UP 2026-10-12: local account signed in to the Store (HKCU entry)
        # but no Microsoft account on Windows -> no switch, must not stop.
        self.assertEqual((False, False), self._run(linked=False, user_extended=1))
        self.assertEqual((True, True), self._run(linked=True, provider="Local"))

    def test_internet_identity_without_windows(self):
        if sys.platform == "win32":
            self.skipTest("real Windows answers")
        self.assertIsNone(clone_desktop._internet_identity())

    def test_sid_from_whoami(self):
        clone_desktop._current_user_sid.cache_clear()
        out = f'"desktop-abc\\nobel","{SID}"\n'
        result = types.SimpleNamespace(stdout=out)
        with mock.patch.object(clone_desktop.subprocess, "run", return_value=result):
            self.assertEqual(SID, clone_desktop._current_user_sid())
        clone_desktop._current_user_sid.cache_clear()
        with mock.patch.object(clone_desktop.subprocess, "run", side_effect=OSError("no")):
            self.assertIsNone(clone_desktop._current_user_sid())
        clone_desktop._current_user_sid.cache_clear()


class TurnOffHelloOnlyTest(unittest.TestCase):
    """「帮我关掉」 (Leo 2026-10-12): writes the value the Settings switch writes."""

    def test_elevated_writes_the_value(self):
        written = {}

        class Key(_Key):
            pass

        fake = types.SimpleNamespace(
            HKEY_LOCAL_MACHINE="HKLM", KEY_SET_VALUE=2, REG_DWORD=4,
            CreateKeyEx=lambda root, path, reserved, access: Key(0),
            SetValueEx=lambda key, name, reserved, kind, value: written.update(
                {name: (kind, value)}
            ),
        )
        with (
            mock.patch.dict(sys.modules, {"winreg": fake}),
            mock.patch.object(clone_desktop, "is_admin", return_value=True),
            mock.patch.object(clone_desktop, "hello_only", return_value=False),
        ):
            self.assertTrue(clone_desktop.turn_off_hello_only())
        self.assertEqual({"DevicePasswordLessBuildVersion": (4, 0)}, written)

    def _not_elevated(self, result, states):
        calls = []
        shell = types.SimpleNamespace()

        def shell_execute(*args):
            calls.append(args)
            return result

        shell.ShellExecuteW = shell_execute
        windll = types.SimpleNamespace(shell32=shell)
        with (
            mock.patch.object(clone_desktop.ctypes, "windll", windll, create=True),
            mock.patch.object(clone_desktop, "is_admin", return_value=False),
            mock.patch.object(clone_desktop, "hello_only", side_effect=states),
            mock.patch.object(clone_desktop.time, "sleep"),
        ):
            return clone_desktop.turn_off_hello_only(wait=5), calls

    def test_not_elevated_asks_windows_and_waits(self):
        done, calls = self._not_elevated(42, [True, True, False])
        self.assertTrue(done)
        _hwnd, verb, program, arguments, _cwd, show = calls[0]
        self.assertEqual(("runas", "reg.exe", 0), (verb, program, show))
        self.assertIn("DevicePasswordLessBuildVersion", arguments)
        self.assertIn("/d 0 /f", arguments)
        self.assertIn('"HKLM\\SOFTWARE\\Microsoft\\Windows NT\\', arguments)

    def test_player_said_no(self):
        done, _calls = self._not_elevated(5, [True])
        self.assertFalse(done)


if __name__ == "__main__":
    unittest.main()
