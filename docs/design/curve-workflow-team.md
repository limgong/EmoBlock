# 强度画布 v2 r3 团队与阶段协议

SPEC_REV=curve-workflow-v2-r3
CONTRACT_REV=curve-workflow-v2-r3-p7

当前阶段：P6实施ROUND2独立PASS及前后199文件指纹已现场核对；用户启动P7。第13节p7独立契约ROUND2已PASS并FROZEN，已授权实施。本轮结束停止，不进入P8；下面旧阶段启动/停止语句仅为保留的历史。

产品依据：[r3完整计划](curve-workflow-v2.md)；[公共契约](curve-workflow-contracts.md)的p0/p23/p4正文为 **FROZEN**；历史P5第11节为 **FROZEN**（独立ROUND2 PASS），当前P6第12节为 **FROZEN**（独立ROUND1 PASS）。历史P0独立ROUND2、P4实施ROUND3均PASS，原阶段记录保留；用户已启动P5，只读评审、独立契约冻结后才按文件归属实施，完成P5停止，不进入P6。

## 角色与文件所有权

| 角色 | 职责 | 边界 |
| --- | --- | --- |
| lead-backend | 唯一协调者，公共契约、时间轴、工程状态、保护门禁、story_engine.py主流程及集成 | 发任务、读pane收交付；公共接口先更新契约并通知 |
| music-algorithm | 新旋律、基础补全、bridge决策/生成、连接块/最终边界算法、测试与样例 | 独立worktree/分支，只改允许范围，不改story_engine.py主流程 |
| frontend | shared三栏/画布/播放器、保护/推荐/对比状态、双主题和配对适配 | 不改后端契约/算法，不复制平台UI，不把保护仅做Canvas标记 |
| verifier | 冻结集成目录只读审查，严格顺序/保护/实际输出 | 不改源码/测试/文档，不提交，idle/done不是PASS |

worker不互相派单、不自行合并集成分支、不推送、不向lead自动发唤醒消息；由lead读取实际名称/pane收交付，不按codex类型寻址。角色职责不是本次功能启动授权。

## P0–P8顺序与依赖

| 阶段 | 交付 | 门禁 |
| --- | --- | --- |
| P0 | r3规格、契约、测试迁移清单及独立设计检查 | 用户启动；检查后才能冻结DRAFT |
| P1 | 固定时间轴、工程状态、保存/撤销、快照与旧工程读取 | P0明确PASS、契约冻结，lead主导 |
| P2 | 三栏、原始块/句、新旋律、组合及共用播放器 | 契约/基础后端通过，再按范围并行 |
| P3 | 无过冲强度、手绘、情绪、记忆积木和保护 | P1/P2与对应契约 |
| P4 | 实际基础补全候选、精确tick空缺，无待生成占位 | P3，目标完成、峰值保护确定 |
| P5 | bridge位置决策→立即锁定→生成→READY验证 | CompletedCandidate，失败保锁并中止版本 |
| P6 | READY桥保护外判断/生成连接块 | 桥版本、实际端点、保护摘要匹配 |
| P7 | 最终边界、整曲校验、完整推荐/对比试听、确认与自动应用 | P6，不改桥结构，同一快照一次事务 |
| P8 | 整曲三格式、双主题/双平台、真实渲染和人工听感 | 前述有效集成结果，验证类别分别报告 |

每套推荐均基础候选→桥决策/锁定/READY→连接块→最终边界→整曲校验/编配/试听；不共同决策、不交错生成。五类最终边界不替代桥或连接块生成。无桥也是显式新计划版本；失败/失效不是释放保护。

P0–P1由lead主导，其他角色只执行明确派发的设计审查；契约和基础后端通过后再并行实现。同步文档或agent空闲不会自动启动P0/P1。

## 任务信封和交付

```text
RUN_ID:
TASK_ID:
ROUND:
SPEC_REV: curve-workflow-v2-r3
CONTRACT_REV: 当前明确契约修订；DRAFT任务仅做授权设计审查
WORKTREE:
BASE_SHA:
BRANCH:
ALLOW_FILES: 明确文件/新增文件；禁止并发改公共接口
DEPENDENCIES: 任务/提交及计划/保护版本；未就绪不越过
ACCEPTANCE: 输入输出、保护、失败、行为测试与证据
```

