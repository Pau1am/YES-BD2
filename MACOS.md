# macOS (Apple Silicon) 运行说明

这个分支让 YES-BD2 在 Mac 上跑，游戏放在安卓模拟器里、通过 ADB 控制。
挂机时物理鼠标键盘完全不参与，电脑可以照常用。

## 和上游的关系

只新增文件，对上游原有文件的改动只有一处：

| 文件 | 改动 |
|---|---|
| `src/config.py` | 把 7 个 Windows 专用导入/安装调用放进 `if sys.platform == "win32"`（非 Windows 下留同名空函数） |
| 其余全部 | 新增文件，不碰上游 |

新增文件：

| 文件 | 作用 |
|---|---|
| `win32_shim.py` | 把 macOS 上不存在的 win32 模块换成桩，让 ok-script 能 import |
| `main_macos.py` | 入口；`--selftest` 是体检 |
| `src/macos/adb.py` | ADB 通道：截图（原始 RGBA）、点击、滑动、启动游戏 |
| `src/macos/patches.py` | 运行期替换 ok-script 的 6 处行为（每处都标注了上游函数名） |
| `src/macos/config.py` | 把配置里的 `windows` 设备段换成 `adb` 段 |
| `requirements-macos.txt`、`scripts/install_macos.sh` | 安装 |

上游更新后合并：

```bash
git remote add upstream https://github.com/nobell001/YES-BD2.git
git fetch upstream
git merge upstream/main
```

冲突预期：只有 `src/config.py` 那一处可能冲突。如果 ok-script 升级后行为变了，
`src/macos/patches.py` 里每处替换都会打日志，按日志里的上游函数名核对即可。

## 前置

| 项 | 要求 |
|---|---|
| 系统 | macOS 12+，Apple Silicon |
| Python | 3.12（`brew install python@3.12`） |
| adb | `brew install android-platform-tools` |
| 模拟器 | BlueStacks Air |
| 模拟器设置 | 设置 → 高级 → 启用 **Android Debug Bridge**（端口 5555） |
| 分辨率 | **1920×1080、横屏**（工具按这个尺寸标定模板） |
| 游戏 | 安卓版棕色尘埃2（`com.neowizgames.game.browndust2`），语言切简体中文 |
| 路径 | 安装目录不能有中文（ok-script 的限制） |

## 安装与运行

```bash
bash scripts/install_macos.sh     # 建 venv、装依赖、跑体检
source .venv/bin/activate
python main_macos.py              # 开界面
python main_macos.py --selftest   # 只体检
python main_macos.py --headless   # 无界面
```

可用的环境变量 / 参数：

| 选项 | 默认值 | 说明 |
|---|---|---|
| `--adb` / `OK_BD2_ADB` | 自动查找 | adb 可执行文件路径 |
| `--serial` / `OK_BD2_ADB_SERIAL` | 自动选第一个在线设备 | 例如 `127.0.0.1:5555` |
| `--package` / `OK_BD2_ADB_PACKAGE` | `com.neowizgames.game.browndust2` | 游戏包名 |
| `--no-launch` | 关 | 启动时不自动把游戏拉到前台 |
| `--headless` | 关 | 不开界面 |

## 已知限制

| 限制 | 说明 |
|---|---|
| 模板兼容性 | 识别模板来自 PC 客户端。手机端 UI 若有差异，需要重截；`--selftest` 最后会打印几张模板的匹配分数，<0.6 就要重标 |
| 截图延迟 | ADB 取帧约 100–300 ms（已用原始 RGBA 代替 PNG）。回合制够用，连招类任务会吃力 |
| 键盘走位 | 「舞台移动方式」需保持默认的「鼠标点击舞台」，不要选 WASD（模拟器没有键盘） |
| 救赎之塔 | 该任务靠按住 W/A/S/D 走到祭坛，ADB 发不出按住事件，macOS 版**不提供**（已从任务列表和一键日常里移除） |
| 定时启动 | 依赖 Windows 任务计划程序，macOS 版不可用；界面上的开关不会生效 |
| 桌面分身 | 该功能依赖 Windows 远程桌面，macOS 上不可用（也不需要：模拟器本身就是独立窗口） |
| 自动更新 | pyappify 的在线更新是 Windows 的；macOS 版请用 `git pull` 更新源码 |
| 管理员权限 | 不需要 |

## 故障排查

| 现象 | 处理 |
|---|---|
| `--selftest` 报「没有在线的安卓设备」 | BlueStacks Air 设置里开 ADB；`adb connect 127.0.0.1:5555`；`adb devices` 确认状态是 `device` |
| 报「游戏包未安装」 | 在模拟器里用 Play 商店装好游戏并登录一次 |
| 能截图但识别不到东西 | 确认分辨率 1920×1080、横屏、游戏语言简中、没有遮挡画面 |
| 点击没反应 | 前台不是游戏。工具会在点击前自动切前台；若持续失败，检查是否有权限弹窗盖住游戏 |
| 启动报「must be an English path」 | 把整个目录移到纯英文路径，例如 `~/apps/yes-bd2-macos` |
| 界面打不开但 `--headless` 正常 | Qt 在 macOS 上的兼容问题，先用 `--headless` 跑，把报错贴出来 |
