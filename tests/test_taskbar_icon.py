import tempfile
import unittest
from pathlib import Path
from unittest import mock

from src.compat import taskbar_icon


class TaskbarIconTest(unittest.TestCase):
    def test_installed_tool_relaunches_through_the_launcher_with_its_ico(self):
        with tempfile.TemporaryDirectory() as root:
            working = Path(root) / "data" / "apps" / "yes-bd2" / "working"
            (working / "icons").mkdir(parents=True)
            (working / "icons" / "icon.ico").write_bytes(b"ico")
            launcher = Path(root) / "yes-bd2.exe"
            launcher.write_bytes(b"exe")
            properties = taskbar_icon.window_properties(working)
            names = [name for name, _ in properties]
            values = dict(properties)
            self.assertEqual("System.AppUserModel.ID", names[-1])
            self.assertEqual(taskbar_icon.APP_ID, values["System.AppUserModel.ID"])
            self.assertEqual("YES-BD2", values["System.AppUserModel.RelaunchDisplayNameResource"])
            self.assertEqual(str(launcher), values["System.AppUserModel.RelaunchCommand"].strip('"'))
            icon = values["System.AppUserModel.RelaunchIconResource"]
            self.assertTrue(icon.endswith("icon.ico,0"), icon)

    def test_source_checkout_relaunches_main_py(self):
        with tempfile.TemporaryDirectory() as folder:
            values = dict(taskbar_icon.window_properties(folder))
            self.assertIn("main.py", values["System.AppUserModel.RelaunchCommand"])
            # no icons\icon.ico there: no icon property rather than a broken path
            self.assertNotIn("System.AppUserModel.RelaunchIconResource", values)

    def test_repo_ships_a_multi_size_ico(self):
        ico = Path(__file__).resolve().parents[1] / "icons" / "icon.ico"
        data = ico.read_bytes()
        self.assertEqual(b"\x00\x00\x01\x00", data[:4])
        self.assertGreaterEqual(int.from_bytes(data[4:6], "little"), 2)

    def test_nothing_happens_off_windows(self):
        with mock.patch.object(taskbar_icon.sys, "platform", "linux"):
            self.assertFalse(taskbar_icon.set_process_app_id())
            self.assertFalse(taskbar_icon.apply_to_main_window(object()))

    def test_main_sets_the_id_before_any_window(self):
        main = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")
        self.assertLess(main.index("set_process_app_id()"), main.index("import ok\n"))
        self.assertLess(main.index("relaunch_as_admin()"), main.index("set_process_app_id()"))


if __name__ == "__main__":
    unittest.main()
