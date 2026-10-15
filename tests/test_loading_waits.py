"""Loading time does not count as stuck (Leo 2026-10-15 「我說的10秒是卡死 或者
辨識不到」「一定會超過10秒甚至15秒」「你單純等載入怎麼可以改成只等10秒」).

Each wait below sees 20 s of the black loading screen and then its target:
it must pass.  A still screen that is neither loading nor the target still
ends after STUCK_SECONDS, and nothing waits past LOADING_MAX_SECONDS."""

import unittest
from types import SimpleNamespace
from unittest import mock

import numpy as np

from src.tasks.DailyTask import DailyTask
from src.tasks.FreeGachaTask import FreeGachaTask
from src.tasks.map_trade.models import ScreenState
from src.tasks.map_trade.navigator import Navigator
from src.tasks.PVPTask import PVPTask
from src.utils.frozen_screen import FrozenScreen, FrozenWatch
from src.utils.wait_limits import LOADING_MAX_SECONDS, STUCK_SECONDS, load_wait

BLACK = np.full((108, 192, 3), 12, np.uint8)
TARGET = np.full((108, 192, 3), 160, np.uint8)
OTHER = np.full((108, 192, 3), 90, np.uint8)


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, seconds=0.0, *_args, **_kwargs):
        self.t += max(float(seconds), 0.1)


def screens(clock, loading_for, then):
    return lambda *_a, **_k: BLACK if clock.t < loading_for else then


class LoadWaitTest(unittest.TestCase):
    def test_loading_does_not_count_a_still_screen_does(self):
        wait = load_wait(0.0, STUCK_SECONDS)
        for t in range(20):
            self.assertFalse(wait.over(BLACK, float(t), loading=True))
        self.assertFalse(wait.over(OTHER, 20.0))
        self.assertTrue(wait.over(OTHER, 20.0 + STUCK_SECONDS))

    def test_never_past_the_loading_cap(self):
        wait = load_wait(0.0, STUCK_SECONDS)
        self.assertTrue(wait.over(BLACK, LOADING_MAX_SECONDS, loading=True))

    def test_a_longer_saved_setting_stays(self):
        wait = load_wait(0.0, 45.0)
        self.assertFalse(wait.over(BLACK, 40.0, loading=True))


class FrozenWatchLoadingTest(unittest.TestCase):
    def test_a_black_loading_screen_for_20_s_then_the_page_passes(self):
        watch = FrozenWatch()
        for second in range(21):
            watch.look(BLACK, float(second))
        watch.look(TARGET, 21.0)
        watch.look(TARGET, 21.0 + STUCK_SECONDS - 1)

    def test_a_black_screen_past_the_loading_cap_is_stuck(self):
        watch = FrozenWatch()
        for second in range(int(LOADING_MAX_SECONDS)):
            watch.look(BLACK, float(second))
        with self.assertRaises(FrozenScreen) as raised:
            watch.look(BLACK, LOADING_MAX_SECONDS)
        self.assertIn("加载画面", str(raised.exception))

    def test_a_still_page_is_still_stuck_after_the_usual_limit(self):
        watch = FrozenWatch()
        for second in range(int(STUCK_SECONDS)):
            watch.look(OTHER, float(second))
        with self.assertRaises(FrozenScreen):
            watch.look(OTHER, STUCK_SECONDS)


class FieldHomeReturnTest(unittest.TestCase):
    """跑商/跑图: the chapter home button, then the loading, then 主页."""

    def _navigator(self, clock, then):
        task = SimpleNamespace(
            config={},
            sleep=clock.sleep,
            log_warning=lambda *_a, **_k: None,
            info_set=lambda *_a, **_k: None,
        )
        vision = SimpleNamespace(capture=screens(clock, 20.0, then))
        navigator = Navigator(task, vision)
        navigator._home_confirmation_signals = lambda frame, **_k: (
            frame is TARGET, 0, 0.0, ""
        )
        navigator._clear_return_home_announcement_if_needed = lambda *_a, **_k: False
        return navigator

    def test_home_after_20_s_of_loading(self):
        clock = Clock()
        navigator = self._navigator(clock, TARGET)
        with mock.patch("src.tasks.map_trade.navigator.monotonic", clock):
            self.assertTrue(navigator._wait_for_cartridge_home(timeout=10.0))
        self.assertGreaterEqual(clock.t, 20.0)

    def test_an_unknown_still_screen_ends_after_the_stuck_limit(self):
        clock = Clock()
        navigator = self._navigator(clock, OTHER)
        with mock.patch("src.tasks.map_trade.navigator.monotonic", clock):
            self.assertFalse(navigator._wait_for_cartridge_home(timeout=10.0))
        self.assertLess(clock.t, 20.0 + STUCK_SECONDS + 1.0)

    def test_the_loading_state_wait_runs_past_10_s(self):
        clock = Clock()
        navigator = self._navigator(clock, TARGET)
        navigator.classify = lambda frame=None: (
            ScreenState.HOME if frame is TARGET else ScreenState.LOADING
        )
        navigator._status = lambda *_a, **_k: None
        with mock.patch("src.tasks.map_trade.navigator.monotonic", clock):
            state = navigator.wait_state({ScreenState.HOME}, navigator._loading_timeout())
        self.assertEqual(ScreenState.HOME, state)


