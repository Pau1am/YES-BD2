"""The 桌面分身 page (Leo 2026-10-14): this PC's checks and the questions."""

import unittest
from unittest import mock

from src.ui.shell import clone_guide_page as page
from src.ui.shell.clone_guide_page import BAD, OK, WARN, checks


def _rows(**over):
    values = dict(
        supported=True, removed=False, ready=True, service="ok",
        microsoft=False, account="DESKTOP-ABC\\leo", hello_only=False,
    )
    values.update(over)
    return {row.label: row for row in checks(**values)}


class ChecksTest(unittest.TestCase):
    def test_home_edition_says_only_that(self):
        rows = _rows(supported=False)
        self.assertEqual(["Windows"], list(rows))
        self.assertEqual(BAD, rows["Windows"].tone)

    def test_all_good_has_no_buttons(self):
        rows = _rows()
        self.assertTrue(all(row.tone == OK and not row.action for row in rows.values()))
        self.assertIn("DESKTOP-ABC\\leo", rows["登录帐户"].text)
        self.assertIn("开机密码", rows["要打的密码"].text)

    def test_microsoft_account_wants_the_microsoft_password(self):
        rows = _rows(microsoft=True, account="MicrosoftAccount\\leo@outlook.com")
        self.assertIn("leo@outlook.com", rows["登录帐户"].text)
        self.assertNotIn("MicrosoftAccount", rows["登录帐户"].text)
        self.assertIn("微软帐号的密码", rows["要打的密码"].text)
        self.assertIn("不是 PIN", rows["要打的密码"].text)

    def test_each_known_problem_offers_its_fix(self):
        self.assertEqual("第一次设定", _rows(ready=False)["第一次设定"].action)
        self.assertEqual("第一次设定", _rows(removed=True)["分身程序"].action)
        self.assertEqual("帮我打开", _rows(service="disabled")["远程桌面服务"].action)
        self.assertEqual(BAD, _rows(service="missing")["远程桌面服务"].tone)
        self.assertEqual("", _rows(service="missing")["远程桌面服务"].action)
        self.assertEqual("帮我关掉", _rows(hello_only=True)["Windows Hello"].action)

    def test_unknown_account(self):
        rows = _rows(microsoft=None, account=None)
        self.assertEqual(WARN, rows["登录帐户"].tone)
        self.assertIn("不是 PIN", rows["要打的密码"].text)

    def test_every_question_has_steps(self):
        questions = [question for question, _steps, _folder in page.QUESTIONS]
        self.assertIn("提示「登录失败」", questions)
        self.assertTrue(all(steps for _q, steps, _f in page.QUESTIONS))


class PageTest(unittest.TestCase):
    def test_page_builds_and_fixes_refresh_it(self):
        from PySide6.QtWidgets import QApplication

        QApplication.instance() or QApplication([])
        from src.utils import clone_desktop

        with (
            mock.patch.object(clone_desktop, "supported", return_value=True),
            mock.patch.object(clone_desktop, "viewer_removed", return_value=False),
            mock.patch.object(clone_desktop, "ready", return_value=True),
            mock.patch.object(clone_desktop, "remote_desktop_service", return_value="disabled"),
            mock.patch.object(clone_desktop, "microsoft_account", return_value=False),
            mock.patch.object(clone_desktop, "sign_in_account", return_value="PC\\leo"),
            mock.patch.object(clone_desktop, "hello_only", return_value=False),
            mock.patch.object(
                clone_desktop, "enable_remote_desktop_service", return_value=True
            ) as enable,
        ):
            shown = page.CloneGuidePage()
            shown.refresh()
            self.assertEqual(6, shown.rows.count())
            shown._fix("帮我打开")
            enable.assert_called_once_with()
            self.assertIn("已经打开", shown.note.full_text())

    def test_sidebar_lists_the_page(self):
        from src.ui.shell.sidebar import Sidebar

        self.assertIn("clone", [key for key, _label, _icon in Sidebar.BOTTOM])


if __name__ == "__main__":
    unittest.main()