交付含以上身份、本地提交SHA、变更清单、契约及保护校验、测试日志、实际音乐样例和待验项，留pane由lead读取。worker仅提交本分支/允许文件，lead集成本地提交并处理冲突。公共接口或版本变化提交前更新契约、通知受影响角色，不猜字段或绕门禁。

## 安全同步与运行环境

复用现有分支、两个worktree及四角色布局，不重复初始化、不删除其他目录/pane、不reset --hard/git clean。同步前确认worker空闲、无未交付修改/新增文件、无未集成提交，再快进；冲突/写入时报告文件、提交、角色并停止冲突操作，不强制覆盖。

复用已有Python依赖，各worktree加载自身源码；仓库外每角色run-python包装器隔离数据、临时文件、测试输出、pycache。长驻agent不能假定自动继承新RUN_ID，任务信封和对应包装器才是依据。不重复安装环境/模型，不操作用户工程，不把音频/凭据/环境/LMMS纳入提交。

动态名称/pane、RUN_ID、BASE_SHA、SPEC_SHA、日志、指纹和证据留仓库外，不影响代码指纹。不推送、不发布、不改账户设置、不代答授权。

## 冻结、检查与失败

每阶段实现→集成→冻结→verifier→修复复验，最多5轮。验收期间不修改集成目录；指纹含相关tracked及非忽略untracked源码/测试。核对同一RUN/TASK/ROUND/SPEC/CONTRACT/BASE_SHA及前后指纹；代码变化则结果作废，修复后重新冻结/计算。

PASS必须明确匹配；FAIL列位置/条件/影响/缺失验证，第5轮仍失败报告余项。idle/done仅可收输入；超时/stalled先读输出核实，不盲重发。blocked先读原因报告，不代答授权。实际音频设备检查串行。

## 验收分工与诚实边界

lead负责CompletedCandidate完成门禁、位置确定即锁、BridgePlan READY/版本依赖、保存撤销及过期处理、连接规划/生成/整曲三道保护。算法交真实音符、单侧/相邻桥联合边界及指纹，连接用桥真实端点，最终边界保留表演/编配变化证据。前端直接显示锁定/READY/失败/失效和记忆保护，试听/应用同一快照，不重随机。

verifier重点验证占位/未完成不能进桥、生成时已有锁、失败不静默解锁、三类侵入窗口拒绝、最终桥结构不变、手放移动删除/保存撤销/过期更新、实际差异及一次事务。流程矩阵与旧接口/测试迁移见契约，不能只检查流程图。

按改动执行后端/完整测试、check_frontends及diff检查。固定素材提供基础、桥后、连接后、最终对照和影响范围；真实LMMS、保存重开和三格式同谱。双主题、1020×700/更大窗口、折叠/滚动/命中、Mac鼠标触控板、Windows及常见缩放需实证。

自动约束、程序化Tk、实际渲染、设备流、人工视觉/听感、Mac/Windows实机分别记录；源码/模拟不证明连接自然或音乐表达。静态Vibrancy不是真毛玻璃，情绪色是语义例外，未验项目明确待测。

## 本轮交付停止点

P0与P1提交、匹配指纹的verifier结论、自动验证及未验项。P0审核期间契约仍DRAFT，PASS只授权将审核过的规范正文标为FROZEN，不擅改正文。P1仅后端数据/保存/撤销/旧读取；算法与前端不派功能任务。完成后停止等待P2指令。

## P2–P3 启动补充

用户已授权P2–P3，P1最终R3 PASS、HEAD与指纹已现场复核。补充契约第9节先DRAFT评审、PASS后FROZEN；P0正文历史保留。公共接口归lead，算法/前端按第9.6文件清单并行；P2冻结验收PASS后才派P3，结束P3停止不进P4。运行记录继承P0/P1结论，不重置旧阶段轮数；本轮P2/P3各最多5轮。

