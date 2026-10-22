"""The 公告事项 on the title screen says 维护 (Leo 2026-10-22).

The texts are what the OCR read from Leo's screenshot (2K, 10-22 10:48).
"""

import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import numpy as np

from src.tasks import run_report
from src.tasks.trigger.AutoLoginTask import AutoLoginTask, MatchResult
from src.utils import maintenance_notice
from src.utils.game_day import GAME_TZ

NOTICE_SCREEN = [
    "v2.37.11(FHD-802:514)",
    "公告事项",
    "ROWNDUST II",
    "大家好，我们是冒汗心跳的RPG《棕色尘埃2》。",
    "将于10月22日（四）进行定期维护和更新。",
    "请玩家留意游戏使用。",
    "尘埃2",
    "更新时间：2026年10月22日(四) 上午7:50",
    "~11:00",
    "维护影响:",
    "将无法登入及使用游戏",
    "维护内容",
    "请至官网查看详细内容",
    "游戏启动中",
    "确认",
]
DURING = datetime(2026, 10, 22, 10, 48, tzinfo=GAME_TZ)
DAYS_BEFORE = datetime(2026, 10, 20, 9, 0, tzinfo=GAME_TZ)


def at(hour, minute=0, day=22, month=10):
    return datetime(2026, month, day, hour, minute, tzinfo=GAME_TZ)


class ParseTest(unittest.TestCase):
    def test_the_real_notice_reads_7_50_to_11_00(self):
        notice = maintenance_notice.read(" ".join(NOTICE_SCREEN), DURING)
        self.assertEqual(at(7, 50), notice.start)
        self.assertEqual(at(11), notice.end)
        self.assertTrue(notice.now_in(DURING))
        self.assertFalse(notice.now_in(DAYS_BEFORE))
        self.assertFalse(notice.now_in(at(11, 1)))

    def test_afternoon_and_an_end_without_its_own_word(self):
        self.assertEqual(
            (at(14), at(17)),
            maintenance_notice.parse_window("10月22日 下午2:00~5:00", DURING),
        )
        self.assertEqual(
            (at(10), at(13)),
            maintenance_notice.parse_window("10月22日 上午10:00 ~ 下午1:00", DURING),
        )
        self.assertEqual(
            (at(10), at(12)),
            maintenance_notice.parse_window("10月22日 上午10:00 ~ 12:00", DURING),
        )

    def test_overnight_with_an_end_date(self):
        self.assertEqual(
            (at(23, day=31), at(2, day=1, month=11)),
            maintenance_notice.parse_window("10月31日(六) 晚上11:00 ~ 11月1日(日) 凌晨2:00", DURING),
        )

    def test_24_hour_clock_and_korean(self):
        self.assertEqual(
            (at(7, 50), at(11)),
            maintenance_notice.parse_window("점검 10월 22일 (목) 07:50 ~ 11:00", DURING),
        )

    def test_a_date_with_no_time_after_it_is_skipped(self):
        # 「将于10月22日（四）进行定期维护」 has no time; the 更新时间 line has.
        window = maintenance_notice.parse_window(
            "将于10月22日（四）进行定期维护和更新。更新时间：10月22日 上午7:50~11:00", DURING
        )
        self.assertEqual((at(7, 50), at(11)), window)

    def test_traditional_chinese(self):
        notice = maintenance_notice.read("維護時間：10月22日（四）上午7:50～11:00 遊戲啟動中", DURING)
        self.assertEqual((at(7, 50), at(11)), (notice.start, notice.end))

    def test_no_maintenance_word_is_no_notice(self):
        self.assertIsNone(maintenance_notice.read("活动时间：10月22日 上午7:50~11:00 游戏启动中", DURING))

    def test_a_notice_inside_the_game_is_not_looked_at(self):
        # Leo 「只有登入畫面喔 不要點進去看到彈窗公告也判定」.
        inside = [line for line in NOTICE_SCREEN if line not in ("游戏启动中", "v2.37.11(FHD-802:514)")]
        self.assertIsNone(maintenance_notice.read(" ".join(inside), DURING))
        self.assertIsNotNone(maintenance_notice.read(" ".join(inside + ["v2.37.11(FHD-802:514)"]), DURING))

    def test_maintenance_with_no_readable_time_counts_as_now(self):
        notice = maintenance_notice.read("v2.37.11(FHD-802:514) 服务器维护中，请稍后再试", DURING)
        self.assertTrue(notice.now_in(DURING))
        self.assertEqual("游戏正在维护，已关闭游戏，这次没有跑。", maintenance_notice.message(notice))

    def test_message_says_until_when(self):
        notice = maintenance_notice.read(" ".join(NOTICE_SCREEN), DURING)
        self.assertEqual(
            "游戏正在维护（到 10/22 11:00），已关闭游戏，这次没有跑。",
            maintenance_notice.message(notice),
        )
        self.assertIn("没能自动关掉", maintenance_notice.message(notice, closed=False))


def _box(name):
    return SimpleNamespace(name=name, x=100, y=100, width=40, height=20)


