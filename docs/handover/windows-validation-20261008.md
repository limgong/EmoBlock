# EmoBlocks Windows 主线验证与开发交接

日期：2026-10-08。对象：`codex/windows-validation-20261008` 分支。代码来源：`14df7e8c3fe3e803e1aa53deef210057bd4fb73c`。本分支用于 Windows 实机验证，包含已知问题，不代表 UI 或音乐听感验收通过。验收前记录本次实际下载的完整提交 SHA；PR 中的验证提交为版本依据。

## 主线范围与责任

本分支包含既有三栏工作流、固定四拍时间轴、单一强度画布、素材分块和组合、情绪与记忆保护、完整推荐、全曲 Bridge 分析、连接块及块间处理、共用播放器、保存和输出，以及 R6–R8 的现有 UI 修复。

本轮新增内容是交接说明和后续 UI 规格；产品源码与 R8 相同。下列功能仍在 Herdr 的独立 worktree 中，本次没有纳入：F05 明确选轨实验服务及 UI、F06 MusicVAE、F05/F06 组合后端、新哼唱 H1/H2、录音及输出释放屏障、异步录音 preflight、H3/H4/H5 接线。历史可选音频导入兼容代码不表示这些新功能已上线。

| 工作 | 负责人 | 交付规则 |
| --- | --- | --- |
| 主线集成、现有缺陷与新 UI | 接收方 Codex 当前聊天 | 独立分支开发；记录测试提交；负责主线合并 |
| Windows 实机、输入、设备与听感 | Windows partner | 固定 SHA 验收；按本表回报证据 |
| 额外功能隔离开发和独立验收 | Herdr | 交付提交、范围、契约、测试与缺口；不自动合入主线 |

原主线队列已停止 UI 派工和自动集成，相关恢复路径为 `WAITING_HANDOFF`。旧 UI R1–R8 记录保留。额外功能如需修改主线通用 UI、播放器或公共接口，先交付具体接口需求，由主线负责人安排集成。

## 当前版本与后续 UI 计划

当前版本仍有完整乐句卡、顶部新旋律选项、行内组合草稿及独立播放/暂停按钮。请按当前真实界面验收，不把后续计划当作已实现。

已确认的下一轮 UI 规格见 [主线 UI 后续计划](../design/ui-mainline-next-plan-20261008.md)。其重点是来源栏图标切换、仅分块展示、稳定短名、右键生成、简单组合确认、统一播放/暂停和完整候选补全预览。待验证基线明确后，由主线负责人分阶段实施。

## Windows 准备与启动

使用新的验证目录。需要 Git、含 Tk 的 Python 3.11、以及用于真实音频生成的本机 LMMS。无需安装 MusicVAE、Basic Pitch 或录音相关环境来验证本分支。

在 PowerShell 中执行以下命令。私有仓库需要使用有读取权限的 GitHub 登录；凭据由 Git 的登录机制处理。

```powershell
git clone --branch codex/windows-validation-20261008 --single-branch https://github.com/limgong/EmoBlock.git EmoBlock-Windows-Validation
Set-Location EmoBlock-Windows-Validation
$validationSha = (git rev-parse HEAD).Trim()
git switch --detach $validationSha
Write-Output "VALIDATION_SHA=$validationSha"

py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m tkinter

$env:EMOBLOCKS_DATA_DIR = Join-Path $env:LOCALAPPDATA ("EmoBlocks-validation\" + $validationSha.Substring(0,12))
New-Item -ItemType Directory -Force -Path $env:EMOBLOCKS_DATA_DIR | Out-Null
$evidenceDir = Join-Path $env:EMOBLOCKS_DATA_DIR 'evidence'
New-Item -ItemType Directory -Force -Path $evidenceDir | Out-Null

# 将路径改为本机实际安装位置。
$env:EMOBLOCKS_LMMS = 'C:\Program Files\LMMS\lmms.exe'
# 若自动查找不到鼓采样，改为实际包含 samples 子目录的资源目录。
# $env:EMOBLOCKS_LMMS_DATA = 'C:\Program Files\LMMS\data'

.\.venv\Scripts\python.exe scripts/doctor.py
.\.venv\Scripts\python.exe run.py
```

