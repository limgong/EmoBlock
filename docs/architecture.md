# 源码结构与 UI-v2 同步

## 基准与同步结果

基准：`EmoBlocks-Windows-20260926-UI-v2/EmoBlocks`。与旧 `outputs/` 比较后，同步了 28 个不同/新增的源码及文档文件，其中 6 个原文件有替换前备份。明细和 SHA-256 见 `sync-report-20261001.json`，备份在本地 `work/sync-backup-20261001/`。原发布包、用户工程、音频及历史目录均保留，未删除。

正式源码以 UI-v2 为起点，随后仅进行了目录拆分、路径配置和双平台适配；这些修改不是要求两份源码逐字相同。历史设计文档保存在 `docs/design/`，其旧启动命令以根 README 的新命令为准。

## Git 目录树

```text
EmoBlock/
├── run.py                     # 自动选择平台的桌面入口
├── emoblocks_bootstrap.py      # 统一模块路径
├── frontend/
│   ├── shared/                # UI-v2 显示与交互，唯一通用界面
│   ├── windows/               # Windows 启动、MCI、Explorer 拖入、窗口 API
│   └── macos/                 # Mac 启动、afplay、Finder 拖入、原生窗口
├── backend/
│   ├── cli.py                 # 无界面规划 / 渲染入口
│   ├── core/                  # 情绪线、块规划、连接、连续音乐、工程模型
│   ├── step1/                 # 旋律情绪编配
│   └── step2/                 # 变体、回答句、关联素材
├── assets/samples/            # MIDI / MMP 示例及素材来源说明
├── tests/                     # 原回归测试与双平台契约测试
├── scripts/                   # 测试、平台检查、依赖诊断、一次性迁移
├── docs/                      # 设计、同步记录、架构及 Mac 检查
├── .github/workflows/         # Windows / macOS 自动测试
└── AGENTS.md                  # 后续双平台同步要求
```

## 前后端边界

前端负责布局、主题、卡片、情绪绘制、试听控制和用户操作；后端负责音符解析、素材发展、排布、连接、情绪编配、导出及渲染。依赖方向为“前端 → 后端 → LMMS / NumPy / mido”，后端不反向导入界面。

这是本地桌面程序的源码分层，不是拆成浏览器网站和 HTTP 服务器；无需部署服务或开放端口。`backend/cli.py` 可完全不加载 Tk 独立规划音乐。

后端现阶段是可解释的离线规则算法，不应宣传成已接入大模型。可选 Basic Pitch 是音频转 MIDI，而不是音乐续写或情绪生成模型。

## 两平台显示同步

卡片、情绪块、强度曲线、生成试听、历史列表、亮暗主题及动态缩放共用 `frontend/shared/`，避免复制界面导致版本落后。两端分别提供相同播放器、文件拖入及窗口接口。

Windows 保留 UI-v2 自绘无边框窗口；Mac 使用原生标题栏与系统窗口按钮，中文字体映射为 PingFang SC，支持 Command 快捷键及 Mac 滚轮事件。平台差异不是功能缺失，但需实机验证布局。

每次改动运行 `scripts/check_frontends.py`；它检查两端接口及不允许的依赖，但不能替代视觉和音频实测。详细约定见根 `AGENTS.md`。

## 本地历史与 Git

`outputs/` 旧快捷方式入口已转发到正式源码与项目 `.venv`，旧结果仍留在原处；新结果在 `data/`。这些目录不上传。外部 LMMS、音频模型、虚拟环境和 Windows 发布压缩包也不提交到源码 Git；将来需要分发二进制时单独制作 Release。