## P4启动补充

P3最终ROUND3 PASS已现场核对，用户授权P4。公共契约第10节p4先DRAFT，两角色只读评审、lead整合、verifier独立检查后冻结。文件归属及接口见10.7/10.8；算法/前端待冻结后并行，不相互派单。基础候选只暂存，不接P5 bridge或P7最终应用/试听。契约与实现各最多5轮，冻结期不写集成目录。完成P4停止；历史P0–P3的门禁、轮次、保护兼容和待人工验证保留。


## P5 启动补充（DRAFT）

用户已授权P5，P4最终ROUND3 PASS的实际输出、HEAD与前后指纹已核对。已验证的Mac删除键修复六文件单独提交为c767fe6，保留P4所有修复和待人工验收。当前第11节p5补充契约DRAFT，算法/前端只读评审后由lead整合，再经verifier独立PASS冻结。实现只到bridge位置原子锁定、完整乐句、独立就绪认证与暂存；失败保锁，none新版本；不进入P6，不实现连接、最终应用、完整方案试听或正式整曲导出。旧规范正文和数据所属版本不重写。契约和实施分别最多五轮，冻结期间不写集成源码；各角色范围与接口详见契约第11节。

P5契约独立ROUND2 PASS：受检HEAD=9901766，前后指纹186d265ad323c9b7152fcfc220dbd06ac6a892f68eb6a85461c8947774455273；lead现场核对同一RUN/TASK/ROUND及HEAD/指纹，只修改状态标为FROZEN，规范正文未改。worker同步后按11.8派工，实现仍须独立验收。


## P6 启动（FROZEN）

P5实施ROUND2实际独立PASS已核对：HEAD=8706f96fa9c8aecdbb613f115547f64255da9b3c，192文件前后指纹c733742fd431bfd27e751ca51bda3ad1bb2fa3414d1ce36d7b928490af8ccbd3；集成与两个worker源码一致且干净。用户明确授权P6，历史规范和验收保留。第12节p6为DRAFT，算法/前端只读评审与verifier独立PASS后才冻结实现；只处理真实就绪桥保护外连接，不进入P7，不开放最终方案应用/试听/导出。四角色及本轮记录在仓库外运行目录，使用已有Python和独立数据，文件所有权/验收见12.6。

P6-CONTRACT独立ROUND1 PASS：HEAD=5c70a8c6d0e0b724831a0f82a4139fe66b5f1138，193文件前后指纹1dd4d9914e45d51853de7b89dd24936502c273f0deba2b29b173e90098df90e2。lead核对实际pane与review一致，仅更新状态FROZEN，正文规则不改；worker安全同步后按12.6范围实现P6，停止于P7之前。


## P7启动补充

P6实施ROUND2的实际独立PASS、HEAD及完整199文件前后指纹已经现场核对。P7新RUN保留旧验收与人工待验，复用既有四角色/worktree/依赖。第13节p7先DRAFT，算法/前端已完成两轮只读建议，lead整合13.10–13.16；接下来独立契约ROUND1，PASS后才能FROZEN和派功能，不能以worker设计建议当验收。

lead独占公共curve_final/curve_recommendations/curve_final_render/curve_application服务、curve_project/session/store/workflow、story_engine主流程；旧completion/bridge/connection的p7来源读取适配仅lead改，旧音乐规则/输入校验不放宽。算法只新增curve_boundary_music及专项；前端shared RecommendationUI、唯一Canvas/共用player和既有stage互斥接线及对应tests；具体ALLOW_FILES在任务中，不并发写同模块。

契约和实现各最多5轮，冻结时整目录不得写；修复重新冻结，明确RUN/TASK/ROUND/HEAD/前后同完整指纹PASS。候选mode只编配/渲染，不重作曲；单gap局部可听/确认不可正式整曲导出；确认同谱/一次undo/幂等、接受绑定不自失效。实际LMMS及设备串行，完整试听与应用本轮必须真接通，人工听感/Windows和截图仍分别待验，不以P8为理由交假音频。完成P7停止，不派P8。