`python -m tkinter` 打开测试窗口后关闭它。`doctor.py` 的退出码为零不等于 LMMS 可用：同时检查 `lmms_found` 和采样路径。新打开的 PowerShell 需要重新设置环境变量；最直接的验证入口始终为 `run.py`。依赖就绪后也可用 `frontend/windows/Launch.cmd` 启动。

测试或更改分支前保存并关闭本次验证应用。完整 Tk 测试期间不要键入或操作其窗口。不要在验收过程中 `git pull` 切换测试代码；新修复需记录新 SHA，并重验相关项目。

## 自动检查与运行证据

```powershell
git rev-parse HEAD
.\.venv\Scripts\python.exe -c "import sys, tkinter; print(sys.version); print('Tk', tkinter.TkVersion)"
.\.venv\Scripts\python.exe scripts/check_frontends.py 2>&1 | Tee-Object (Join-Path $evidenceDir 'frontends.log')
.\.venv\Scripts\python.exe scripts/test.py --backend-only 2>&1 | Tee-Object (Join-Path $evidenceDir 'backend.log')
.\.venv\Scripts\python.exe scripts/test.py 2>&1 | Tee-Object (Join-Path $evidenceDir 'full.log')
.\.venv\Scripts\python.exe scripts/doctor.py 2>&1 | Tee-Object (Join-Path $evidenceDir 'doctor.log')
.\.venv\Scripts\python.exe scripts/doctor.py --render 2>&1 | Tee-Object (Join-Path $evidenceDir 'render-smoke.log')
```

每条命令执行后记录 `$LASTEXITCODE`。`doctor.py --render` 是 LMMS 兼容流程冒烟，实际三栏工作流生成还须完成下方 W07。GitHub Actions 的 Windows/macOS 检查覆盖静态契约、无窗口测试和诊断，不能替代真实窗口、实际音频设备或人耳验收。

## 已知未关闭问题

| 编号 | 复现与实际结果 | 验收要求 |
| --- | --- | --- |
| UI3-R8-F1 | 1020×700，来源栏收起，选中画布积木并展开详情；明亮和黑暗主题的画布高度约 305px，关闭详情约 353px。要求至少 320px。 | 两种主题分别截图，记录实际客户区、缩放与可见画布高度；该问题在本轮仍开放。 |
| UI3-R8-F2 | R8 生产者完整 1044 项测试中，`tests/core/test_curve_canvas_ui.py` 的 Text Backspace 断言预期 `A`，实际 `Ai`；独立一次完整运行通过。原因尚未确认。 | 保留每次原始日志；若复现，记录输入焦点、操作及环境；后续绿色运行不能删除首次失败。 |

R8 提示修复本身 PASS，整体 UI 验收 FAIL。当前主线重新运行的 643 项后端测试和配对前端检查通过，源码与原收据的 242 文件 manifest 相符。当前会话没有重新运行完整 GUI 套件，亦没有执行 Windows、设备播放或人工听感验收。

隔离输出释放模块中 A→B→A 播放意图失败属于排除功能，本分支不含该模块；不得将它误列为本次源码已修复或本次 UI 新发现。

## Windows 实机验收表

先用 100% 显示缩放，再对最小窗口和关键操作重复 125%／150%。每项分别填写 PASS、FAIL、NOT_TESTED 或 BLOCKED，并注明 SHA、截图/日志与失败步骤。

