# 2026-10-01 迁移验证记录

基准版本：UI-v2。环境：Windows，Python 3.9.13 / Tk 8.6，项目内 `.venv`，mido 1.3.3、NumPy 1.26.4。未安装或运行 Mac 虚拟机。

| 检查 | 结果与边界 |
| --- | --- |
| `scripts/check_frontends.py` | 通过：共享显示、双端接口、后端依赖隔离 |
| `scripts/test.py --backend-only` | 245 项通过：规则、素材、情绪线、规划、连接、平台模拟；不启动 GUI / 实际音频 |
| `scripts/test.py` | 287 项通过：包括隐藏 Tk 界面的实际交互回归 |
| 后端独立进程导入 | 通过；未加载 tkinter 或平台音频播放器 |
| Mac 适配选择后的前端导入 | 通过，运行于 Windows 主机；不是 Mac 原生运行 |
| 无窗口测试选择 Mac 适配器 | 245 项通过（Windows 主机，`--platform macos`），不代表 native OS / 音频实测 |
| Mac 播放模拟 | WAV 片段帧数、暂停/恢复计时、退出和临时文件清理通过；afplay 调用被替换为模拟进程 |
| `scripts/doctor.py --render` | Windows 实际 LMMS 渲染成功：13 块 / 26 秒主体 + 1 秒尾音，44.1kHz；峰值 0.31419，削波样本 0 |
| `backend/cli.py` | 默认主题故事生成独立排布 JSON 成功 |

完整 GUI 回归期间，Tk 曾输出销毁测试窗口后 `ttk::ThemeChanged` 的异步回调警告，测试最终全部通过。警告保留在本地 `work/test-migration.log`，不将其表述为“零警告”。本记录是迁移回归，不是音乐听感质量评价。

新增 GitHub Actions 配置包含 Windows/macOS 无窗口测试和平台契约检查。本地运行通过不代表远端 CI 已通过；远端结果以仓库 Actions 为准。真实 Mac 的桌面、播放、Finder 拖入、LMMS 渲染和音频转 MIDI 仍待验证，方法见 `macos-portability.md`。
