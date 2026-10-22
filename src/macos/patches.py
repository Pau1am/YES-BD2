"""把 ok-script / YES-BD2 接到 ADB 上。

设计原则（为了上游能持续合并）：
  · 不改 ok-script（它是 pip 依赖，改了下次升级就丢）；
  · 只在本文件里做**运行期替换**，每一处都标注了它替换的上游函数，
    上游一升级，按注释里的名字核对一遍即可；
  · 替换失败不抛异常，只记日志——宁可少一个能力，也不要开不了机。
"""

from __future__ import annotations

import logging
import time

from src.macos import adb as adb_module

logger = logging.getLogger("bd2.macos.patches")

_applied: list[str] = []

# 这些任务靠「按住 W/A/S/D」走位，ADB 发不出按住事件，macOS 版不提供
KEYBOARD_ONLY_TASKS = ("RedemptionTowerTask",)
KEYBOARD_ONLY_BATCH_CHILDREN = ("救赎之塔",)


def _mark(name: str) -> None:
    _applied.append(name)
    logger.info("已接入 macOS 适配：%s", name)


def _skip(name: str, reason: str) -> None:
    logger.warning("跳过 %s：%s", name, reason)


def applied() -> list[str]:
    return list(_applied)


# --------------------------------------------------------------- ok-script


def patch_device_manager(adb: adb_module.Adb) -> None:
    """ok.device.DeviceManager：跳过 Windows 模拟器扫描、换掉截图实现。"""

    from ok.device.DeviceManager import DeviceManager

    # 上游 refresh_emulators 会 import ok.alas.emulator_windows（只认 Windows 注册表），
    # 它在 do_refresh 的同一个 try 里，抛异常会把后面的 refresh_phones 一起带掉。
    def no_emulators(self, current=False):
        logger.debug("macOS：跳过 Windows 模拟器枚举")
        return None

    DeviceManager.refresh_emulators = no_emulators
    _mark("DeviceManager.refresh_emulators → 空实现")

    original_screencap = DeviceManager.do_screencap

    def do_screencap(self, device):  # noqa: ANN001
        serial = getattr(device, "serial", None)
        if serial and adb.serial != serial:
            adb.serial = serial
        frame = adb.screencap()
        if frame is not None:
            return frame
        return original_screencap(self, device)

    DeviceManager.do_screencap = do_screencap
    _mark("DeviceManager.do_screencap → 原始 RGBA 取帧")


def patch_adb_interaction(adb: adb_module.Adb) -> None:
    """ok.device.interaction_methods.adb.ADBInteraction：补三个缺失的方法。"""

    from ok.device.interaction_methods.adb import ADBInteraction

    original_click = ADBInteraction.click

    def click(self, x=-1, y=-1, move_back=False, name=None, down_time=0.01, move=True, key=None):
        adb.ensure_foreground()  # 安卓的点击只给前台窗口
        return original_click(
            self, x, y, move_back=move_back, name=name, down_time=down_time, move=move, key=key
        )

    ADBInteraction.click = click
    _mark("ADBInteraction.click → 点击前确保游戏在前台")

    original_swipe = ADBInteraction.swipe

    def swipe(self, from_x, from_y, to_x, to_y, duration=0.3, settle_time=0):
        adb.ensure_foreground()
        return original_swipe(
            self, from_x, from_y, to_x, to_y, duration=duration, settle_time=settle_time
        )

    ADBInteraction.swipe = swipe
    _mark("ADBInteraction.swipe → 拖动前确保游戏在前台")

    def scroll(self, x, y, scroll_amount):
        """Windows 的滚轮 → 安卓的上下滑。正数=向上滚=手指向下划。"""

        if not scroll_amount:
            return None
        distance = max(160, min(700, abs(int(scroll_amount)) * 140))
        half = distance // 2
        if scroll_amount > 0:
            return self.swipe(x, y + half, x, y - half, duration=0.25)
        return self.swipe(x, y - half, x, y + half, duration=0.25)

    ADBInteraction.scroll = scroll
    _mark("ADBInteraction.scroll → 上下滑")

    def mouse_down(self, x=-1, y=-1, name=None, key="left"):
        self._macos_press_point = (x, y)
        return None

    def mouse_up(self, key="left"):
        point = getattr(self, "_macos_press_point", None)
        self._macos_press_point = None
        if point and point[0] >= 0 and point[1] >= 0:
            return adb.long_press(point[0], point[1], duration=0.12)
        return None

    ADBInteraction.mouse_down = mouse_down
    ADBInteraction.mouse_up = mouse_up
    _mark("ADBInteraction.mouse_down/up → 按住/松开")

    def long_press(self, x=-1, y=-1, duration=0.8):
        return adb.long_press(x, y, duration=duration)

    ADBInteraction.long_press = long_press


def patch_notifications() -> None:
    """ok.notification.system：Windows 托盘通知 → macOS 通知中心。"""

    try:
        from ok.notification import system as system_module
    except Exception as exc:  # pragma: no cover - 上游结构变了就跳过
        _skip("通知桥", f"ok.notification.system 不可用：{exc}")
        return

    def notify(title, message="", *args, **kwargs):
        import subprocess

        text = f"{title} {message}".replace('"', "'").strip()
        script = f'display notification "{text}" with title "YES-BD2"'
        try:
            subprocess.run(["osascript", "-e", script], capture_output=True, timeout=5)
        except Exception as exc:
            logger.debug("osascript 通知失败：%s", exc)

    replaced = []
    for name in ("notify", "toast", "show_toast", "send_notification"):
        target = getattr(system_module, name, None)
        if callable(target) and not isinstance(target, type):
            setattr(system_module, name, notify)
            replaced.append(name)
    if replaced:
        _mark(f"ok.notification.system → osascript（{', '.join(replaced)}）")
    else:
        _skip("通知桥", "没找到可替换的通知函数")


