# macOS 兼容性分析与验证边界

## 结论

音乐后端无需整体重写：音符/MIDI/XML 处理、块规划、关联素材、情绪曲线及连接算法采用 Python、mido、NumPy，可共用。WAV 渲染仍需要 Mac 本机的 LMMS；不能使用 Windows 包中的 `lmms.exe`。LMMS 官方提供 Mac 构建，请从 [官方 Releases](https://github.com/LMMS/lmms/releases) 选择适合 Intel/Apple Silicon 的包。

2026-10-03 已在 Apple Silicon Mac 上完成 Python/Tk 启动、完整测试和 LMMS 原生 WAV 渲染。Finder 拖入、Retina 布局及人工试听仍待交互验证；自动化测试和生成 WAV 不能证明这些体验。

## 已处理的原障碍

| 原问题 | 当前处理 |
| --- | --- |
| LMMS 和鼓采样绑定 Windows 目录 | 自动查找 Mac app bundle；支持环境变量覆盖 |
| 子进程 Windows 隐藏窗口参数 | 非 Windows 默认使用 creationflags=0 |
| winsound / MCI / Win32 直接耦合界面 | 播放、拖入、窗口 API 隔离为平台适配器 |
| 输出写入旧源代码目录 | 统一 `data/`，可另设可写目录 |
| 音频转 MIDI 环境仅识别 Scripts/python.exe | 同时识别 bin/python 和显式解释器配置 |
| Windows 字体、滚轮、右键、窗口按钮 | Mac 原生标题栏、字体映射、滚轮和 Control-click |

## 本机配置

推荐 Python 3.11；基础依赖支持 Python 3.9–3.12，需 Tk 可用。默认 LMMS 执行文件为 `/Applications/LMMS.app/Contents/MacOS/lmms`，也尝试大小写不同的 `LMMS`。这一执行文件布局可参考 [LMMS 官方编译说明](https://github.com/LMMS/lmms/wiki/Compiling)。

采样查找候选为 app bundle 内 `Contents/Resources`、`Contents/Resources/data` 及共享资源目录。不同构建的资源位置可能不同，诊断不通过时显式设置真实路径（下例仅示意，必须以本机存在目录为准）：

```bash
export EMOBLOCKS_LMMS="/Applications/LMMS.app/Contents/MacOS/lmms"
export EMOBLOCKS_LMMS_DATA="/Applications/LMMS.app/Contents/Resources"
export EMOBLOCKS_DATA_DIR="$HOME/Documents/EmoBlocksData"
python scripts/doctor.py
```

`EMOBLOCKS_LMMS_DATA` 应包含 `samples/drums/bassdrum01.ogg`、`snare01.ogg`、`hihat_closed01.ogg`；实际诊断必须找到这三个文件。音乐工程只使用 TripleOscillator 与这些鼓采样，不依赖 Windows VST。

Tk 9 将双指触控板滚动作为 `TouchpadScroll` 事件发送，不再作为 `MouseWheel` 发送。共享界面现在同时处理两种事件：精细页面纵向滚动，快速模式的情绪积木时间线横向滚动；时间线使用 1 像素滚动精度，拖拽边缘自动滚动仍保持原速度。Windows 旧版 Tk 的鼠标滚轮路径保留。2026-10-05 在本机 Tk 9 控件上通过自动化滚动测试，触控板手势的主观速度和惯性仍需人工体验检查。

2026-10-05 的共享界面操作调整同时适用于 Mac 与 Windows：素材卡单击仅选中，播放按钮才试听；界面分别显示编辑稿是否与最新快速成品一致、实际播放来源和所选成品版本。新生成版本记录时间及相对上一快速版本的高层修改摘要，导出文件名和对话框标明所选版本。旧工程缺少生成时间或快照文件时会明确显示“未记录”或“不可用”，不会猜测。试听侧栏在小窗口下压缩历史卡、波形和块卡高度，保证播放及导出控件可见。两端共享逻辑测试已通过；Windows 实际界面与双端人工流程验收仍待完成。

Finder 拖入采用 [tkinterdnd2](https://github.com/pmgagne/tkinterdnd2)。如果 TkDND 与本机 Tk/架构不匹配，程序退回普通 Tk，仍可使用“导入”选文件；拖入需要单独验证。WAV 试听使用 Mac 专属的 `sounddevice` 音频流；片段按帧读取，暂停输出静音而不停止设备，播放、暂停、恢复及重播边界采用约 12 毫秒淡入淡出。播放位置按已提交给音频缓冲区的帧数计算，可能比实际听到的声音略提前。

音频转 MIDI 是可选大型依赖，独立安装 Basic Pitch 并用 `EMOBLOCKS_BASIC_PITCH_PYTHON` 指定解释器；Mac 原生转写未验证，不影响默认 MIDI / MMP 工作流。

## 验证记录与 Mac 实测步骤

Windows 基线曾验证音乐逻辑与后端独立导入，并通过模拟 afplay 验证片段播放行为。2026-10-03 在 Apple Silicon Mac 上，Python 3.11.16 / Tk 9.0 使用用户目录中的 LMMS 1.3.0-alpha.2 完成原生验证：290 项测试通过，`scripts/check_frontends.py` 通过，`scripts/doctor.py --render` 生成了 44.1 kHz、27 秒的非静音 WAV，报告状态为 `complete`。`run.py` 启动后事件循环保持运行，但尚未完成人工界面交互及试听验证。Tk 9 对未选中 Combobox 的 `current()` 行为与旧版不同，已经做兼容处理；LMMS 1.3 不接受旧渲染命令的 `-x` 参数，现已移除。

2026-10-05 因旋律素材暂停和重播出现杂音，移除了 Mac 播放器对 `afplay` 进程的 `SIGSTOP` / `SIGCONT` 控制，并改用持续音频流与淡入淡出。293 项完整测试、246 项无窗口测试及双平台契约检查通过；本机扬声器上的静音 WAV 播放、暂停、恢复和重播无设备错误。真实旋律的人工听感仍需复核。

Mac 后续回归检查：

```bash
python scripts/check_frontends.py
python scripts/test.py --backend-only
python scripts/doctor.py
python scripts/doctor.py --render
python run.py
```

随后检查亮/暗主题、旋律导入、Finder 拖入、块拖拽、情绪绘制与强度点拖拽、生成/分块试听、暂停和拖动进度、保存重开、WAV/MIDI/MMP 导出，以及关闭窗口无残留播放。完整 GUI 测试可运行 `python scripts/test.py`（需要桌面环境）。
