"""ADB 通道：macOS 上控制安卓模拟器里的游戏。

这条路对应 AzurPilot / ALAS 的做法——截图和点击都走 ADB，物理鼠标键盘不参与，
所以挂机时电脑照常使用。

坐标约定：`wm size` 报的分辨率就是截图尺寸，也就是 `input tap` 的坐标空间。
工具是按 1920x1080 标定模板的，所以模拟器请锁 1920x1080 横屏。
"""

from __future__ import annotations

import os
import re
import shutil
import struct
import subprocess
import time
from pathlib import Path

DEFAULT_PACKAGE = "com.neowizgames.game.browndust2"
# BlueStacks Air 默认 5555；MuMu Player Pro 默认 16384；夜神/雷电常见 62001/5554
CANDIDATE_PORTS = (5555, 16384, 5554, 62001, 7555, 5556)

_ADB_CANDIDATES = (
    "/opt/homebrew/bin/adb",
    "/usr/local/bin/adb",
    "~/Library/Android/sdk/platform-tools/adb",
)


def resolve_adb(explicit: str | None = None) -> str | None:
    """找一个可用的 adb：显式参数 > $ADB > PATH > 常见安装位置 > adbutils 自带。"""

    if explicit:
        return explicit if Path(explicit).expanduser().is_file() else None
    if env := os.environ.get("ADB"):
        if Path(env).expanduser().is_file():
            return str(Path(env).expanduser())
    if found := shutil.which("adb"):
        return found
    for candidate in _ADB_CANDIDATES:
        path = Path(candidate).expanduser()
        if path.is_file():
            return str(path)
    try:  # adbutils 会在自己的包目录里带一份 adb
        from adbutils._utils import _get_bin_dir

        path = Path(_get_bin_dir()) / "adb"
        if path.is_file():
            return str(path)
    except Exception:
        pass
    return None


class AdbError(RuntimeError):
    pass