class DailyHomeConfirmationTest(unittest.TestCase):
    def test_home_after_20_s_of_loading(self):
        clock = Clock()
        task = object.__new__(DailyTask)
        task.config = {}
        task.capture_frame = screens(clock, 20.0, TARGET)
        task.sleep = clock.sleep
        task.info_set = lambda *_a, **_k: None
        task.log_info = lambda *_a, **_k: None
        task._home_confirmation_signals = lambda frame, _name: (frame is TARGET, 0, 0.0, "")
        task.clear_temporary_home_announcement_if_needed = lambda **_k: False
        with mock.patch("src.tasks.task_vision_mixin.monotonic", clock):
            self.assertTrue(DailyTask._wait_for_home_confirmation(task, "小屋签到返回主页"))

    def test_a_quick_look_stays_short(self):
        clock = Clock()
        task = object.__new__(DailyTask)
        task.config = {}
        task.capture_frame = screens(clock, 20.0, TARGET)
        task.sleep = clock.sleep
        task.info_set = lambda *_a, **_k: None
        task.log_info = lambda *_a, **_k: None
        task._home_confirmation_signals = lambda frame, _name: (frame is TARGET, 0, 0.0, "")
        task.clear_temporary_home_announcement_if_needed = lambda **_k: False
        with mock.patch("src.tasks.task_vision_mixin.monotonic", clock):
            self.assertFalse(
                DailyTask._wait_for_home_confirmation(task, "失败后主页确认", timeout=3.0)
            )
        self.assertLess(clock.t, 5.0)


class PvpHomeReturnTest(unittest.TestCase):
    def test_home_after_20_s_of_pvp_exit_loading(self):
        clock = Clock()
        task = object.__new__(PVPTask)
        task.config = {}
        task.capture_frame = screens(clock, 20.0, TARGET)
        task.sleep = clock.sleep
        task.info_set = lambda *_a, **_k: None
        task._home_confirmation_signals = lambda frame: (frame is TARGET, 0, 0.0, "")
        task.clear_temporary_home_announcement_if_needed = lambda **_k: False
        with mock.patch("src.tasks.PVPTask.monotonic", clock):
            self.assertTrue(PVPTask._wait_for_home(task, timeout=5.0))

    def test_the_pvp_field_without_loading_keeps_its_time(self):
        clock = Clock()
        task = object.__new__(PVPTask)
        task.config = {}
        task.capture_frame = lambda: OTHER
        task.sleep = clock.sleep
        task.info_set = lambda *_a, **_k: None
        task._home_confirmation_signals = lambda frame: (False, 0, 0.0, "")
        task.clear_temporary_home_announcement_if_needed = lambda **_k: False
        with mock.patch("src.tasks.PVPTask.monotonic", clock):
            self.assertFalse(PVPTask._wait_for_home(task, timeout=5.0))
        self.assertLess(clock.t, 6.0)


class GachaPageTest(unittest.TestCase):
    def test_gacha_page_after_20_s_of_loading(self):
        clock = Clock()
        task = object.__new__(FreeGachaTask)
        task.config = {"抽卡页面等待秒数": 10.0, "抽卡页面关键词最低命中数": 1}
        task.capture_frame = screens(clock, 20.0, TARGET)
        task.sleep = clock.sleep
        task.info_set = lambda *_a, **_k: None
        task.log_info = lambda *_a, **_k: None
        task._ocr_text = lambda frame, name: "服装 抽抽乐" if frame is TARGET else ""
        with mock.patch("src.tasks.FreeGachaTask.monotonic", clock):
            self.assertTrue(FreeGachaTask._wait_for_gacha_page(task, "进入抽卡页"))
        self.assertGreaterEqual(clock.t, 20.0)


if __name__ == "__main__":
    unittest.main()
