# macOS 兼容性分析与验证边界

## 结论

音乐后端无需整体重写：音符/MIDI/XML 处理、块规划、关联素材、情绪曲线及连接算法采用 Python、mido、NumPy，可共用。WAV 渲染仍需要 Mac 本机的 LMMS；不能使用 Windows 包中的 `lmms.exe`。LMMS 官方提供 Mac 构建，请从 [官方 Releases](https://github.com/LMMS/lmms/releases) 选择适合 Intel/Apple Silicon 的包。

此次已做代码适配，但执行环境为 Windows。Mac 真机启动、实际音频输出、Finder 拖入、Retina 布局及本机 LMMS 渲染 **尚未实测**。CI 的 Mac 无窗口测试也不等同于完整 GUI / 音频测试。

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

Finder 拖入采用 [tkinterdnd2](https://github.com/pmgagne/tkinterdnd2)。如果 TkDND 与本机 Tk/架构不匹配，程序退回普通 Tk，仍可使用“导入”选文件；拖入需要单独验证。WAV 播放采用系统 `/usr/bin/afplay`，片段播放通过临时 WAV 截取实现，暂停/恢复通过进程信号，结束后清理临时文件。播放位置为单调时钟估计，尚不是硬件采样级精确定位。

音频转 MIDI 是可选大型依赖，独立安装 Basic Pitch 并用 `EMOBLOCKS_BASIC_PITCH_PYTHON` 指定解释器；Mac 原生转写未验证，不影响默认 MIDI / MMP 工作流。

## 验证记录与 Mac 实测步骤

2026-10-01 新增的内联分块、多选组成旋律积木、时间线拖放吸附、内联颜色/变体设置和手绘情绪识别，都实现在 `frontend/shared/composer_ui.py` 与共享 StoryPage 中。Windows/macOS 使用完全相同的交互逻辑，无新增 Win32 依赖；多选仅使用通用 Shift 状态，手绘使用跨平台 crosshair 光标。新增旋律积木模型位于后端 `brick_model.py`，不导入 Tk。Mac 的原生拖放、鼠标捕获及真实显示仍需按下述流程实测。

“指定主旋律，情绪可变”的文案和说明也位于共享前端，两端同步：保护主旋律不被连接替换，不等于关闭音色、伴奏、和声或力度变化。本次不改变平台适配器接口。

本次在 Windows 验证音乐逻辑与后端独立导入；通过模拟 afplay 验证截取帧数、暂停/恢复计时、播放结束和临时文件清理；用临时目录验证 Mac bundle 资源路径。模拟不会发出声音，也不能证明实际 macOS 播放成功。

Mac 需依次执行：

```bash
python scripts/check_frontends.py
python scripts/test.py --backend-only
python scripts/doctor.py
python scripts/doctor.py --render
python run.py
```

随后检查亮/暗主题、旋律导入、Finder 拖入、块拖拽、情绪绘制与强度点拖拽、生成/分块试听、暂停和拖动进度、保存重开、WAV/MIDI/MMP 导出，以及关闭窗口无残留播放。完整 GUI 测试可运行 `python scripts/test.py`（需要桌面环境）。
