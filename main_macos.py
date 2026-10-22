#!/usr/bin/env python3
"""YES-BD2 的 macOS 入口（ADB 版）。

和 main.py 的区别只有一个：设备从「Windows 游戏窗口」换成「安卓模拟器 + ADB」。
界面、任务、模板、识别逻辑全部复用上游，一行没改。

用法：
    python3 main_macos.py                 # 开界面（正常挂机用这个）
    python3 main_macos.py --selftest      # 只做体检，不开界面，用来定位问题
    python3 main_macos.py --headless      # 无界面跑（调试/服务器）
    python3 main_macos.py --adb ~/adb --serial 127.0.0.1:5555

环境变量：OK_BD2_ADB / OK_BD2_ADB_SERIAL / OK_BD2_ADB_PACKAGE
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# 必须在 import ok / import src 之前
import win32_shim  # noqa: E402

win32_shim.install()

from src.macos import adb as adb_module  # noqa: E402


def _banner() -> None:
    print("YES-BD2 · macOS (ADB) 版")
    print(f"  python {sys.version.split()[0]}  {sys.platform}")
    print(f"  工作目录 {ROOT}")


def _template_probe(adb: adb_module.Adb, frame) -> None:
    """顺手比几张模板，判断 PC 模板在手机端还能不能用。"""

    try:
        import cv2
    except ImportError:
        print("  （没装 opencv，跳过模板检查）")
        return
    root = ROOT / "recognition-assets" / "template-assets"
    names = ["back.png", "home.png", "Q_pvp.png", "browndustx.png"]
    screen = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    print("\n模板兼容性（分数越高越可用；<0.6 说明手机端 UI 与 PC 端不同）")
    for name in names:
        path = root / name
        if not path.is_file():
            hits = list(root.rglob(name))
            if not hits:
                continue
            path = hits[0]
        template = cv2.imdecode(
            __import__("numpy").fromfile(str(path), dtype="uint8"), cv2.IMREAD_GRAYSCALE
        )
        if template is None:
            continue
        best = (0.0, 1.0)
        for scale in (0.8, 0.9, 1.0, 1.1, 1.2):
            height = int(template.shape[0] * scale)
            width = int(template.shape[1] * scale)
            if height < 8 or width < 8 or height > screen.shape[0] or width > screen.shape[1]:
                continue
            resized = cv2.resize(template, (width, height), interpolation=cv2.INTER_AREA)
            result = cv2.matchTemplate(screen, resized, cv2.TM_CCOEFF_NORMED)
            _, score, _, _ = cv2.minMaxLoc(result)
            if score > best[0]:
                best = (float(score), scale)
        verdict = "可用" if best[0] >= 0.8 else ("勉强" if best[0] >= 0.6 else "需重标")
        print(f"  {path.name:<24} 最高 {best[0]:.3f} @ x{best[1]:.1f}  → {verdict}")


def selftest(adb: adb_module.Adb) -> int:
    """体检：每一步都打印结果，最后给结论。返回 0 = 全部通过。"""

    failures: list[str] = []
    warnings: list[str] = []

    print("\n[1/8] adb")
    if not adb.available():
        print("  ✗ 找不到 adb。brew install android-platform-tools")
        return 2
    version = adb.run("version")
    print(f"  ✓ {adb.exe}")
    print(f"    {str(version or '').strip().splitlines()[0] if version else ''}")

    print("\n[2/8] 设备")
    devices = adb.devices()
    if not devices:
        print("  ✗ 没有设备。先开 BlueStacks Air，并在设置里启用 ADB")
        print("    然后：adb connect 127.0.0.1:5555")
        failures.append("没有在线的安卓设备")
    else:
        for serial, state in devices:
            print(f"  · {serial}  {state}")
        print(f"  ✓ 使用 {adb.serial}")

    if adb.serial:
        print("\n[3/8] 分辨率")
        size = adb.wm_size()
        if size:
            print(f"  · {size[0]}x{size[1]}")
            if (size[0], size[1]) != (1920, 1080):
                print("  ⚠ 工具按 1920x1080 标定模板，其他分辨率要靠模板缩放兜底")
                warnings.append("分辨率不是 1920x1080")
        density = adb.shell("wm", "density")
        print(f"  · {str(density or '').strip()}")

        print("\n[4/8] 游戏包")
        if adb.installed():
            print(f"  ✓ 已安装 {adb.package}")
        else:
            print(f"  ✗ 模拟器里没装 {adb.package}")
            failures.append("游戏包未安装")

        print("\n[5/8] 运行状态")
        pid = adb.pidof()
        front = adb.foreground_package()
        print(f"  · pid={'有' if pid else '无'}   前台={front or '未知'}")
        if pid is None:
            print("  ⚠ 游戏没在跑，下面会尝试启动")
            adb.start_package()
            time.sleep(3)
            pid = adb.pidof()
            print(f"  · 启动后 pid={'有' if pid else '仍然没有'}")
        if front and front != adb.package:
            print("  ⚠ 前台不是游戏，点击会打到别处（工具运行时会自动切前台）")

        print("\n[6/8] 截图速度")
        samples: list[float] = []
        frame = None
        for _ in range(5):
            start = time.perf_counter()
            frame = adb.screencap()
            samples.append((time.perf_counter() - start) * 1000)
        if frame is None:
            print("  ✗ 截图失败")
            failures.append("截图失败")
        else:
            median = sorted(samples)[len(samples) // 2]
            print(f"  ✓ {frame.shape[1]}x{frame.shape[0]}  中位 {median:.0f} ms")
            if median > 350:
                print("  ⚠ 偏慢：回合制能忍，连招会吃力")
                warnings.append(f"截图中位 {median:.0f}ms")
            try:
                import cv2

                out = ROOT / "logs" / "macos-selftest.png"
                out.parent.mkdir(exist_ok=True)
                cv2.imwrite(str(out), frame)
                print(f"    截图已存 {out}")
            except Exception:
                pass
            _template_probe(adb, frame)

        print("\n[7/8] 点击")
        if frame is not None:
            height, width = frame.shape[:2]
            start = time.perf_counter()
            sent = adb.tap(width / 2, height / 2)
            print(f"  {'✓' if sent else '✗'} 点了一下屏幕正中（{width // 2},{height // 2}）"
                  f"  {1000 * (time.perf_counter() - start):.0f} ms")

    print("\n[8/8] 工具导入链")
    try:
        from src.macos import patches

        patches.install(adb)
        from src.macos.config import build

        config = build(use_gui=False)
        print(f"  ✓ 配置组装成功，设备段={list(config.get('adb', {}))}，"
              f"任务 {len(config.get('onetime_tasks', []))} 个")
        if "windows" in config:
            print("  ✗ 配置里还留着 windows 段，设备会选错")
            failures.append("配置未清理 windows 段")
    except Exception as exc:  # noqa: BLE001
        print(f"  ✗ 导入失败：{exc}")
        import traceback

        traceback.print_exc()
        failures.append(f"导入链失败：{exc}")

    print("\n" + "=" * 60)
    if failures:
        print("结论：还不能跑，先解决：")
        for item in failures:
            print(f"  ✗ {item}")
        return 2
    print("结论：环境通过。可以 python3 main_macos.py 开界面了。")
    for item in warnings:
        print(f"  ⚠ {item}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="YES-BD2 macOS (ADB) 启动器")
    parser.add_argument("--adb", help="adb 可执行文件路径")
    parser.add_argument("--serial", help="设备序列号，如 127.0.0.1:5555")
    parser.add_argument("--package", help=f"游戏包名，默认 {adb_module.DEFAULT_PACKAGE}")
    parser.add_argument("--selftest", action="store_true", help="只体检，不开界面")
    parser.add_argument("--headless", action="store_true", help="不开界面")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--no-launch", action="store_true", help="不自动启动游戏")
    args = parser.parse_args()

    _banner()
    adb = adb_module.Adb(
        exe=args.adb,
        serial=args.serial,
        package=args.package or adb_module.DEFAULT_PACKAGE,
    )
    connected, message = adb.bootstrap()
    print(f"\n设备：{message}")

    if args.selftest:
        return selftest(adb)

    if not connected:
        print("\n没有连上设备。先用 --selftest 看看卡在哪一步。")
        if not args.headless:
            print("（仍会打开界面，但识别不了游戏）")

    # adbutils 内部也走 adb，告诉它用哪一个
    if adb.exe:
        os.environ["ADBUTILS_ADB_PATH"] = adb.exe

    from src.macos import patches  # noqa: PLC0415

    patches.install(adb)
    if connected and not args.no_launch:
        try:
            patches.start_game_if_needed(adb)
        except Exception as exc:  # noqa: BLE001
            print(f"启动游戏失败（可以在模拟器里手动打开）：{exc}")

    from src.macos.config import build  # noqa: PLC0415

    config = build(use_gui=not args.headless, debug=args.debug, package=args.package)

    import ok as ok_pkg  # noqa: PLC0415

    app = ok_pkg.OK(config)
    app.start()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
