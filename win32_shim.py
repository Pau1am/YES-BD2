"""macOS 上的 Windows API 垫片（win32 shim）。

为什么要它：YES-BD2 依赖的 ok-script 在**模块导入阶段**就 `import win32gui`、
`ctypes.WinDLL('user32')`、`SendInput = ctypes.windll.user32.SendInput`，本仓库也有
一批模块在顶层 `import win32api`。这些 API 在 macOS 上不存在，但它们只在
「窗口截图 / PostMessage 点击」那条路径上被**执行**；走 ADB 时这些代码永远不该跑。
所以在导入 `ok` 和 `src` 之前，把缺失的模块换成桩：导入就通了，真被调用时打一条
警告（说明有代码误走了 Windows 分支）。

用法（必须在任何 `import ok` / `import src` 之前）：

    import win32_shim
    win32_shim.install()

注意：这是给「ADB 设备」这条路用的，它不会让窗口截图、后台点击在 macOS 上工作。
"""

from __future__ import annotations

import logging
import sys
import types

logger = logging.getLogger("bd2.macos.shim")

# 这些模块在 macOS 上要么装不上、要么装上了也 import 不动
_WIN_MODULES = (
    "win32api",
    "win32con",
    "win32gui",
    "win32process",
    "win32ui",
    "win32event",
    "win32file",
    "win32security",
    "win32clipboard",
    "win32print",
    "win32com",
    "win32com.client",
    "pywintypes",
    "pythoncom",
    "comtypes",
    "comtypes.client",
    "comtypes.gen",
    "pycaw",
    "pycaw.pycaw",
    "pydirectinput",
    "mouse",
    "winreg",
    "msvcrt",
    "wmi",
    "_winapi",
)

_installed: list[str] = []
_warned: set[str] = set()


class _StubAny:
    """任意属性、任意调用都能接住的对象（模拟 COM/DLL/结构体）。"""

    def __init__(self, path: str) -> None:
        self._path = path

    def __getattr__(self, item: str):
        if item.startswith("__") and item.endswith("__"):
            raise AttributeError(item)
        return _StubAny(f"{self._path}.{item}")

    def __setattr__(self, key: str, value) -> None:
        object.__setattr__(self, key, value)

    def __call__(self, *args, **kwargs):
        if self._path not in _warned:
            _warned.add(self._path)
            logger.warning(
                "win32 桩被调用：%s —— macOS 上无意义，返回空值。"
                "如果这行出现在正常流程里，说明有代码走了 Windows 分支。",
                self._path,
            )
        return _StubAny(self._path + "()")

    def __int__(self) -> int:
        return 0

    def __index__(self) -> int:
        return 0

    def __bool__(self) -> bool:
        return False

    def __iter__(self):
        return iter(())

    def __repr__(self) -> str:
        return f"<win32 stub {self._path}>"


class _StubModule(types.ModuleType):
    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.__path__ = []  # 让 `import comtypes.client` 这类写法走到子模块查找

    def __getattr__(self, item: str):
        if item.startswith("__") and item.endswith("__"):
            raise AttributeError(item)
        return _StubAny(f"{self.__name__}.{item}")


def _fake_pyappify() -> types.ModuleType:
    """pyappify 装不上时的替身：只提供 ok-script 会读的那几个属性。"""

    module = types.ModuleType("pyappify")
    module.app_version = None
    module.app_profile = None
    module.pyappify_version = None
    module.pyappify_upgradeable = False
    module.pyappify_executable = None
    module.logger = logger

    def _noop(*args, **kwargs):
        return None

    module.kill_pyappify = _noop
    module.restart = _noop
    module.check_update = _noop

    def _getattr(name: str):
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        logger.debug("pyappify 桩：未定义的属性 %s 被读取，返回 None", name)
        return None

    module.__getattr__ = _getattr  # PEP 562
    return module


def install(verbose: bool = True) -> list[str]:
    """安装垫片；返回被替换掉的模块名。在 Windows 上什么都不做。"""

    if sys.platform == "win32":
        return []
    if getattr(install, "_done", False):
        return list(_installed)

    import ctypes

    # ctypes 上的 Windows 入口
    if not hasattr(ctypes, "WinDLL"):
        ctypes.WinDLL = lambda *args, **kwargs: _StubModule("ctypes.WinDLL")
    if not hasattr(ctypes, "windll"):
        ctypes.windll = _StubModule("ctypes.windll")
    if not hasattr(ctypes, "oledll"):
        ctypes.oledll = _StubModule("ctypes.oledll")
    if not hasattr(ctypes, "WinError"):
        ctypes.WinError = OSError  # rotypes 里 `from ctypes import WinError`
    if not hasattr(ctypes, "FormatError"):
        ctypes.FormatError = lambda code: f"WinError {code}"

    for name in _WIN_MODULES:
        if name in sys.modules:
            continue
        try:
            __import__(name)
            continue  # 真装了（比如 Wine 里的 python），就用真的
        except Exception:
            pass
        sys.modules[name] = _StubModule(name)
        _installed.append(name)

    # `from ctypes import wintypes` 在 macOS 上也会失败（依赖 WINFUNCTYPE）
    try:
        import ctypes.wintypes  # noqa: F401
    except Exception:
        stub = _StubModule("ctypes.wintypes")
        sys.modules["ctypes.wintypes"] = stub
        ctypes.wintypes = stub  # type: ignore[attr-defined]
        _installed.append("ctypes.wintypes")

    # ok-script 顶层 `import pyappify`；装不上就给替身
    try:
        __import__("pyappify")
    except Exception:
        sys.modules["pyappify"] = _fake_pyappify()
        _installed.append("pyappify")

    install._done = True  # type: ignore[attr-defined]
    if verbose and _installed:
        logger.info("macOS 垫片已安装：%s", ", ".join(_installed))
    return list(_installed)


def stubbed() -> list[str]:
    return list(_installed)
