# EmoBlocks · 音乐积木

输入一段或多段旋律，以“情绪种类 + 连续程度曲线”规划音乐故事：发展关联素材、选用旋律与情感变体、保护原旋律记忆点、安排连接块，生成可编辑工程及连续音乐。

本仓库以 **EmoBlocks-Windows-20260926-UI-v2** 为基准整理。当前为离线规则工作流 Demo，不是已接入生成式音乐模型的成品。Windows / macOS 共用界面及音乐后端，平台差异由适配器处理；Mac 完整原生运行尚待实机验证。

## 当前功能

- 快速成品与详细素材/编配/结构流程；支持多个 MIDI / MMP 旋律输入、用途设置及高/低声部选择。
- 内置欢乐颂主题；输入按四拍分块，块时长由 BPM 决定；素材与分块展示、试听、暂停及可拖动进度。
- 平静、希望、悲伤、悬疑、紧张、振奋六种情绪；框选/涂色情绪段、整块吸附、曲线点强度拖动、平滑程度曲线与时间线长度调整。
- 主题顺序保护、变体/回答句/关联素材发展、情绪版本选用、块内表达变化、旋律保持连接、独立连接块 / bridge、连接与结尾设计。
- 固定时间锚点与最高程度自动原旋律记忆点；保护高表达段落，优先使用较弱区域进行过渡。
- 素材卡片、块拖拽/交换与归位动画；编辑后自动生成拼接预览，显示旋律来源和第几块。
- 生成结果波形与分块试听、当前播放块同步高亮、试听历史；保存/重开工程和 WAV / MIDI / MMP 导出。
- 默认浅色 B / 可切换深色 A，统一卡片按钮与响应式缩放。Windows 自绘无边框窗口；Mac 原生窗口、字体和快捷键适配。
- 可选 Basic Pitch 音频转 MIDI；不保证复杂混音能可靠提取主旋律，也未验证 Mac 原生转写。

## 积木创作交互（2026-10-01 更新）

1. 导入旋律，点击素材卡片或“分块组合”，分块在素材下方展开，不再打开分块窗口。点击分块多选，Shift 连选；▶ 单块试听不会清空多选。
2. 点击“组成积木”，按原顺序拼接选中的四拍块；可选择不相邻块。尾部不足四拍时补休止，不拉伸节奏。新积木留在“我的旋律积木”库，可重复使用。
3. 选中积木，在内联设置栏选情绪颜色；拖到下面旋律轨，松开吸附到四拍格。绿色/主题色外框表示可放置，红色表示碰撞或超长。也可选中库积木按回车放入第一个空位。
4. 已摆放积木指定的是该位置的**主旋律**，不是固定音频或固定编配。音色、和声、伴奏、节奏密度和力度仍按情绪种类与连续程度变化；“原旋律”保留主旋律音高与节奏，“简单变体”允许少量调内邻音变化，两者都参与情绪编配。积木可以移动、改情绪或移除；至少三块长可允许首尾各一块参与连接，中间主旋律不被连接块替换。关闭“首尾连接”只保护整段主旋律，不关闭情绪处理。改变库积木颜色不改变已经摆放的副本。
5. 建议先设计整首情绪：选颜色，再切到“手绘情绪线”，在程度曲线区按住左键绘制。松开识别为四拍情绪段和每块中点的程度值，再平滑显示。切回“选择 / 拖动”才能拖程度点；两种手势分离。积木自己的情绪优先，程度仍跟随这条曲线。
6. 点击“生成连续成品”，保留已指定的主旋律，按情绪线补齐所有未摆放的时间，再做连接和全曲情绪编配、连续渲染。时间线的“空位”是未指定旋律，不是人为预留静音或连接时间。默认情绪线已覆盖全曲，不强迫必须手绘。“仅主旋律”是用于诊断旋律连续性的特殊试听模式，会主动关闭情绪配器；正常成品生成应保持它未勾选。