# ------------------------------------------------------------------ 应用层


def patch_base_task(adb: adb_module.Adb) -> None:
    from src.tasks.BaseBD2Task import BaseBD2Task

    def drag_client(self, start, end, duration=0.7, after_sleep=0.0):
        """上游用 win32 真鼠标拖动；ADB 下改成滑动，且不需要前台窗口检查。"""

        adb.ensure_foreground()
        interaction = getattr(self.executor, "interaction", None)
        if interaction is None:
            return False
        interaction.swipe(start[0], start[1], end[0], end[1], duration=duration)
        if after_sleep:
            self.sleep(after_sleep)
        return True

    BaseBD2Task.drag_client = drag_client
    _mark("BaseBD2Task.drag_client → ADB 滑动")

    for method, replacement, label in (
        ("_bring_game_to_foreground", lambda self: adb.ensure_foreground(), "安卓前台切换"),
        ("_point_on_game", lambda self, point: True, "恒真（安卓只有一个前台窗口）"),
    ):
        if hasattr(BaseBD2Task, method):
            setattr(BaseBD2Task, method, replacement)
            _mark(f"BaseBD2Task.{method} → {label}")
        else:
            _skip(f"BaseBD2Task.{method}", "上游已改名或删除，跳过（不影响 ADB 点击）")


def patch_game_process(adb: adb_module.Adb) -> None:
    """src.utils.game_process.game_running：用 adb pidof 判断游戏在不在。"""

    import src.utils.game_process as game_process

    def game_running():
        if not adb.serial:
            return None
        if adb.shell("echo", "1", timeout=3) is None:
            return None
        return adb.pidof() is not None

    game_process.game_running = game_running
    _mark("game_process.game_running → adb pidof")


def patch_keyboard() -> None:
    """ADB 下没有键盘：按键动作直接返回失败，不假装成功。

    上游有个别任务靠按住 W/A/S/D 走位（例如 救赎之塔 的祭坛），模拟器里发不出
    「按住」这种键，`input keyevent` 只是敲一下。与其让任务以为自己走了，
    不如立刻失败并在日志里说明原因。
    """

    from src.tasks.BaseBD2Task import BaseBD2Task

    def hold_key(self, key, seconds, after_sleep=0.0):
        self.log_info(f"macOS/ADB 没有键盘，跳过按键移动（{key} {seconds:.2f}s）")
        return False

    def tap_key(self, key, after_sleep=0.0):
        self.log_info(f"macOS/ADB 没有键盘，跳过快捷键 {key}")
        return False

    BaseBD2Task.hold_key = hold_key
    BaseBD2Task.tap_key = tap_key
    _mark("BaseBD2Task.hold_key / tap_key → 直接失败（无键盘）")


def patch_daily_batch() -> None:
    """一键日常里剔除必须走键盘的子任务，免得每天固定失败一项。"""

    import src.tasks.DailyBatchTask as batch

    children = getattr(batch, "DAILY_BATCH_CHILDREN", ())
    kept = tuple(
        child
        for child in children
        if getattr(child, "config_key", "") not in KEYBOARD_ONLY_BATCH_CHILDREN
    )
    if len(kept) == len(children):
        _skip("一键日常子任务", "没找到需要剔除的键盘任务")
        return
    batch.DAILY_BATCH_CHILDREN = kept
    _mark(f"一键日常剔除 {len(children) - len(kept)} 个键盘任务")


def start_game_if_needed(adb: adb_module.Adb, wait_seconds: float = 3.0) -> bool:
    """工具启动时把游戏带到前台；没装/没开就给一句人话。"""

    if not adb.serial:
        return False
    if not adb.installed():
        logger.error("模拟器里没装 %s", adb.package)
        return False
    if adb.pidof() is None:
        logger.info("游戏没在跑，尝试启动 %s", adb.package)
        adb.start_package()
        deadline = time.monotonic() + wait_seconds
        while time.monotonic() < deadline:
            if adb.pidof() is not None:
                break
            time.sleep(0.3)
    return adb.ensure_foreground(min_interval=0)


def install(adb: adb_module.Adb) -> list[str]:
    """按顺序打上所有补丁。任何一块失败都不影响其余部分。"""

    steps = (
        ("DeviceManager", lambda: patch_device_manager(adb)),
        ("ADBInteraction", lambda: patch_adb_interaction(adb)),
        ("通知", patch_notifications),
        ("BaseBD2Task", lambda: patch_base_task(adb)),
        ("键盘", patch_keyboard),
        ("一键日常", patch_daily_batch),
        ("game_process", lambda: patch_game_process(adb)),
    )
    for name, step in steps:
        try:
            step()
        except Exception as exc:  # noqa: BLE001 - 上游结构变化不该让工具起不来
            logger.error("macOS 适配 %s 失败：%s", name, exc, exc_info=True)
    return applied()