| 项目 | 操作 | 预期与证据 |
| --- | --- | --- |
| W01 启动与布局 | 启动空工程，切换两主题；测试 1020×700、1280×800；收起/展开来源。 | 标签、图标、按钮和播放器可达；分别记录客户区与系统缩放。单独回报 F1。 |
| W02 素材 | 导入 `assets/samples/ode-to-joy-theme.mid` 和 `assets/samples/EmoBlocks-Calm.mmp`；滚动素材列表，点击选择，再明确试听。 | 点击不自动播放或添加；原文件不被改写；缩略图显示真实音符；素材与来源清晰。 |
| W03 组合与拖放 | 分别拖到素材卡左/右；取消一次、确认一次。拖入、移动、删除；尝试重叠和越界；Esc 取消。 | 前后顺序正确；取消不入库；确认保留原件；拒绝重叠/越界；删除不压缩其他积木时间；撤销重做准确。 |
| W04 强度与记忆 | 控制点编辑和手绘；改变积木情绪；移动积木；长度加/减；让峰值位于组合内部及空缺。 | 手绘一次撤销；移动不带走强度线；每次长度四拍；不能隐式截断；记忆保护所选素材版本和正确子片段。 |
| W05 输入与滚动 | 实体鼠标竖向/横向滚动；滚动后拖放；Tab、Return、Space、Delete、Backspace、Ctrl 撤销重做及 Esc。在输入框键入 AB 并 Backspace。 | 命中准确；焦点可见；输入框删除文字不删除积木；滚动条拖动/聚焦时可操作，无布局跳动。单独回报 F2。 |
| W06 补全与留白 | 留一个和多个空缺，测试全局与选中空缺；标记主动留白；取消一次计算。 | 只修改目标空缺；主动留白不补主旋律；局部剩余空缺有说明；取消、失败或过期结果不覆盖当前编辑。 |
| W07 完整生成 | 使用 8 格工程，画强度线，拖入欢乐颂分块并留空缺；生成完整方案；明确试听基础/处理后；切换候选后采用。 | 补全后确定并保护 Bridge，再生成连接块与块间处理；候选点击不播放；采用与试听快照一致；有效方案不足时如实说明。原始/处理后实际听感另填写。 |
| W08 播放器 | 明确播放后暂停/继续、停止、重播、定位、块导航；播放 A 时选择 B，再明确试听 B。 | 当前播放对象、波形、时间与块导航一致；仅选择 B 不抢播；暂停/重播无异常杂音需实际听测；无可靠映射时导航禁用。 |
| W09 保存与跨端 | 采用方案后撤销/重做；用中文和空格路径保存、关闭、重开；交换一份验证工程到 Mac。 | 素材来源、放置、强度、留白、保护和版本一致；不依赖另一台机器的个人绝对路径；缺少音频时明确重新准备，不冒用旧缓存。 |
| W10 输出与资源 | 明确选中成品，导出 MIDI/MMP/WAV；在 Windows LMMS 打开 MMP，外部软件打开 MIDI/WAV。 | 导出对象和模式正确；乐谱结构与时长一致；LMMS 工厂资源实际可解析；WAV 尾音/杂音由人耳记录。MMP 不等于自包含资源包。 |

若本机未配置 LMMS，可先完成无需渲染的编辑项目，其余保持 BLOCKED，不使用旧音频冒充本提交生成结果。第三方软件 MIDI 导入可能改变时值；记录软件版本和实际差异，不调整原谱来补偿未定位的导入器行为。

## 问题回报与交付

```text
VALIDATION_SHA:
执行日期与执行者:
Windows版本 / Python / Tk / LMMS版本:
显示缩放 / 客户区尺寸 / 实际音频设备:
项目编号 / 输入样例及SHA256:
操作步骤:
预期:
实际:
PASS / FAIL / NOT_TESTED / BLOCKED:
截图、日志、音频时间位置:
```

把验收表和日志反馈给主线负责人；本说明不自动向 partner 发消息。主线负责人根据具体 SHA 修复并复验。主线合并条件包括关闭已知阻塞问题、配对契约与适当自动检查通过，以及 Windows 编辑/生成/保存/输出实机结果。人工音乐听感单独记录，不将自动检查扩展为音乐质量通过。

原交接清单、指纹、UI R1–R8 收据和截图保留在本机仓库外运行档案，按交接记录 `handoff-20261008-161929-bae7c4` 索引；不将用户工程、音频、权重、凭据或个人环境复制进 Git。
