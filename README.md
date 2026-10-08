# EmoBlocks · 音乐积木

导入旋律，将四拍分块排列在情绪强度画布中，通过素材发展、记忆保护、Bridge 和局部连接形成可保存、试听和导出的作品。

当前入口 `run.py` 为三栏 Curve 工作流：左侧素材来源、中栏分块与组合、右侧唯一强度画布及共用播放器。Windows/macOS 使用同一份界面和音乐后端，由配对适配器处理平台差异。

## 主线验证状态

`codex/windows-validation-20261008` 是待 Windows 实机验证的主线候选，代码来源为 `14df7e8`，包含已知 UI 问题。**R8 提示修复 PASS，整体 UI 验收仍 FAIL**：最小窗口展开详情时画布高度不足，以及一次 Text Backspace 完整测试失败尚未归因。当前643项后端测试和配对契约检查通过；不代表 Windows、物理输入或人工音乐听感通过。

- [Windows 启动、验收与开发交接](docs/handover/windows-validation-20261008.md)
- [验证范围与证据摘要](docs/handover/mainline-validation-20261008.json)
- [下一轮 UI 已确认计划，尚未实现](docs/design/ui-mainline-next-plan-20261008.md)

F05/F06、MusicVAE、新哼唱和录音链路继续在隔离分支开发，本候选未纳入。当前为规则音乐工作流；后续模型接入须保留工程与生成接口约束。

## 当前工作流

- MIDI/MMP 来源按四拍分块，末尾保留实际长度；素材保存音符和来源快照，支持规则新旋律、整句及手动组合。
- 先设固定时间轴、编辑或手绘强度线，再拖入素材；可留空缺或主动留白。移动/删除不压缩时间轴，重叠和越界拒绝。
- 每次放置可设置情绪，保留峰值记忆及选用素材版本；自动补全和推荐遵守保护与时长约束。
- 完整候选先补全，再判断并保护全曲 Bridge 位置，生成 Bridge 和连接块，最后处理块间连接和整曲编配。
- 基础/处理后、单旋律/编配模式通过明确操作共用底部播放器；采用对应候选快照，支持撤销、保存重开及 MIDI/MMP/WAV 输出。
- Soft UI 明亮和静态 Vibrancy 暗色主题、统一类型色素材卡、拖放反馈、真实波形、块导航、自动隐藏滚动条及四拍长度加减。

旧版“快速成品/精细创作”、涂色情绪和完整主题选择等说明属于历史，不代表当前默认入口。历史实现见 [功能历史](docs/design/Current-Features-and-History.md) 和 [UI-v2 原版说明](docs/UI-v2-original-README.md)。

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
