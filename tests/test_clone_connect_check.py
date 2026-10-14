"""桌面分身 code 516 (B站 player report 2026-10-14).

The clone is a Remote Desktop session of the PC to itself.  When Windows'
「远程桌面服务」 is disabled or gone, the viewer only got Windows' generic
「未启用对服务器的远程访问 / 远程计算机已关闭」 text (code 516/0) and a note
about the password.  Now the tool checks the service before opening the
clone, and a connection failure is told apart from a wrong password.
"""

import re
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

from src.ui.shell import clone_flow
from src.utils import clone_desktop

REPO = Path(__file__).resolve().parents[1]
SERVICE = clone_desktop.REMOTE_DESKTOP_SERVICE_KEY


class RemoteDesktopServiceTest(unittest.TestCase):
    def _state(self, values):
        def read_hklm(path, name):
            return values.get((path, name))

        with (
            mock.patch.dict(sys.modules, {"winreg": types.SimpleNamespace()}),
            mock.patch.object(clone_desktop, "_read_hklm", side_effect=read_hklm),
        ):
            return clone_desktop.remote_desktop_service()

    def test_windows_default_is_ok(self):
        self.assertEqual("ok", self._state({
            (SERVICE, "Start"): 3,
            (SERVICE, "ImagePath"): r"%SystemRoot%\System32\svchost.exe -k NetworkService",
            (SERVICE + r"\Parameters", "ServiceDll"): r"%SystemRoot%\System32\termsrv.dll",
        }))

    def test_disabled_service(self):
        self.assertEqual("disabled", self._state({(SERVICE, "Start"): 4}))

    def test_service_removed_by_a_trimmed_windows(self):
        self.assertEqual("missing", self._state({}))

    def test_rdp_wrapper(self):
        self.assertEqual("replaced", self._state({
            (SERVICE, "Start"): 3,
            (SERVICE + r"\Parameters", "ServiceDll"): r"C:\Program Files\RDP Wrapper\rdpwrap.dll",
        }))

    def test_not_windows(self):
        with mock.patch.dict(sys.modules, {"winreg": None}):
            self.assertEqual("unknown", clone_desktop.remote_desktop_service())


class EnableRemoteDesktopServiceTest(unittest.TestCase):
    def _not_elevated(self, result, states):
        calls = []

        def shell_execute(*args):
            calls.append(args)
            return result

        windll = types.SimpleNamespace(shell32=types.SimpleNamespace(ShellExecuteW=shell_execute))
        with (
            mock.patch.object(clone_desktop.ctypes, "windll", windll, create=True),
            mock.patch.object(clone_desktop, "is_admin", return_value=False),
            mock.patch.object(clone_desktop, "remote_desktop_service", side_effect=states),
            mock.patch.object(clone_desktop.time, "sleep"),
        ):
            return clone_desktop.enable_remote_desktop_service(wait=5), calls

    def test_sets_windows_default_start_type_only(self):
        done, calls = self._not_elevated(42, ["disabled", "ok"])
        self.assertTrue(done)
        _hwnd, verb, program, arguments, _cwd, show = calls[0]
        self.assertEqual(("runas", "sc.exe", 0), (verb, program, show))
        # 手动 (demand) is Windows' default; Remote Desktop itself stays off.
        self.assertEqual("config TermService start= demand", arguments)

    def test_player_said_no(self):
        done, _calls = self._not_elevated(5, ["disabled"])
        self.assertFalse(done)

    def test_elevated_runs_sc_directly(self):
        with (
            mock.patch.object(clone_desktop, "is_admin", return_value=True),
            mock.patch.object(clone_desktop.subprocess, "run") as run,
            mock.patch.object(clone_desktop, "remote_desktop_service", return_value="ok"),
        ):
            self.assertTrue(clone_desktop.enable_remote_desktop_service())
        self.assertEqual(["sc.exe", "config", "TermService", "start=", "demand"], run.call_args.args[0])


