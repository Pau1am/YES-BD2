"""在 macOS 上给 ok-script 组装一份「ADB 设备」版配置。

做法：仍然导入上游的 `src.config.config`（保持所有任务、模板、界面的注册不变），
     只把设备那一段从 `windows` 换成 `adb`，其余原样。
这样上游往 config 里加任务、改界面，你都自动继承。
"""

from __future__ import annotations

import copy
import logging
import sys

from src.macos.adb import DEFAULT_PACKAGE

logger = logging.getLogger("bd2.macos.config")


def build(
    *,
    use_gui: bool = True,
    debug: bool = False,
    package: str | None = None,
) -> dict:
    from src.config import config as upstream

    config = dict(upstream)

    windows = config.pop("windows", None)
    if windows is not None:
        logger.info(
            "macOS：移除 windows 设备配置（截图方式=%s），改用 adb 设备",
            windows.get("capture_method"),
        )

    config["adb"] = {"packages": [package or DEFAULT_PACKAGE]}
    config["use_gui"] = bool(use_gui)
    config["check_mutex"] = False  # 命名互斥体是 Windows 的；macOS 用不到
    config["debug"] = bool(debug)

    # 去掉依赖键盘 WASD 的任务（ADB 发不出按住事件），见 src/macos/patches.py
    from src.macos.patches import KEYBOARD_ONLY_TASKS

    tasks = config.get("onetime_tasks") or []
    kept = [
        entry
        for entry in tasks
        if not (
            isinstance(entry, (list, tuple))
            and len(entry) >= 2
            and str(entry[1]) in KEYBOARD_ONLY_TASKS
        )
    ]
    if len(kept) != len(tasks):
        logger.info("macOS：任务列表去掉 %d 个键盘任务", len(tasks) - len(kept))
        config["onetime_tasks"] = kept

    # OCR 后端：Apple Silicon 上没有可用的 Intel NPU，走 CPU
    ocr = copy.deepcopy(config.get("ocr") or {})
    for entry in ocr.values():
        params = entry.get("params")
        if isinstance(params, dict):
            params["use_openvino"] = False
            params["use_npu"] = False
    if ocr:
        config["ocr"] = ocr

    if sys.platform != "darwin":
        logger.warning("当前不是 macOS（%s），仍按 macOS 方式启动，仅供调试", sys.platform)
    return config
