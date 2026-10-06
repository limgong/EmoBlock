# 强度画布 r3：P0–P1 验收范围

SPEC_REV=curve-workflow-v2-r3
CONTRACT_REV=curve-workflow-v2-r3-p0
RUN_ID=curve-v2-p01-20261006-8f7597e8

## 基线与 P0

起始规格提交 `f6cdb954fd622e22c57a8d75c8f8b4b9def9d0f4`，其前本地开发基线为 `a84d293a574094b3b543916e347bfc89ebfbf478`。所有此前源码、测试、平台适配与未提交优化已在基线保留；本轮没有清理历史目录或用户文件。

读取算法、前端、verifier 的实际 ROLE_READY，三者均为 r3。算法和前端只读评审后，lead 整合精确数据形状、保护持久化、指纹、失败与任务失效、阶段边界及夹具。verifier P0 R1 指出历史引用与保护摘要缺口；R2 明确 PASS，151 文件前后指纹均为 `c472609667d36597c5343c28b822e0d10588618c19c60ff8e90a2b1dc3ce69c6`。

PASS 后标记 FROZEN，本地提交 `e78c98eeb7f4bcafc0cafa0d54c49369748cddc9`；两个干净 worktree 安全快进，实际 SYNC_READY 已读取。契约正文及 P1 API 见 [公共契约第8节](design/curve-workflow-contracts.md)。严格主流程是实际补全完成→bridge位置与立即锁→全部桥就绪→连接块→最终边界→整曲校验。

## P1 实施范围

- `curve_project`：独立 assembly.v2 固定 tick 时间轴、8格/120 BPM空初始工程，独立放置位置/音符快照、组合来源、强度点、主动留白、保护与未来记录校验。移动/删除不压缩；重叠/越界/截断原子拒绝；内部短素材和精确tick无旧四拍/最短秒数限制。
- `curve_session`：原子编辑、undo/redo、保存指纹、独立不可变请求快照、单调编辑修订、重复请求和迟到结果失效。返回数据均深拷贝，界面状态不写工程。
- `curve_store`：独占创建新快照、不覆盖旧文件、fsync和失败清理；当前工程、输入快照与候选暂存空间独立保存。恢复 RUNNING 为 INTERRUPTED，保留锁/内容/计划，不恢复后台线程。
- 旧 studio/structure/pool/assembly/story 读取返回原载荷及 legacy_readonly 能力；已有成品逐格式报告实际可用性，不自动规划或迁移。新数据服务供 P2 UI 消费；现有 Tk 公共入口本轮仍沿用旧路径。
- `story_engine.validate` 明确分派 v2；v2 plan/generate 返回 PIPELINE_NOT_AVAILABLE，不能误入旧隐式变体/bridge与连接共同分配。

P1只记录情绪标签，不计算情绪音乐。手动 bridge 夹具注册保护、移动/删除更新并保留旧引用审计、undo恢复；新旋律/补全/bridge/连接/边界算法均未实现。已有非桥保护的移动/删除/情绪编辑若需重算，明确拒绝而不静默丢弃，待 P3接线。失效记录的 payload.audit_total_ticks 保存审计时总长，活动与历史范围分别检查；不把历史时间轴当作当前占用。

## 自动验证（自查，独立结论另存运行目录）

沿用现有 `.venv/bin/python`，通过仓库外 run-python 包装器隔离 DATA、TMPDIR、pycache 和测试输出；未安装或切换依赖。文件故障和序列化测试全部使用临时目录。

| 命令 | 结果 |
| --- | --- |
| `.venv/bin/python scripts/check_frontends.py` | PASS：共享UI、配对适配器与后端隔离 |
| `.venv/bin/python scripts/test.py --backend-only` | PASS：278项 |
| `.venv/bin/python scripts/test.py` | PASS：414项 |
| `git diff --check` | PASS |

新增23项行为测试覆盖：默认空编排、240tick/短尾、移动删除不搬线/邻居、重叠/越界/缩短原子拒绝、显式留白、重复使用独立情绪与快照、嵌套组合实际音符一致、无效类型/来源/版本、v2不走旧planner、保存与undo/noop/redo状态、请求快照深拷贝/重复/迟到、手动桥移动删除的历史引用/保存/缩短/undo、固定指纹向量、就绪实际内容与保护支撑、自动桥缺失结果门禁、失败锁与中断恢复、连接三类侵入窗口、两快照/中文路径、写失败/损坏文件与历史保留、旧格式只读/逐格式可用性。未来音乐阶段的数据均是手工夹具，仅证明数据门禁和往返。

完整Tk测试结束时输出一个 `hide_history_scroll` after 回调的 invalid command name 警告，测试判定仍为 OK。未为P1数据任务修改相关旧UI定时器；不将此计作人工GUI通过。

本文件记录冻结前自查；P1 verifier 的 RUN/TASK/ROUND/HEAD/前后指纹和明确结论保存在仓库外运行记录，由最终交付引用，不在等待检查期间修改本文件。

## 待验及停止点

本轮没有启动应用做人工操作、录制双主题/三尺寸截图、真实LMMS渲染、设备试听、听感判断或Windows实机验证。完整测试包含程序化Tk回归，与人工GUI/听感证据分开。新v2界面与旧只读UI路由待P2；峰值/情绪音乐待P3；基础补全、bridge、连接、边界、推荐及真实输出待P4–P8。旧MMP输出器的10tick量化风险已登记，受保护数据精确保存不代表三格式输出已经验收。

P0–P1各最多5轮，冻结后只读复核；只有同一身份与指纹匹配的明确PASS可交付。本轮完成P1后停止，不派发P2，不推送或发布。