class LaunchFailureTest(unittest.TestCase):
    def test_connection_failure(self):
        self.assertEqual(("noconnect", 516), clone_desktop.launch_failure("failed noconnect 516"))

    def test_other_failures(self):
        self.assertEqual(("other", None), clone_desktop.launch_failure("failed 沒有登入分身"))
        self.assertEqual(("other", None), clone_desktop.launch_failure("failed noconnect"))

    def test_player_text_says_it_is_not_the_password(self):
        text = clone_flow.launch_failure_text("failed noconnect 516")
        self.assertIn("516", text)
        self.assertIn("不是密码的问题", text)
        self.assertIn("viewer.log", text)
        self.assertIn(str(clone_desktop.DATA_DIR), text)
        other = clone_flow.launch_failure_text("failed 遠端桌面服務不能用")
        self.assertIn("遠端桌面服務不能用", other)

    def test_sign_in_failure_points_to_the_clone_page(self):
        # It used to say the tool did not open in the clone (Leo 2026-10-14).
        text = clone_flow.launch_failure_text("failed 沒有登入分身")
        self.assertIn("「桌面分身」页", text)
        self.assertIn("登录失败", text)
        self.assertNotIn("没能自动打开工具", text)

    def test_viewer_uses_the_same_codes(self):
        source = (REPO / "tools" / "clone_desktop" / "CloneDesktop.cs").read_text(encoding="utf-8")
        found = re.search(r"ConnectFailures = \{([^}]*)\}", source)
        self.assertIsNotNone(found)
        codes = {int(code) for code in found.group(1).split(",")}
        self.assertEqual(set(clone_desktop.CONNECT_FAILURES), codes)
        self.assertIn('"failed noconnect " + reason', source)


class _Box:
    """Stand-in for qfluentwidgets.MessageBox: records the text, answers yes."""

    shown = []
    answer = True

    def __init__(self, title, text, parent):
        self.text = text
        self.yesButton = types.SimpleNamespace(setText=lambda value: setattr(self, "yes", value))
        self.cancelButton = types.SimpleNamespace(
            setText=lambda value: None, hide=lambda: setattr(self, "no_cancel", True)
        )
        self.no_cancel = False
        _Box.shown.append(self)

    def exec(self):
        return _Box.answer


class AskAndStartTest(unittest.TestCase):
    def setUp(self):
        _Box.shown = []
        _Box.answer = True

    def _ask(self, service, *, hello=False, fixed=True):
        widgets = types.SimpleNamespace(MessageBox=_Box)
        with (
            mock.patch.dict(sys.modules, {"qfluentwidgets": widgets}),
            mock.patch.object(clone_flow.data, "busy", return_value=False),
            mock.patch.object(clone_desktop, "viewer_removed", return_value=False),
            mock.patch.object(clone_desktop, "ready", return_value=True),
            mock.patch.object(clone_desktop, "hello_only", return_value=hello),
            mock.patch.object(clone_desktop, "remote_desktop_service", return_value=service),
            mock.patch.object(clone_desktop, "enable_remote_desktop_service", return_value=fixed) as enable,
            mock.patch.object(clone_desktop, "turn_off_hello_only", return_value=True),
            mock.patch.object(clone_flow, "open_clone", return_value=True) as open_clone,
            mock.patch.object(clone_flow, "message") as message,
        ):
            started = clone_flow.ask_and_start(object(), object())
        return started, _Box.shown[-1], enable, open_clone, message

    def test_missing_service_explains_and_stops(self):
        started, box, enable, open_clone, _message = self._ask("missing")
        self.assertFalse(started)
        self.assertIn("远程桌面服务", box.text)
        self.assertEqual("知道了", box.yes)
        self.assertTrue(box.no_cancel)
        enable.assert_not_called()
        open_clone.assert_not_called()

    def test_disabled_service_is_turned_on_then_goes(self):
        started, box, enable, open_clone, _message = self._ask("disabled")
        self.assertTrue(started)
        self.assertEqual("帮我打开", box.yes)
        self.assertIn("别的电脑还是连不进来", box.text)
        enable.assert_called_once()
        open_clone.assert_called_once()

    def test_disabled_service_not_fixed(self):
        started, _box, _enable, open_clone, message = self._ask("disabled", fixed=False)
        self.assertFalse(started)
        open_clone.assert_not_called()
        self.assertTrue(message.call_args.kwargs.get("error"))

    def test_service_first_then_hello_on_the_next_press(self):
        started, _box, enable, open_clone, message = self._ask("disabled", hello=True)
        self.assertFalse(started)
        enable.assert_called_once()
        open_clone.assert_not_called()
        self.assertIn("再按一次", message.call_args.args[1])

    def test_working_service_goes_straight_on(self):
        for service in ("ok", "replaced", "unknown"):
            started, box, enable, open_clone, _message = self._ask(service)
            self.assertTrue(started)
            self.assertEqual("前往", box.yes)
            enable.assert_not_called()

    def test_ready_to_go_needs_the_service(self):
        with (
            mock.patch.object(clone_desktop, "viewer_removed", return_value=False),
            mock.patch.object(clone_desktop, "ready", return_value=True),
            mock.patch.object(clone_desktop, "hello_only", return_value=False),
            mock.patch.object(clone_desktop, "remote_desktop_service", side_effect=["disabled", "missing", "ok"]),
        ):
            self.assertFalse(clone_flow.ready_to_go())
            self.assertFalse(clone_flow.ready_to_go())
            self.assertTrue(clone_flow.ready_to_go())


if __name__ == "__main__":
    unittest.main()