选择、多选、移动失败反馈、Esc 取消、Delete 移除、Ctrl+Z 撤销、保存重开及亮暗主题均保留；Mac 使用 Command+Z。分块和积木库可横向滚动，小窗口下素材区自动出现垂直滚动，避免下方控件被裁切。新工作流没有新增独立业务窗口，原精细流程仍可使用。当前仍是规则 Demo；完整商业产品的 Mac 真机和长期使用验证尚待进行。

完整基准功能说明：[UI-v2 原版说明](docs/UI-v2-original-README.md)；历史实现与限制：[功能历史](docs/design/Current-Features-and-History.md)。旧说明中的路径/启动命令请以本文为准。

## Windows 运行

需要 Python 3.9–3.12（推荐 3.11，包含 Tk）与本机 LMMS。源码 Git 不包含 LMMS 安装器/可执行文件。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
# LMMS 不在自动查找目录时，设置本机真实路径：
$env:EMOBLOCKS_LMMS = 'C:\Program Files\LMMS\lmms.exe'
.\.venv\Scripts\python.exe scripts/doctor.py
.\.venv\Scripts\python.exe run.py
```

安装依赖后可双击 `frontend/windows/Launch.cmd`。本机保留的 `outputs/EmoBlocks/launch.vbs` 旧入口已转发到新源码，不必修改原桌面快捷方式。

## macOS 运行

安装含 Tk 的 Python 和适合本机架构的 [LMMS Mac 版](https://github.com/LMMS/lmms/releases)，建议放在 `/Applications/LMMS.app`。详情：[Mac 兼容性与验证边界](docs/macos-portability.md)。

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-macos.txt
python scripts/doctor.py
python run.py
```

依赖就绪后可双击 `frontend/macos/Launch.command`，或在终端执行 `bash frontend/macos/Launch.command`。如果 LMMS 或采样未找到，按兼容性文档设置 `EMOBLOCKS_LMMS` / `EMOBLOCKS_LMMS_DATA`。Finder 拖入不可用时仍可点“导入”选择文件。

## 独立后端与验证

```bash
python backend/cli.py                # 默认旋律与情绪线，输出排布 JSON，不加载界面
python backend/cli.py --project story.json --output plan.json
python backend/cli.py --render       # 需要 native LMMS，生成连续 WAV / MIDI / MMP
python scripts/check_frontends.py    # 双平台接口和依赖边界
python scripts/test.py --backend-only
python scripts/test.py               # 完整回归，需要桌面/Tk
python scripts/doctor.py --render    # 真实本机渲染检查
```

CLI 接受独立 story JSON（可取生成目录中的 `story.json`），不是旧 studio 工程的包装格式。新工程和结果保存在 `data/`；可用 `EMOBLOCKS_DATA_DIR` 指定其他可写目录。

音频转 MIDI 为可选独立环境：在 `work/basic-pitch-venv` 安装 `requirements-basic-pitch.txt`，或用 `EMOBLOCKS_BASIC_PITCH_PYTHON` 指定含 Basic Pitch 的 Python；基础 MIDI / MMP 工作流不依赖它。

## 目录与文档

```text
frontend/shared/                 通用界面与交互
frontend/windows/                Windows 平台适配与启动
frontend/macos/                  macOS 平台适配与启动
backend/core/, step1/, step2/     规划、音乐处理、素材发展
assets/samples/                  演示 MIDI / MMP
tests/, scripts/                 回归、契约检查与本机诊断
docs/                            设计与迁移记录
```

- [架构及 Git 树](docs/architecture.md)
- [产品 Idea](docs/design/EmoBlocks-idea-overview.md)
- [实现计划](docs/design/EmoBlocks-implementation-goals.md)
- [开发交接](docs/design/EmoBlocks-handover.md)
- [2026-10-01 验证记录](docs/verification-20261001.md)
- [GitHub 上传说明](docs/github-upload.md)
- [开发约定：每次前端改动必须同步两平台](AGENTS.md)

原发布包、旧 `outputs/`、`work/`、用户生成音频及虚拟环境均保留本地，不纳入 Git。默认主题来源见 [素材说明](assets/samples/DEFAULT-MELODY.md)。项目许可证尚待所有者选择；第三方工具遵循各自许可证。