class Adb:
    """一个设备的 adb 会话。没连上时所有操作都返回 None，不抛异常。"""

    def __init__(
        self,
        exe: str | None = None,
        serial: str | None = None,
        package: str = DEFAULT_PACKAGE,
        autoconnect: bool = True,
    ) -> None:
        self.exe = exe or resolve_adb()
        self.serial = serial
        self.package = package or DEFAULT_PACKAGE
        self.autoconnect = autoconnect
        self._last_front_check = 0.0
        self._front_ok = False

    # ---------------------------------------------------------------- 基础

    def available(self) -> bool:
        return bool(self.exe) and Path(self.exe).is_file()

    def run(
        self,
        *args: str,
        timeout: float = 20.0,
        binary: bool = False,
        check: bool = False,
    ) -> bytes | str | None:
        if not self.available():
            return None
        command = [self.exe, *args]
        try:
            proc = subprocess.run(
                command,
                capture_output=True,
                timeout=timeout,
                text=not binary,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            if check:
                raise AdbError(f"{' '.join(command)} 失败：{exc}") from exc
            return None
        if proc.returncode != 0:
            if check:
                message = proc.stderr if binary else proc.stderr.strip()
                raise AdbError(f"{' '.join(command)} 失败：{message}")
            return None
        return proc.stdout

    def shell(self, *args: str, timeout: float = 20.0, check: bool = False):
        if not self.serial:
            return None
        return self.run("-s", self.serial, "shell", *args, timeout=timeout, check=check)

    def devices(self) -> list[tuple[str, str]]:
        output = self.run("devices", "-l")
        if not output:
            return []
        result = []
        for line in str(output).splitlines()[1:]:
            line = line.strip()
            if not line or line.startswith("*"):
                continue
            parts = line.split()
            if len(parts) >= 2:
                result.append((parts[0], parts[1]))
        return result

    def connect(self, address: str) -> bool:
        output = self.run("connect", address, timeout=10)
        return bool(output) and "connected" in str(output)

    def bootstrap(self) -> tuple[bool, str]:
        """起 adb server、连模拟器、选定设备。返回 (是否可用, 说明)。"""

        if not self.available():
            return False, (
                "找不到 adb。装一个：brew install android-platform-tools，"
                "或用 --adb 指定路径"
            )
        self.run("start-server", timeout=20)
        devices = self.devices()
        online = [serial for serial, state in devices if state == "device"]
        if not online and self.autoconnect:
            for port in CANDIDATE_PORTS:
                address = f"127.0.0.1:{port}"
                self.connect(address)
                online = [
                    serial
                    for serial, state in self.devices()
                    if state == "device" and serial == address
                ]
                if online:
                    break
        if not online:
            return False, (
                "没有在线的安卓设备。请先打开 BlueStacks Air，"
                "并在设置里启用 ADB（默认端口 5555），然后 adb connect 127.0.0.1:5555"
            )
        if self.serial not in online:
            self.serial = online[0]
        return True, f"已连接 {self.serial}"

    # ---------------------------------------------------------------- 画面

    def wm_size(self) -> tuple[int, int] | None:
        output = self.shell("wm", "size")
        if not output:
            return None
        match = re.search(r"(\d+)x(\d+)", str(output))
        if not match:
            return None
        return int(match.group(1)), int(match.group(2))

    def screencap(self):
        """原样读取 RGBA 帧（比 `screencap -p` 少一次设备端 PNG 编码，快约一倍）。"""

        if not self.serial:
            return None
        data = self.run(
            "-s", self.serial, "exec-out", "screencap", timeout=15, binary=True
        )
        if not data or len(data) < 16:
            return None
        try:
            import cv2
            import numpy as np
        except ImportError:
            return None
        width, height, _pixel_format = struct.unpack_from("<III", data, 0)
        if not (0 < width <= 10000 and 0 < height <= 10000):
            return None
        frame_bytes = width * height * 4
        for header in (12, 16):  # Android 9+ 会在头部多带一个 colorspace
            if len(data) == header + frame_bytes:
                buffer = np.frombuffer(
                    data, dtype=np.uint8, count=frame_bytes, offset=header
                ).reshape(height, width, 4)
                return cv2.cvtColor(buffer, cv2.COLOR_RGBA2BGR)
        return None

    # ---------------------------------------------------------------- 输入

    def tap(self, x: float, y: float) -> bool:
        return self.shell("input", "tap", str(round(x)), str(round(y))) is not None

    def swipe(
        self, from_x: float, from_y: float, to_x: float, to_y: float, duration: float = 0.3
    ) -> bool:
        return (
            self.shell(
                "input",
                "swipe",
                str(round(from_x)),
                str(round(from_y)),
                str(round(to_x)),
                str(round(to_y)),
                str(max(1, round(duration * 1000))),
            )
            is not None
        )

    def long_press(self, x: float, y: float, duration: float = 0.8) -> bool:
        return self.swipe(x, y, x, y, duration)

    def press_back(self) -> bool:
        return self.shell("input", "keyevent", "KEYCODE_BACK") is not None

    # ---------------------------------------------------------------- 应用

    def pidof(self) -> int | None:
        output = self.shell("pidof", self.package)
        if not output:
            return None
        text = str(output).strip()
        if not text:
            return None
        first = text.split()[0]
        return int(first) if first.isdigit() else None

    def is_running(self) -> bool | None:
        if not self.serial:
            return None
        pid = self.pidof()
        return None if pid is None and self.shell("echo", "1") is None else pid is not None

    def start_package(self) -> bool:
        return (
            self.shell(
                "monkey",
                "-p",
                self.package,
                "-c",
                "android.intent.category.LAUNCHER",
                "1",
            )
            is not None
        )

    def installed(self) -> bool:
        output = self.shell("pm", "list", "packages", self.package, timeout=30)
        return bool(output) and self.package in str(output)

    def foreground_package(self) -> str | None:
        output = self.shell("dumpsys", "window", timeout=15)
        if not output:
            return None
        for line in str(output).splitlines():
            if "mCurrentFocus" in line or "mFocusedApp" in line:
                match = re.search(r"([A-Za-z0-9_.]+)/[A-Za-z0-9_.$]+", line)
                if match:
                    return match.group(1)
        return None

    def ensure_foreground(self, min_interval: float = 2.0) -> bool:
        """确保游戏在最前面——ADB 的点击只会给当前前台窗口。"""

        now = time.monotonic()
        if self._front_ok and now - self._last_front_check < min_interval:
            return True
        self._last_front_check = now
        if not self.serial:
            return False
        front = self.foreground_package()
        if front is None:
            self._front_ok = False
            return False
        if front == self.package:
            self._front_ok = True
            return True
        self.start_package()
        self._front_ok = False
        return False


def from_environment() -> Adb:
    """按环境变量造一个 Adb，方便给 selftest / main 共用。"""

    return Adb(
        exe=os.environ.get("OK_BD2_ADB") or None,
        serial=os.environ.get("OK_BD2_ADB_SERIAL") or None,
        package=os.environ.get("OK_BD2_ADB_PACKAGE") or DEFAULT_PACKAGE,
    )
