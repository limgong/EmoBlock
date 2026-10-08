# EmoBlocks 开发约定

## 项目来源与目录

- 本次整理的基准为 `EmoBlocks-Windows-20260926-UI-v2/EmoBlocks`；同步记录见 `docs/sync-report-20261001.json`。后续开发修改正式源码，不重复运行一次性迁移脚本。
- 正式后端在 `backend/`，正式前端在 `frontend/`，入口为 `run.py`。`outputs/`、原发布包、`work/` 是保留的本地历史，不是第二份正式源码。
- 后端不得依赖 Tk、Win32、MCI、winsound 或具体前端。平台路径统一通过 `backend/core/runtime_config.py` 解析。
- 不提交用户工程、历史生成结果、虚拟环境、安装器、LMMS 二进制、凭据或个人绝对路径配置。不要删除本地历史来整理 Git。

## 每次前端改动必须同步 Windows 和 macOS

1. 改动前先检查 `frontend/shared/`、`frontend/windows/`、`frontend/macos/`，确定两端受影响的显示、交互和播放行为。
2. 通用界面、样式、情绪线、素材卡、时间线和试听逻辑只修改 `frontend/shared/`：两平台使用同一份源码，自动获得相同功能；不得另复制一份界面造成分叉。
3. 如果改动涉及窗口、字体、快捷键、滚轮、文件拖拽或音频播放器接口，必须同时检查另一个平台的适配器，必要时同步修改。Windows 专属 API 只能出现在 Windows 适配器中。
4. 两端都应保持 `ui_platform`、`file_drop.FileDrop`、`audio_player.WavePlayer` 的相同调用契约。修改接口时更新两个实现及契约测试。
5. 每次前端改动运行 `python scripts/check_frontends.py` 和 `python scripts/test.py`；CI 跑 Windows/macOS 的无窗口测试。更新平台差异说明，不能将模拟测试描述成 Mac 真机验证。
6. 交付说明明确哪些双端行为已验证，哪些需要 Mac 实机验证。若缺少 Mac，不要声称完整兼容已实测。

## 验证与交付

- 基础测试：`python scripts/test.py --backend-only`；完整测试：`python scripts/test.py`（需要桌面/Tk）。
- 本机依赖检查：`python scripts/doctor.py`；实际 LMMS 渲染：`python scripts/doctor.py --render`。
- `data/` 保存新工程、导入缓存和导出结果；可以用 `EMOBLOCKS_DATA_DIR` 指定其他可写位置。
- 未经用户授权不强推、不覆盖远程历史、不为项目擅自选择开源许可证。

## 当前用户确认范围（2026-10-08）

- 后续开发不再要求旧版工程文件兼容，不新增旧格式读取、编辑迁移或兼容适配；验收以当前工程格式为准。保留已有历史文件和证据，不把当前格式的保存重开回归移除。
- 主线 UI 以 Herdr R8 已交付代码为基础，由当前聊天维护；Herdr 额外功能继续在原隔离 worktree 开发，禁止自动接线或合入主线。Windows 实机验收暂缓，共享源码及双端适配契约检查继续。