class LoginMaintenanceTest(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        run_report.set_report_file(str(Path(folder.name) / "run_reports.json"))
        self.addCleanup(run_report.set_report_file, None)
        self.closed = []
        patches = [
            mock.patch(
                "src.utils.game_process.close_game",
                lambda: self.closed.append(True) or True,
            ),
            mock.patch("src.utils.scheduled_start.take_run_pending", lambda: True),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def _task(self, texts=NOTICE_SCREEN, waiting=True, state="waiting"):
        task = object.__new__(AutoLoginTask)
        task.config = {"BrownDustX OCR 阈值": 0.2, "登录后主页总等待秒数": 300.0}
        task.info = {}
        task.warnings = []
        task.clicks = []
        task.texts = list(texts)
        task.info_set = lambda key, value: task.info.__setitem__(key, value)
        task.log_info = lambda *_args, **_kwargs: None
        task.log_warning = lambda message, **kwargs: task.warnings.append(message)
        task.sleep = lambda *_args, **_kwargs: None
        task.ocr = lambda *_args, **_kwargs: [_box(text) for text in task.texts]
        task.operate_click = lambda *args, **_kwargs: task.clicks.append(args)
        task.capture_frame = lambda: np.zeros((10, 10, 3), dtype=np.uint8)
        task._match = lambda _frame, _spec: MatchResult(-1.0, (0, 0), (0, 0), pixel_score=-1.0)
        task._home_confirmation_signals = lambda _frame: (False, None, None, 0.0, "")
        task._clear_popups_until_home = lambda *_a, **_k: task.clicks.append("clear") or False
        task._click_login_after_touch = lambda *_a, **_k: task.clicks.append("login")
        task._state = state
        task._finished = False
        task._login_clicked_at = None
        task._login_retry_not_before = 0.0
        task._no_login_signal_since = None
        task._last_confirm_click_at = 0.0
        task._last_download_click_at = 0.0
        task.batch = SimpleNamespace(
            _start_after_login=waiting, batch_label="一键完成日常", cancelled=False
        )
        task.batch.cancel_resume = lambda: setattr(task.batch, "_start_after_login", False)
        task.batch.disable = lambda: setattr(task.batch, "cancelled", True)
        task._executor = SimpleNamespace(get_task_by_class=lambda _cls: task.batch)
        return task

    def _run(self, task, now, times=1):
        with mock.patch("src.tasks.trigger.AutoLoginTask.datetime") as clock:
            clock.now.return_value = now
            for _ in range(times):
                AutoLoginTask.run(task)

    def test_during_maintenance_the_waiting_run_ends_and_the_game_closes(self):
        task = self._task()
        self._run(task, DURING)
        self.assertEqual([], self.closed)  # one look is not enough
        self._run(task, DURING)
        self.assertEqual([True], self.closed)
        self.assertTrue(task.batch.cancelled)
        self.assertEqual([], task.clicks)  # 确认 is not pressed: nothing to log into
        report = run_report.load("一键完成日常")
        self.assertEqual(run_report.ENDED_SETUP, report["ended"])
        self.assertEqual(
            "游戏正在维护（到 10/22 11:00），已关闭游戏，这次没有跑。", report["notice"]
        )
        self.assertTrue(report.get("scheduled"))
        self.assertTrue(report.get("maintenance"))
        self.assertEqual(1, len(task.warnings))
        self.assertEqual("waiting", task._state)

    def test_an_announcement_days_ahead_is_closed_and_the_login_goes_on(self):
        task = self._task()
        self._run(task, DAYS_BEFORE)
        self.assertEqual([], self.closed)
        self.assertFalse(task.batch.cancelled)
        self.assertEqual(1, len(task.clicks))  # 确认
        self.assertIsNone(run_report.load("一键完成日常"))
        task.texts = ["TOUCH TO START"]
        task._match = lambda _f, _s: MatchResult(0.99, (0, 0), (1, 1), pixel_score=0.99)
        self._run(task, DAYS_BEFORE)
        self.assertEqual("login", task.clicks[-1])

    def test_the_players_own_game_is_left_open_with_one_word(self):
        task = self._task(waiting=False)
        self._run(task, DURING, times=5)
        self.assertEqual([], self.closed)
        self.assertEqual([], task.clicks)
        self.assertEqual(["自动登录：游戏正在维护（到 10/22 11:00），维护完再登录。"], task.warnings)
        self.assertIsNone(run_report.load("一键完成日常"))

    def test_a_notice_after_the_login_click_is_never_looked_at(self):
        for now in (DURING, DAYS_BEFORE):
            task = self._task(state="clearing")
            self._run(task, now, times=3)
            self.assertEqual(["clear"] * 3, task.clicks)
            self.assertEqual([], self.closed)
            self.assertFalse(task.batch.cancelled)

    def test_a_notice_inside_the_game_before_home_is_confirmed_is_left_alone(self):
        inside = [line for line in NOTICE_SCREEN if line not in ("游戏启动中", "v2.37.11(FHD-802:514)")]
        task = self._task(texts=inside)
        self._run(task, DURING, times=3)
        self.assertEqual([], self.closed)
        self.assertEqual([], task.clicks)
        self.assertFalse(task.batch.cancelled)

    def test_a_run_that_already_reports_keeps_its_own_report(self):
        task = self._task()
        run_report.begin("一键完成日常", "全部已启用子任务", [])
        self.addCleanup(lambda: run_report.active() and run_report.finish(run_report.ENDED_STOPPED))
        self._run(task, DURING, times=2)
        self.assertEqual([True], self.closed)
        self.assertIsNotNone(run_report.active())


if __name__ == "__main__":
    unittest.main()
