# 强度画布 v2 r3 公共契约草案

SPEC_REV=curve-workflow-v2-r3
CONTRACT_REV=curve-workflow-v2-r3-p7-runtime1

**状态：p0历史正文FROZEN；第9节p23 FROZEN (P23-CONTRACT ROUND2 PASS)，第10节p4 FROZEN (P4-CONTRACT ROUND1 PASS)；第11节p5 FROZEN (P5-CONTRACT ROUND2 PASS)；第12节p6 FROZEN (P6-CONTRACT ROUND1 PASS)，当前实施至P6。** 产品依据为 [r3完整规格](curve-workflow-v2.md)。公共接口不依赖 Tk，旧规划不得用来绕过 r3 门禁。历史正文所述阶段能力以相应独立验收为准。

## 1. 时间、身份、工程和快照

内层 schema 为 `emoblocks.assembly.v2`；音乐时间整数 tick、PPQ=480、四拍格=1920 tick、半开区间 `[start_tick,end_tick)`。导入统一 PPQ，保留短尾和跨块音符身份。默认8格、内部120 BPM、强度0.25、不预填素材；右栏无BPM控件，本轮不另加速度入口。音乐主体与实际WAV尾音长度分开记录，播放器秒数由适配层转换。

ID独立于显示编号，删除不重排编号。公开数据可序列化，不含Tk、像素、线程和播放器句柄。所有阶段请求/响应包含 `spec_rev, contract_rev, request_id, snapshot_id, content_fingerprint, edit_revision, algorithm_version`；依赖计划时必须包含其ID、版本及输入/保护指纹。

工程候选字段：`schema, project_id, grid_count, total_ticks, bpm, sources, materials, label_counters, placements, intensity_points, blank_regions, memory_protection, bridge_plans, bridge_protections, connection_layers, boundary_layers, accepted_candidate, settings`。

内容指纹覆盖音乐持久化状态、基础快照、位置、情绪、强度、留白、保护及接受的阶段结果；排除播放位置、选择、悬停、滚动、主题、未确认草稿及缓存。edit_revision/request用于过期校验，不独自导致dirty。保存、生成和所选成品差异分别判断；撤销回保存内容恢复内容指纹。

## 2. 素材、句、放置、强度及记忆

### 素材服务

`SourceSnapshot`保存原始导入身份、音符快照、调性、文件指纹和完整来源。`MaterialSnapshot`保存 `id, label, kind, length_ticks, notes, provenance, generation, phrase_id, children`。不再建立固定A/B/C/D版本族。

音符含 `note_id, origin_note_id, pitch, start_tick, duration_tick, velocity`，时间相对素材；跨块切片保留同一原音符身份及连续关系。generation保存方法、参数、种子、算法版本和基础音符快照；重复/嵌套使用也有独立路径身份，不覆盖原件。

`generate_material(base, method, parameters, context)`统一提供局部音高变化、回答、原副旋律规则、节奏重组、动机发展、疏密变化及bridge。副旋律是替换素材，不额外叠声部。默认最多三条有效导入候选：局部变化、回答句、节奏重组；优先首个有音符完整句，否则首个有音符块；重复/无效不凑数。

整句为主要素材，可展开有归属、相对位置、来源及独立快照的四拍子块，子块可独立试听/拖用/组合。组合是有序组件快照，支持重复和嵌套但无环；实际长度求和。整句/组合整体放置一个外框、一个情绪。中栏卡片等大，左右拖放产生行内草稿；确认才新增，取消/试听不写工程。

### 固定放置与曲线

Placement含 `id, material_id, base_snapshot, start_tick, length_ticks, emotion, emotion_variant, manual_protection`；基础快照不可被情绪变体覆盖。用户拖放每拍吸附，自动补全按精确tick处理不足一拍空缺。移动/删除不压缩、不搬其他放置/曲线；重叠、越界、缩短截断已有内容原子拒绝。

基础放置与bridge/连接覆盖层分开：合法覆盖层不是新基础放置重叠，也不授权侵入保护。待补全是未被基础放置/主动留白覆盖的补集，素材自身休止不算空缺；主动留白禁止主旋律，允许克制伴奏及尾音。

强度保持现有无过冲平滑插值（单调三次Hermite、平端延伸，换成tick表达），撤销此前线性插值草案。初始恒定0.25；积木中点读强度、宽度对应实际长度、厚度固定；纵向拖动不改强度。手绘转控制点，结束一次撤销，Esc取消未提交操作。

### 情绪与记忆

情绪处理每次读该放置基础快照，不累计失真、不改库/其他使用、不隐式轮换用户选定素材。MemoryProtection保存峰值tick、放置/句/组件路径、对应四拍子片段范围和情绪处理前所选素材音符指纹，不恢复原始来源旋律。

同峰取最早位置，终点映射最后有效片段，长句/组合保护对应四拍子片段，短尾实际长度。记忆积木叠放对应音乐块、标记与范围一致、不加音符或时长；空缺待落位、主动留白不填。候选补齐峰值空缺后立即计算记忆保护，先于bridge决策。

## 3. 不可交错的主流程

```text
完成基础补全候选
→ bridge位置决策
→ 立即锁定范围
→ bridge生成并验证就绪
→ 连接块判断及生成
→ 最终块间处理
→ 整曲校验、编配与试听
```

每套推荐独立完整执行。状态候选为 `BASE_COMPLETED → BRIDGE_DECIDED_AND_LOCKED → BRIDGES_READY → CONNECTIONS_READY → BOUNDARIES_READY → SCORE_VALIDATED → AUDITION_READY`。失败进入本版本FAILED，不跳阶段。

位置决策与锁定必须同一后端状态事务返回；不能先公开位置计划再留下可被占用的间隙。所有选定bridge READY后才可连接。无bridge也必须有明确决策、计划ID/版本和理由，不能用缺失计划或待生成占位冒充就绪。

## 4. 流程输入、输出、保护、失败与验收

### A：完成基础补全候选

接口：`complete_base_candidate(CompletionRequest) -> CompletedCandidate`。

- 输入：不可变工程快照、目标gap ID/精确范围、素材库、左右音乐、调性/节奏/动机、情绪/强度、重复程度、保护和留白。选中gap只该处，否则全部。
- 输出：真实基础排布、实际素材/音符快照、target_resolution、remaining_gaps、base_write_ranges、输入/候选指纹及即时记忆保护。完整工程直接以当前排布进入下一步。
- 保护：只填目标基础空缺，不移动/改写已有放置；使用原始/新旋律或精确长度新素材。合法内部休止不能混同未完成空缺，此阶段不决定自动bridge、不留无音符bridge/连接占位。
- 失败：目标仍未解决或无合法填法，报告失败/候选不足，不进入bridge；不能假留白。局部其他gap保留，不能误报正式整曲完成。
- 验收：2.5拍后0.5拍（240tick）精确填满且邻块不动；占位/未覆盖拒绝；峰值gap完成后保护先建立。

### B/C：bridge决策、立即锁定、生成与就绪

接口：`decide_bridge(CompletedCandidate) -> {BridgePlan, BridgeProtection[]}`；`generate_bridge(plan, protection, context) -> BridgeResult`；`validate_bridge_result(...) -> ready_plan_and_protection`。

BridgePlan含 `id, version, candidate_fingerprint, decision, ranges, reasons, context, goals, dependencies, algorithm_version`。先检查音乐自然成立，再分析前后关系与发展、保护/固定时间、保留与替换收益。窗口可重要旋律间连续2–4块或更长，同情绪不强制桥；允许明确decision=none。

BridgeProtection含 `bridge_id, owner_id, start_tick, end_tick, input_snapshot_id, input_fingerprint, plan_id, plan_version, status, blank_mask, content_fingerprint`。位置一确定即RANGE_LOCKED；生成验证后CONTENT_READY，保存实际不可变音符及结构指纹。手动bridge放置也提前登记保护，不依赖Canvas标记。

BridgeResult含完整句、子块、来源、参数/种子、实际音符、输入版本及验证。统一新旋律服务读取左右实际素材、长度、调性、情绪/强度轨迹、保护及留白掩码；须有动机关系、句发展和入口空间，不只是加长端点插值。缺一侧按单侧引入/收束；相邻桥先联合确定边界条件，不互读旧音符猜测。情绪处理在内容READY前完成。

- 保护：记忆、主题、手工保护优先，调整/放弃窗口，不搬保护。主动留白可作为桥内休止，但主旋律空白原样保留。自动规划不覆盖手放bridge，仍检查上下文适配。
- 失败：保留原补全候选和已有工程，当前版本中止，不进连接、不静默释放锁。换位置/改为无bridge创建新计划版本并重走后续；不把旧锁失效当越权授权。
- 验收：位置已决、生成挂起时锁已存在；失败仍锁、未READY不连接；新位置/无bridge增版本；单侧/相邻桥、留白和保护范围正确。

### D：判断并生成连接块

接口：`plan_connection_blocks(CompletedCandidate, ready_bridge_plan, protections, BridgeResult[]) -> ConnectionBlockPlan`；`generate_connection_blocks(plan, actual_layout) -> ConnectionBlockResult`。

ConnectionBlockPlan必含 `bridge_plan_id, bridge_plan_version, bridge_layout_fingerprint, protection_summary_fingerprint`，以及实际端点、合法窗口、规则、依赖、影响范围。输入排布已包含READY桥，用实际桥首尾音，不能用被替换前旧端点。

- 保护：先判断必要性，再选窗口/规则。可用范围减去bridge锁、记忆/主题/手工保护、留白禁止主旋律部分和其他连接窗口；完全覆盖、部分侵入、跨越桥均无效，重新搜窗口，不能裁桥。连接之间不重复覆盖，相邻连接先确定依赖/共享边界。
- 输出：独立覆盖层、原音符对比快照和connection_impact_ranges、保护校验；基础排布不销毁，不移动素材/情绪位置或延长总长。规则可调内导向、局部回应、铺垫、先保留后展开、收束。
- 失败：桥未READY/版本不匹配直接拒绝，生成越权则结果无效。没有合法窗口保留旋律、退到轻量最终边界处理，不解锁桥。
- 验收：READY/版本门禁、实际桥端点、三类侵入拒绝、桥两侧都需连接但无窗、连接互斥和过期返回。

### E：最终块间处理和整曲校验

接口：`plan_boundaries(actual_layout, BridgePlan, protections, connection_results) -> BoundaryPlan`；`apply_boundaries(...) -> FinalScore`；`validate_final_score(...) -> ValidationReport`。

BoundaryPlan含 `id, version, input_fingerprint, bridge_plan_id/version, protection_summary, adjacent_object_ids, operations, impact_ranges, original_splice_snapshot`。自然延续、动机回应、渐进铺垫、留白进入、回落收束、无专门处理只用于最终边界，不替代桥/连接块生成。

- 保护：桥音高、绝对起点、时值不改，桥范围不新增主旋律；可改保护区外邻接片段，或只改力度/音色/伴奏交接。无空间不能缩桥。句内四拍界不自动过渡；只合并同来源同音符的连续切片，不合并不同来源同音高。鼓填充/目标音预示不默认。
- 输出：先收集操作再统一检查冲突，实际各层写入范围与独立表演/编配变化证据；整曲固定总长，重新核对所有保护、留白、占用与依赖，不能只信生成器声明。
- 失败：冲突、改桥结构、桥内新增主旋律、过期依赖导致整曲无效，不进入可应用试听；原工程保留。
- 验收：恶意/遗漏保护声明也被整曲校验发现；允许力度/配器变化独立验证；句内边界不重复处理，同源合并不误伤不同来源。

### F：推荐、编配、试听、确认与自动应用

接口：`prepare_audition_candidate(validated_score, pipeline_results) -> AuditionCandidate`；`apply_candidate(candidate, current_snapshot) -> transaction`。

AuditionCandidate含完整乐谱、A–E各结果/版本、原基础对比快照、新素材暂存区、保护、应用事务、输入版本、实际差异证据、主体/真实音频尾音长度、文件可用性。至少两套实际音符/节奏/排布/句结构不同才称双方案；名字/编号/seed/情绪标签不算音乐差异。

- 保护：试听包含桥、连接和最终边界全部效果，不改工程、不自动抢播；确认使用同一试听快照，不重新随机。自动补全同流程、应用排序最高有效方案。编配和输出继续遵守桥及留白保护。
- 输出：基础补全、桥、连接/边界层、新素材及保护一笔事务应用；确认才加入工程/中栏，取消不污染库，一次撤销全恢复。仅主旋律去伴奏、统一旋律音色/力度但保留规划旋律和连接；三格式来自同一FinalScore。
- 失败：不足两套如实说明。素材/位置/情绪/强度/长度或版本变化，拒绝旧应用、重算，不释放旧桥给连接。其他gap未完成可局部试听，不能导出正式整曲。
- 验收：试听=应用，无重随机，取消库不变，一次撤销保护/层/新素材恢复，未完成不冒充整曲。

## 5. 三道保护门禁与用户编辑

桥旋律结构指纹规范化身份归属、音高、绝对start_tick、duration_tick，保留重复音符数量及休止/留白掩码；力度/音色/伴奏变化分开记录。P0须检查规范化，不能借排序/裁切漏掉改写。

1. 规划前：CompletedCandidate实际完成，选定桥全部CONTENT_READY，BridgePlan ID/版本、实际布局和保护摘要一致；否则连接接口拒绝。
2. 生成后：实际连接写入不交桥锁，桥真实结构不变，不能只信impact_ranges自报。
3. 整曲：最终边界、编配、输出所用FinalScore独立核对桥结构和全部保护；桥内新增音、改音高/起点/时值、缩桥腾位均拒绝；表演/编配合法变化分开验收。

无bridge是有ID/新版本的明确有效计划，而不是计划缺失或失败锁自动释放。手放bridge立即锁范围，已有内容校验后登记指纹。用户明确移动/删除/重新生成时，原子更新范围、内容、计划版本及依赖失效；保存/撤销恢复对应状态。自动生成器无权自行移动/删除锁。

## 6. 持久化、异步和错误

范围锁/就绪内容、输入与计划版本、保护摘要、基础候选、接受覆盖层和应用快照随保存、撤销、推荐、生成请求持久化，不是UI缓存。未确认草稿不入当前工程，候选内部仍包含真实快照和保护。

旧v1独立读取成品，不自动迁移，不调用旧固定族轮换来生成v2。缺失来源可用保存快照；历史文件逐格式检查可用性。

建议错误码：`TARGET_GAPS_UNRESOLVED, BRIDGE_NOT_READY, PLAN_VERSION_MISMATCH, PROTECTION_CONFLICT, BRIDGE_GENERATION_FAILED, STALE_SNAPSHOT, INVALID_FINAL_SCORE, INSUFFICIENT_CANDIDATES`。错误含阶段、可读message、详情、实际冲突范围与恢复操作；失败不部分写工程，恢复busy，历史/源文件保留。后台响应核对request/SPEC/CONTRACT/快照/计划版本，过期不能覆盖或自动抢播。

## 7. 必测矩阵和旧接口/测试迁移

以下清单用于P0独立检查和后续阶段，**本次未实现/未执行r3功能测试**。

| 范围 | 输入/故障 | 验收 |
| --- | --- | --- |
| 素材 | 四拍/短尾/跨块长音，多来源/重复/嵌套/句展开 | 原音符身份、句归属、来源和生成参数保留，子块独立用 |
| 时间轴 | 移动/删除、重叠/越界/缩短，2.5+0.5拍 | 不压缩，原子拒绝，240tick精确填而邻块不动 |
| 强度/记忆 | 平滑曲线、手绘/Esc、多次情绪、同峰/终点 | 无过冲，一次撤销，使用互不污染，保护所选片段 |
| 补全 | 目标未覆盖、待生成占位、局部其他gap | 不进桥，不假留白，不冒充整曲 |
| 桥 | 决定位置而生成挂起/失败、重选/无桥 | 锁已存在、未READY不连、失败保锁、新版本重走 |
| 桥上下文 | 单侧、相邻、记忆/主题/手工/主动留白 | 联合真实边界，保护优先，留白不填主旋律 |
| 连接 | 完全覆盖/部分侵入/跨桥、两侧需连/无窗 | 全部侵入拒绝，不裁桥，合法降级，无重复覆盖 |
| 端点 | 旧素材端点与桥实际端点不同 | 用真实桥首尾音，不用旧端点 |
| 最终边界 | 改桥音高/起点/时值/新增音，仅力度/配器 | 前者整曲拒绝，后者独立允许，不信自报保护 |
| 音符关系 | 句内四拍、同源切片/不同来源同音高 | 不重复过渡，只合法同源连续合并 |
| 保存/任务 | 手放移动删除、重开/撤销、旧响应/旧计划 | 保护与依赖恢复，过期拒绝，无部分写/抢播 |
| 推荐 | 假seed差异、不足、试听/取消/确认/自动 | 真实差异或说明，同一快照，一次事务全恢复 |
| 实际输出 | 基础/桥后/连接后/最终固定素材对照 | 音乐样例和影响范围，连续LMMS与三格式同谱，主体/尾音分开 |

现有 `backend/core/story_engine.py:plan` 在同一规划中分配bridge/transition窗口，再在行处理中决定与改写连接音符；`develop`有旧变体逻辑。r3必须隔离该旧路径，主流程及保护门禁由lead接线，算法worker不并发改story_engine.py。

`tests/core/test_story.py` 中 `test_bridge_in_blank`、`test_explicit_emotion_not_overwritten_by_bridge`，`test_transitions.py` 的插入/顺延过门，`test_assembly.py/test_assembly_ui.py` 的紧接组装等只覆盖旧格式，不证明r3。保留旧回归，不能直接删除来通过新要求。

后续新增明确schema的r3契约/顺序/保护/推荐测试；逐项审查 `test_peak_memory.py, test_intensity_curve.py, test_story_preview.py, test_generation_lifecycle.py, test_project_session.py, test_story_undo_redo.py, test_playback_inputs.py` 的旧假设。必须测试全过程调用顺序，并在连接规划、连接生成、最终校验分别注入越权桥改写；仅改流程图不够。

P0须独立核对输入输出、序列化、状态迁移、保护指纹、失败及测试一致性；冻结时更新CONTRACT_REV并通知角色。文档同步或现有391项测试通过不等于P0 PASS，不允许自行进入P1。

## 8. P0 定稿：持久化形状与 P1 接口（本节优先于上文候选字段）

本节由算法/前端只读评审整合。冻结后实施 P1；后续算法仍不得把存储校验当作音乐算法验收。下列字段为必填，`?` 表示显式 null 可用；未列 UI 字段不得写入工程。字段类型错误、缺字段、未知字段/版本拒绝，不能猜测转换。所有数字有限；整数不接受 bool。ID 为非空字符串，集合内唯一。JSON 只含对象、列表、字符串、数字、bool 和 null；禁止循环引用。

### 8.1 精确 P1 数据形状

```text
Project = {
 schema:"emoblocks.assembly.v2", spec_rev:"curve-workflow-v2-r3",
 contract_rev:"curve-workflow-v2-r3-p0", project_id:ID,
 ppq:480, bpm:120, grid_count:positive-int, total_ticks:grid_count*1920,
 sources:Source[], materials:Material[], label_counters:{str:nonnegative-int},
 placements:Placement[], intensity_points:Point[], blank_regions:Blank[],
 protections:Protection[], records:Record[], accepted_candidate_id:ID?,
 settings:{melody_only:bool}
}
Source = {id:ID, label:str, length_ticks:positive-int, notes:Note[], provenance:JSON-object}
Material = {id:ID, label:str, kind:"block"|"phrase"|"combination"|"bridge",
 length_ticks:positive-int, notes:Note[], provenance:JSON-object,
 generation:JSON-object?, phrase_id:ID?, children:Component[]}
Component = {occurrence_id:ID, offset_tick:nonnegative-int, snapshot:Material}
Note = {id:ID, pitch:int[0..127], start_tick:nonnegative-int,
 duration_tick:positive-int, velocity:int[1..127],
 origin:{source_id:ID, track_id:ID, source_note_id:ID}?,
 lineage:ID[], slice:{parent_emission_id:ID, offset_tick:nonnegative-int,
 parent_duration_tick:positive-int}?}
Placement = {id:ID, material_id:ID, base_snapshot:Material,
 start_tick:nonnegative-int, length_ticks:positive-int,
 emotion:"calm"|"hope"|"sad"|"suspense"|"crisis"|"resolve", emotion_variant:Material?}
Point = {tick:nonnegative-int, level:finite-number[0..1]}
Blank = {id:ID, start_tick:nonnegative-int, end_tick:positive-int, reason:str}
Protection = {id:ID, kind:"memory"|"theme"|"manual"|"bridge",
 owner_id:ID, placement_id:ID?, component_path:ID[],
 start_tick:nonnegative-int, end_tick:positive-int,
 status:"RANGE_LOCKED"|"CONTENT_READY", origin:"manual"|"automatic",
 plan_id:ID?, plan_version:positive-int?, input_fingerprint:str,
 notes:Note[], structure_fingerprint:str?, blank_mask:Range[]}
Range = {start_tick:nonnegative-int, end_tick:positive-int}
Record = {id:ID, kind:"bridge_plan"|"bridge_result"|"connection_plan"|
 "connection_result"|"boundary_plan"|"final_score"|"accepted_candidate",
 version:positive-int, status:"LOCKED"|"READY"|"FAILED"|"INVALIDATED",
 input_fingerprint:str, dependencies:[{id:ID,version:positive-int}], payload:JSON-object}
Bundle = {schema:"emoblocks.curve-bundle.v1", spec_rev, contract_rev,
 project:Project, snapshots:InputSnapshot[], attempts:Attempt[], results:JSON-object[]}
InputSnapshot = {id:ID, spec_rev, contract_rev, content_fingerprint:str, project:Project}
Attempt = {id:ID, snapshot_id:ID, input_fingerprint:str,
 state:"RUNNING"|"FAILED"|"CANCELLED"|"INTERRUPTED"|"READY"|"APPLIED",
 records:Record[], protections:Protection[], staged_materials:Material[], error:JSON-object?}
```

音乐内容是 Project；Bundle 将候选空间独立保存，不让未确认候选/锁/暂存素材污染编辑、dirty 或 undo。InputSnapshot 只内嵌输入 Project，不内嵌 Bundle/Attempt/输入快照表；阶段依赖指向 ID/版本，禁止有环。已接受候选仅存 ID 指针及扁平 Record，不回嵌输入工程。Bundle 的历史结果只用于历史试听/导出，不授予候选应用资格。加载正在运行的 attempt 返回为 INTERRUPTED，原保护/音符/版本保留；不中途恢复后台线程。

Material 的音符在 `[0,length_ticks)` 内，尾部 end 不越界；Source 同规则。来源 ID 必须解析到 sources（持久化来源元信息无文件也可编辑）；派生链保存来源，不把随机显示名当身份。组合 children 按 offset 从0连续排布、实际长度求和；每次 occurrence_id 独立，递归深度最多16，无环。组合音符必须与组件拼接快照一致（含来源、音高/起点/时值/力度）；素材没有固定四拍倍数限制、没有12段库上限。slice 必须 offset+duration 不超过 parent_duration，保留本次发声身份，来源相同不等于同次发声。

Placement 固定基础快照，length 与快照一致、material_id 指向库记录；情绪变体长度相同但不替换基础快照。允许重复放置；placement.id 独立；布局不要求顺序数组排列。用户移动每拍吸附，低层存储与自动阶段允许精确 tick。所有占用和主动留白互斥、工程内；移动/删除不压缩，不带走强度。强度至少两个点、从0到 total_ticks、tick严格递增；默认两端0.25，使用既有无过冲插值。

保护半开区间在作品内、blank_mask 包含于保护内。notes 对保护使用**绝对**起点，完整音符支撑必须位于保护范围且不交留白；所有音符（不只自报归属）穿越保护范围也计入检查。RANGE_LOCKED 可无音符/无结构指纹；CONTENT_READY 必有结构指纹和实际音符（整段主动留白除外）。bridge 的自动 origin 必指向同版本 bridge_plan；手动桥与放置原子登记（已有实际内容可立即 CONTENT_READY），automatic_decision=none 不解除手动桥。placement_id 不空必须解析；component_path 用 occurrence_id 逐层解析。其他保护类型不由 P1 自动计算，只存储和验证显式提供的记录。

### 8.2 未来阶段 Record 的强制字段与门禁

Record.payload 允许阶段扩展的 JSON 参数/证据，但下列字段必填；读写必须验证它们，不仅保留字符串状态：

| kind | payload 必需内容 | 门禁 |
| --- | --- | --- |
| bridge_plan | candidate_id, candidate_fingerprint, automatic_decision=selected/none, bridge_ids[], manual_bridge_ids[], ranges[], reasons[], joint_boundary_conditions[] | 完整桥集合独立；none 的 automatic 集合为空，手动集合仍有效；位置和全部锁原子登记 |
| bridge_result | bridge_id, plan_id, plan_version, protection_id, material_snapshot, validation | READY 要求匹配计划、保护 CONTENT_READY、实际素材/音符及指纹；FAILED 不可从桥集合移除 |
| connection_plan | bridge_plan_id, bridge_plan_version, bridge_layout_fingerprint, protection_summary_fingerprint, endpoint_refs[], windows[], decisions[] | 全部桥（手动也包括）结果就绪；窗口完整范围不交锁/其他保护；端点用实际 bridge 音符 |
| connection_result | plan_id, plan_version, original_notes[], output_notes[], actual_impact_ranges[], validation | 计划版本/摘要复查，按实际删除/新增/延音独立检查 |
| boundary_plan | bridge_plan_id, bridge_plan_version, protection_summary_fingerprint, operations[], original_notes[] | 先收集后整体冲突校验；不能改桥 pitch/start/duration 或桥内增主旋律 |
| final_score | total_ticks, notes[], protection_summary_fingerprint, validation | 固定总长、完整主旋律保护校验；单侧端点为 null，不伪造音高 |
| accepted_candidate | final_score_id, transaction_id, input_snapshot_id | 消费试听同一份最终乐谱；事务 ID 幂等；不重新随机 |

上述桥集合的所有 ID 必须能解析；缺项/重复/额外结果不可作为全部 READY 的证据。计划版本匹配不等于状态就绪。共同边界条件在生成前冻结，避免相邻桥互相等待未知结果。范围锁状态与流水线失败/失效分轴；FAILED/INVALIDATED 记录保留旧保护，**绝不自动解锁**。用户显式移动/删除手动桥才更新其保护及新依赖版本；候选改变位置/无桥创建新计划版本及新 attempt，旧记录作为失效历史保存，旧锁不参与新候选音乐但不能被旧响应修改。bridge失败中止候选；无连接窗口是有理由的成功空结果，不伪装算法失败。

CompletedCandidate 的基础快照必须完整覆盖目标范围，每个被补全目标至少与一个有效音符支撑相交，允许内部休止；新留白/未生成占位不能作为完成证据。remaining_gaps 单独返回，局部成功不授予正式整曲导出。A只写目标gap；B可在规划合法range替换非保护内容；C仅该range（留白不填）；D仅合法连接window；E仅统一校验通过的明确operation范围，不把所有阶段写域误等同目标gap。

### 8.3 指纹、快照、任务失效

统一 `sha256(domain + "\n" + canonical_json)`：UTF-8、sort_keys、compact separators、ensure_ascii=False、allow_nan=False。Project 内容域 `emoblocks.project.v2.1` 对**完整 Project**计算，不含自身hash字段（不允许UI/cache字段）；Record 的 input_fingerprint 始终是原输入快照，不指向应用后的内容，避免循环。

保护结构域 `emoblocks.protection.v1` 取 `{range, blank_mask, notes}`；notes 为按 `(start_tick,pitch,duration_tick,id)` 排序的列表，保留重复数量，取 `id,origin,lineage,slice,pitch,start_tick,duration_tick`，排除velocity。placement/component 的发声归属由保护 owner_id/placement_id/component_path 绑定，重复放置不共用保护。保护摘要域对全部有效保护（含状态/版本/基准）规范化计算；工程指纹不删除这些依赖字段。音乐方案差异另用排除 ID/seed/名称/velocity 的旋律/节奏/排布/句结构投影，不能复用带身份的保护指纹。

P1 RequestToken 精确形状 `{project_id, session_id, request_id, snapshot_id, spec_rev, contract_rev, edit_revision, input_fingerprint}`。Session 每个有效音乐事务、undo/redo、工程切换增加 edit_revision；撤销到同一内容也不复活旧任务。capture 返回 `{token, project}` 深拷贝；register/capture 不写工程或历史。结果匹配完整 token，且内容指纹/修订仍当前；取消/终态移除请求，迟到拒绝。后续阶段增加 attempt/plan版本/保护摘要依赖，在阶段接口重算核对，不允许caller声称 READY 即通过。

未来 StateEvent 另带 event_seq、phase、status：phase=BASE_COMPLETION/BRIDGE_DECISION/BRIDGE_GENERATION/CONNECTIONS/BOUNDARIES/VALIDATION/AUDITION；status=RUNNING/SUCCEEDED/FAILED/CANCELLED/STALE/INTERRUPTED。序号单调且终态不可恢复成功。能力由后端给 `target_complete, remaining_gaps, score_scope, can_audition, can_apply, can_export_final, blocking_reasons`；应用/导出再核对。UI选择、播放对象、导出对象互不隐式切换。

### 8.4 P1 可实现的公共 API 与边界

均在 backend/core，纯数据、无 Tk/平台依赖；抛 `ProjectError(code,message)`，继承 ValueError。数据返回深拷贝。

- `curve_project.new_project(grid_count=8) -> Project`；`validate(project) -> None`；`fingerprint(project) -> str`；`gaps(project) -> Range[]`；`intensity_at(project,tick) -> float`。
- `edit(project,action,**args) -> Project`，原子拷贝/完整校验；action=`add_source(source)`, `add_material(material)`, `place(material_id,start_tick,placement_id?)`, `move(placement_id,start_tick)`, `delete(placement_id)`, `resize(grid_count)`, `set_intensity(points)`, `mark_blank(start_tick,end_tick,blank_id?,reason)`, `delete_blank(blank_id)`, `set_emotion(placement_ids,emotion)`, `set_melody_only(value)`。P1 set_emotion 只记录标签并清除旧变体，不计算音乐。place 短素材/精确tick可用，UI吸附留P2；bridge素材必须原子登记内容保护。用户移动/删除手动桥更新/删除其活动保护，同时标记相关未来计划失效；自动失败不走此删除API。
- 有效编辑使现有未来阶段记录 INVALIDATED（历史和锁保留）；不能拿 INVALIDATED READY内容进入后续。缩短会截断任何放置/留白/控制点之外的锁时拒绝；允许移除旧终点及插入新终点，其他内部点超过新终点则拒绝，延长沿用原终点强度。
- `curve_session.ProjectSession(project)`：`.project` 深拷贝只读出口；`.edit(action,**args)`, `.undo()`, `.redo()`（bool是否改变），`.can_undo/.can_redo`, `.mark_saved()`, `.is_saved`, `.capture(request_id?)`, `.accepts(token)`, `.finish(token)`。noop不增加undo、不清redo、不递增revision；坏编辑不部分写；保存只在真正写入成功后mark_saved。capture相同活动request_id拒绝重复启动，finish后迟到拒绝。
- `curve_store.new_bundle(project)`, `validate_bundle(bundle)`, `save(bundle,path=None) -> Path`, `load(path) -> {format,access_mode,capabilities,bundle?,legacy?}`。快照独立保存、引用/指纹验证；snapshot版本必须匹配。save 每次独占创建新文件、fsync；已有路径拒绝，不覆盖旧快照；失败仅清理本次文件。20MiB读取上限，写入前 JSON 全部验证。
- v2 load 返回 access_mode=editable。旧 studio.v1（内含 assembly.v1/story.v1）、structure.v1、pool.v1、原始 assembly.v1/story.v1返回 access_mode=legacy_readonly；原载荷原样保留、capabilities 仅已有成品试听及各格式导出，无自动规划、迁移或 v2编辑。未知schema明确拒绝。文件可用性逐格式检查，不丢失历史。
- P1 接通 `story_engine.validate` 的 schema 分派；v2 `plan/generate` 明确 `PIPELINE_NOT_AVAILABLE`，不能送进旧自动轮换/bridge共同分配路径。**现有Tk公开入口暂保留旧路径到P2**，不在P1声称三栏/只读UI上线；新读取服务的旧工程模式供P2消费。现有旧测试全部保留，旧planner仍仅可用于旧schema。

P1不实现新旋律、切块服务/导入候选、峰值算法、情绪变奏、补全、bridge位置或音乐、连接/最终边界算法、推荐、播放器或三栏UI。未来数据用手工夹具验证持久化、引用和门禁准备；算法阶段再实现实际音乐及调用顺序。精确 tick 不为旧输出器静默量化：后续输出若不可无损表达必须 `OUTPUT_TIME_UNREPRESENTABLE` 失败，或经单独契约修订提供精确MMP；不得移动保护适配输出。

### 8.5 确定性验收夹具与阶段归属

P1执行：默认8格空项目；任意240tick素材在1200落位；删除/移动邻块不位移；重叠/越界/缩短原子拒绝；主动留白与gap区分；强度平滑/中点/移动不带线；重复使用独立；组合嵌套来源与短尾；保存两快照旧文件不变；写失败/损坏文件不改变session；undo回保存内容；capture→编辑→undo仍拒绝旧token；未来失败bridge锁/READY音符/计划依赖保存重开；手动bridge移动/删除undo；未知版本拒绝、旧工程原始内容和成品读取。已有旧回归继续运行。

P4以后执行：总7680已有[0,1200)与[1440,3360)，真实240tick补全[1200,1440)，其他gap明示；空notes素材拒绝完成。两桥[1920,5760)、[7680,11520)，一READY另一FAILED不连接且两锁保留。桥[1920,5760)连接[0,7680)、[1800,2040)、[5000,6000)全拒绝，邻接[1440,1920)合法。pitch/start/duration/重复增音拒绝，velocity独立可改；区外音延伸入桥拒绝。同来源音跨1800..2100切片只能在同次发声连续关系下合并；[A1,B1,A1]重复使用不误合。相邻/首尾单侧桥共享条件、全部就绪；手动桥+none仍保护。取消候选晚到成功不应用；试听谱=应用谱，一次undo所有层/保护/新素材恢复。tick1921/239无损保存，输出不得静默变1920/240。上述音乐/输出验收**P1不宣称执行或通过**。

### 8.6 P0 R1 修订：活动/历史引用与保护摘要

活动引用与失效历史分开校验。Record.status=INVALIDATED 时 payload.audit_context 必填 `{placements:Placement[], protections:Protection[]}`，保存失效前的相关对象独立快照；它只含这两种对象、不含 Record/Project/Bundle。此记录中的 placement/protection/bridge 引用在 audit_context 命名空间解析；跨阶段依赖依然在本容器的 Record ID/版本表解析，允许依赖记录也是 INVALIDATED，但不得作为 READY/应用证据。音符来源在工程 sources 中解析（P1 无删除来源 API）。活动记录在当前 placements/protections 表解析，不得回落历史空间绕过缺失对象。失效记录版本不改，记录内容的历史意义不改；若已经 INVALIDATED 的记录再次编辑，不覆写首次 audit_context。保存/撤销保留两者。手动桥移动/删除先在事务中给相关记录保存旧 placements/protections 快照并标记 INVALIDATED，再更新/删除活动保护；绝不保留悬空的活动 placement_id。

保护摘要函数 `protection_summary(protections)` 对明确传入的**单一活动作用域**计算：当前 Project.protections 或某一个 Attempt.protections，绝不混合 audit_context/其他候选。计划 FAILED 的 RANGE_LOCKED 和 CONTENT_READY 都保留在该作用域并纳入摘要；attempt CANCELLED/FAILED/INTERRUPTED 保留摘要用于审计但无下游授权。新候选使用其独立 protection 列表；明确无自动桥仍纳入有效手动桥保护。INVALIDATED Record 的 audit_context 仅历史，不属于活动列表。

精确投影：对每个 Protection 取全部字段，唯 notes 投影成8.3中排除velocity的结构音符列表；blank_mask 按 `(start_tick,end_tick)` 排序，component_path保持顺序，其余键保留。每保护的结构指纹仍按8.3独立核验。按 protection.id 排序保护列表，ID不可重复。使用域 `emoblocks.protection-summary.v1` 和8.3统一 canonical JSON。空列表基准如下，必须作为固定测试向量。

`protection_summary([]) = 2cf0a485a17a17a09bc172687a4418b1b6bb09e2acbd7ae175e5560dd98a2837`。非空测试必须验证列表换序摘要不变、力度变化不变、range/status/plan_version/pitch改变摘要变化，失败状态保锁仍与原保护摘要一致；删除/移动的旧摘要从 audit_context 重算，仅作审计。新明确none计划不删除手动保护，摘要仍包含该桥。

P1补充夹具：手动桥p1/L1被 READY计划/结果引用→移动→删除→保存重开→undo/redo；活动引用全部可解析，失效历史通过audit_context解析，内容/版本可追溯；旧token依然拒绝。

## 9. P2–P3 补充契约（优先于第8节的阶段边界与下述明确修订）

SPEC_REV=curve-workflow-v2-r3
CONTRACT_REV=curve-workflow-v2-r3-p23
CONTRACT_STATUS=FROZEN

P0规范正文作为历史冻结版本保留。此节是两角色只读评审后的补充草案，独立审查PASS后才FROZEN；不恢复ABCD族、不实施P4补全或bridge/连接算法。P2独立PASS后才能实现P3。

### 9.1 版本与时间、兼容

新工程仍为 assembly.v2，新的 contract_rev 为 p23；Project/Bundle/InputSnapshot 接受 p0 或 p23，两者必须按自己的数据版本验证，Bundle头与当前Project版本一致、Snapshot头与其Project一致。打开p0 v2只读取，保留原指纹、保护、记录及saved状态，不批量升级；首次成功音乐编辑在同一事务将**当前Project**标为p23，产生dirty/undo，撤销可回p0。旧输入快照/历史保留原版本、原指纹；运行 RequestToken.contract_rev 固定为p23，SPEC及会话/请求/修订门禁仍匹配。仅打开、保存、查询、主题、滚动不升级、不生成、不重算。v1及其他旧格式继续legacy_readonly，不做完整编辑迁移。

用户落点吸附：`floor((tick+240)/480)*480`，正数半拍向上；保留鼠标抓取偏移，再转canvasx坐标。越界拒绝，不用clamp把越界拖入偷偷移动到边缘。已有精确tick绘制与点击不量化。PPQ=480，四拍1920，总长由grid_count决定，BPM内部120，无速度输入。

### 9.2 算法与批次、来源

纯算法模块 `curve_melody`：

- `prepare_source(source, seed=31) -> {materials:Material[], candidates:ID[], warnings:Warning[]}`。materials是**完整待加入集合**，包括原始块/启发式句及其子块、有效默认新候选和其子块；candidates只是materials中最多3个候选父素材ID，不再重复提交。固定顺序variant/answer/rhythm，失败或音乐重复不凑数。
- `derive(material, method, seed=31, parameters=None) -> Material`。仅variant/answer/counter/rhythm/develop/density；输入不变、固定总长、单旋律。没有实际差异返回NO_VALID_VARIATION。counter是替换素材，不叠声部。组合派生为新phrase（children=[]），原组合不变；来源元数据保留原组件快照/occurrence路径，不把已改音符称为原组件未改的拼接。
- `split_phrase(phrase) -> Material[]`：父句完整音符不变，子块按父句相对四拍切分，短尾保留；子块phrase_id指向实际父句，provenance.relative_start_tick及source_start_tick明确。新父句与全部子块一次加入；独立派生子块不继续指向未修改的旧父句，其原归属入provenance。
- `music_signature(material) -> str`：以实际pitch/start_tick/duration_tick及实际length去重，排除ID/label/seed/velocity。

Source由lead的`prepare_import(path,track=0,seed=31)`规范化，保留开头留白，长度为最后实际note end（至少1tick），不沿用旧去头/截音逻辑。读取MIDI/MMP的固定4/4音符，PPQ转换沿现解析器round并记录政策；不执行原插件/效果。单旋律轨默认拒绝同时起音或重叠，不隐式提取声部；无音符/未知格式结构化失败。provenance至少 `{path,file_fingerprint,track_id,original_bpm,ppq_policy,key_context}`，key_context含tonic/mode/confidence/method；调性推断记录，不默认为C。原Source.note.id稳定且origin引用Source/track/note。

原始块按来源坐标四拍切，纯休止块可以保留但不当生成基准；启发式分句边界不得切穿持续音，保存segmentation_version/parameters/reasons；无法确定有音符完整句则默认基准为首个有音符块。phrase.children=[]，通过独立块phrase_id表达句归属；新音符有新id、origin保留血缘、lineage保存派生链，真正切片有parent_emission_id/offset/parent_duration。变化过的音符不能沿用旧发声的slice；新句完成后再切分。

Generation至少 `{method,parameters,seed,rng_version,algorithm_version,input_fingerprint,input_material_ids,base_notes,key_context,operations}`；provenance保留完整来源及组合路径。Warning为 `{code:str,message:str,details:JSON-object}`。错误为ProjectError，至少 EMPTY_MATERIAL/UNSUPPORTED_METHOD/INVALID_PARAMETERS/NO_VALID_VARIATION/PROTECTION_CONFLICT，失败不入库。

统一批次 `Batch={sources:Source[], materials:Material[], warnings:Warning[]}`；生成和组合sources=[]。每个文件独立一个导入批次，UI一次选择一个文件，失败不半导入。批次prepare不改变工程或编号；apply校验完整来源/phrase引用后一次commit、一次undo。显示编号由服务在接受时分配并持久化label_counters；取消/过期不消耗编号；已有编号不重排。

### 9.3 lead Facade 与提交权限

模块 `curve_workflow` 提供：

```text
prepare_import(path, track=0, seed=31) -> Batch
prepare_generation(project, material_id, method, seed=31, parameters=None) -> Batch
combine(project, inputs, label="组合素材") -> Material
# inputs为有序material ID或完整快照，允许重复、嵌套；草稿仅内存，确认才Batch apply
render_audition(snapshot, bpm=120) -> AuditionAsset
Controller(project=None)
  state() -> {access_mode,project|null,capabilities,is_saved,saved_path|null,
              can_undo,can_redo,memory_info|null}
  new(grid_count=8); load(path); save_snapshot(path=None)->Path
  autosave_if_needed()->Path|null（关闭前复用；失败不关闭）
  edit(action,**args)->bool; undo()->bool; redo()->bool
  capture_job(kind,target=None)->{token,snapshot:{project:Project|null,target:JSON|null}}
  accepts(token)->bool; cancel_job(token)->bool; finish_job(token)->bool
  apply_batch(batch,token)->{changed,added_source_ids,added_material_ids}
  history_items()->HistoryItem[]
  export_history(result_id,format,destination)->Path
```

kind为IMPORT/DERIVE/AUDITION/COMBINE。target描述 `{kind:source|material|placement|draft,id?,snapshot?}`，捕获时解析成不可变Source/Material；IMPORT可为null；DERIVE的project来自同次快照。旧只读仅允许历史播放和导出；不能通过Facade.edit/apply_batch绕过。前端不读Session私有字段、不解析旧工程、不构造任意新Project。

`ProjectSession.commit(project,token=None)->bool`限素材批次附加：来源/库只追加完整快照及显示编号，已有项不可改/删；几何、强度、留白、基础快照、保护和设置不变，Record只按既定失效审计规则更新。token先匹配，完整校验后一次提交，成功或noop消耗token，失败不部分写；新工程身份不能在commit中偷换。其他编辑走Session.edit的正式操作，不用commit任意替换受保护工程。

Controller保存整个Bundle，历史快照/attempt原样带上；save成功后才mark_saved。load先完整验证目标，再自动保存有实际未保存工作的当前工程，成功后才切换；new/close同样保护，保存失败保留工程/历史/请求。文件选择取消不调用load、不改变播放。新Session切换使旧token失效；新建空工程不声称自动保存。旧p0 v2首次编辑升级规则见9.1，p0输入快照不重写。

HistoryItem=`{id,label,generated_at,body_seconds,audio_seconds,availability:{wav,mid,mmp},paths:{wav,mid,mmp},edit_fingerprint|null}`，服务统一解析旧report，缺失文件保留记录；audio_seconds优先实际WAV头，主体与尾音分开。选择不播放，导出绑定显式id/格式/路径，点击时逐文件再检查。backend纯文件安全模块复用现atomic_export语义，不依赖frontend：保护源文件、临时写+fsync+原子替换、失败保旧目标。旧shared导出接口可重导出同一实现，调用契约不变。

### 9.4 独立试听与播放器、前端归属

AuditionAsset=`{wav_path,midi_path,mmp_path,body_ticks,body_seconds,audio_seconds,fingerprint,renderer_version}`。snapshot为Source、Material、放置有效变体或未提交组合草稿（均相对起点）；单旋律、中性统一音色、保留实际力度，不补休止。指纹域`emoblocks.audition.v1`覆盖pitch/start/duration/velocity、length_ticks、bpm、neutral-tone策略及renderer_version，不含UI选中或随机ID。只用实际LMMS连续渲染，不走旧planner，不把素材试听登记为成品。现MMP不能无损表达的tick明确OUTPUT_TIME_UNREPRESENTABLE，不静默量化；主体时长与含尾音实WAV时长分别返回。

后台prepare只缓存ready资产，**不调用播放器、不自动切换播放对象**；用户明确点击播放已就绪对象才开始。素材、来源、句、草稿、情绪变体、历史都用一个WavePlayer（play/status/pause/resume/close契约不变）。播放对象、当前选择、历史选择、导出绑定分别管理；过期或取消prepare返回不应用，不覆盖新ready状态，不抢播。

新公开入口为`CurveApplication(root,controller=None)`，shared CurvePage/Canvas/Cards/Theme模块；lead修改shared/app.py入口，旧UnifiedApp/StoryPage保留测试但不实例化为隐藏编辑器。撤下精细入口。左来源可折叠、中素材卡纵滚/等大、右唯一Canvas横滚、底部播放器常驻。P2只显示强度线及位置，P3才开放控制点/手绘/行内情绪与记忆。

Canvas绘制/命中/拖动同一scale及canvasx/canvasy；跨栏用x_root/y_root转换，拖动阈值后才抓取，保留偏移、边缘滚动后重算落点，Esc取消、不半提交。卡左/右组合顺序→行内草稿确认或取消；有显式试听。主要状态与错误常驻可读，不用颜色单独表达；长名称有点击全文入口。两主题用语义角色，dark严格灰阶容器+1px边框+最大12px圆角、蓝仅交互标识、情绪色为数据例外；light柔和浅底/圆角/软层次。无真实模糊、无装饰动画。1020×700优先折叠来源，较大窗口复测。

### 9.5 P3 记忆、跨界、情绪与事务

lead的`curve_memory.memory_info(project)`返回 `{peak_tick,lookup_tick,state:BOUND|PENDING_GAP|PRESERVE_BLANK,placement_id|null,component_path,range|null,protection_id|null}`。无过冲曲线最大值在控制点取得；同峰最早；内边界半开归右。peak=total_ticks时lookup=total_ticks-1，落在末音乐片段则BOUND，末空缺则PENDING_GAP，末主动留白则PRESERVE_BLANK；**不越过尾空缺/留白回搜较早音乐**。

所选四拍范围相对素材/最深组合组件起点计算，短尾裁至实际length；不用全局四拍线代替。组合component_path使用occurrence_id；整句不用生成细分当独立外框。素材内部休止仍BOUND，不是空缺；完整休止子范围可有空memory.notes，但必须独立核验确为该base相交音符的空集合，不靠blank_mask冒充用户主动留白。

自动记忆保护使用id/owner_id=`memory:<project_id>`、kind=memory、origin=automatic，唯一受管条目；BOUND保存为CONTENT_READY并持久化。PENDING/BLANK没有音乐保护条目，状态由持久化布局/曲线/留白确定，保存重开必须一致，不是UI私有标记。输入域`emoblocks.memory-input.v1`投影 `{total_ticks,placements:[id,base_snapshot,start_tick,length_ticks]按id排序,intensity_points,blank_regions}`，排除派生memory、emotion_variant、运行ID，禁止自引用。

**仅memory例外**：notes取对应placement.base_snapshot中与名义四拍range相交的完整音符，转绝对起点和placement发声ID；允许支撑超出名义range但必须在工程内、与range相交且与base独立核验一致。不得裁onset/duration。有效不可写域包括名义range及完整notes支撑，后续连接规划/情绪/最终校验都考虑；bridge/theme/manual仍保持P0严格包含规则。结构指纹排除velocity，保留身份/来源/重复数量。保护所选基础素材，不恢复原始Source。

算法`curve_emotion.emotion_variant(base,emotion,intensity_points,start_tick,protected_notes,protected_ranges=None,seed=31,parameters=None)->Material`。protected_notes是完整绝对音符，id使用**该base的Note.id**（lead移除placement前缀后传入）；结果相对素材，保护音符保留base身份、pitch/start/duration及血缘，力度可独立变化。从base重新计算，固定length，组合变体可转phrase并在generation保存原组件映射；placement.base_snapshot原组合不变。轻度旋律变化和实质编配提示保存于generation.operations/accompaniment_hints；只有音量变化不算旋律处理，素材不足/全保护不能合法变化时明确提示，不破保护强行变化。不实现整曲伴奏或bridge情绪算法。变体ID、音符及元数据按输入/seed确定，不制造重算漂移。

正式受管重算接口 `recompute(before,edited)->{automatic_memory:Protection|null,emotion_variants:{placement_id:Material|null}}`，仅由lead服务注入Session/curve_project的可选recompute；前端不传函数。事务：校验原工程→独立草稿编辑→检查其他固定保护与范围→保存失效前审计→重算新自动memory→从每个base重算相应情绪变体→完整校验保护/变体/引用→一次提交/undo。仅在明确有受管重算时，旧自动memory允许转移；没有回调仍执行P1拒绝策略。回调窄返回，不能改变来源、库、base、位置、曲线、留白、bridge或其他保护；抛错/错误返回则全事务原样。桥数据保留原先严格门禁，既有合法手动移动删除仍由正式编辑事务更新计划版本，不借记忆重算删桥或解锁失效自动桥。

P3轻改是有界纯规则，可以同步在正式编辑事务执行；异步试听及素材生成仍受完整token门禁，快速情绪变化立即失效旧任务。若引入异步情绪prepare也须同一token/基础快照与窄结果原子门禁，不因旧任务迟到覆盖较新选择。undo/redo恢复已存派生快照，不重新随机。

手绘规范化由lead服务`curve_memory.normalize_trace(points,total_ticks,tolerance=.02)->Point[]`：points为tick/level，先校验有限范围、按tick排序/同tick最后值，补两端，保留局部峰谷和方向反转；允许删除接近直线误差内的中间点，不能删峰谷或生成越界点。前端拖动只本地预览，释放一次set_intensity提交；Esc丢弃草稿，noop不改redo。命中优先级：显式控件→控制点→积木→画布；手绘模式只处理画布，不意外移动积木；跨栏素材拖入优先于手绘。

### 9.6 文件所有权与独立验收

lead独占curve_project/curve_session/curve_store/curve_workflow/curve_memory/curve_audition、story_engine主流程、shared/app入口、纯文件导出模块及shared导出重导出、集成与这些服务测试。算法仅curve_melody.py/curve_emotion.py及独立测试与仓库外音乐夹具；不改公共schema或UI。前端仅shared/curve_ui.py、curve_canvas.py、curve_cards.py、curve_theme.py、必要配对适配器与独立UI测试；不改backend/旧UnifiedApp/story_engine/入口。verifier只读冻结集成目录。

P2验收：4080tick短尾+跨1920长音、启发式句/子块独立、默认3规则和六方法重放/去重/失败、嵌套/重复组合取消确认、卡左右顺序、真实窗口拖放/首尾滚动、拒绝重叠/越界/缩短/取消、版本兼容/原子批次/保存undo、selection≠play、后台ready不抢播、旧只读历史逐格式导出。P2通过才P3。

P3验收：手绘峰谷/一次undo/Esc、缩放滚动后的真实坐标、相对四拍/嵌套组件/短尾/并列峰/内部边界/终点音乐与gap/blank、跨界完整音符和全休止片段、所选新旋律基础保护、重复使用独立、情绪A→B→A不累计、memory重定位与变体重算确定、故障不改saved/history、旧/取消/重复响应拒绝、bridge失败锁保留。固定素材保存原始/新旋律/情绪音符对照及实际LMMS WAV；设备播放串行，未人工听感/实机不冒称完成。每阶段check_frontends/full/backend/diff检查及独立冻结最多5轮，P3结束停止、不进P4。

### 9.7 补充R1反例修订：休止与不可写域

`curve_emotion.emotion_variant`的protected_ranges参数为不可变的绝对半开Range[]，即所有适用保护的名义范围及完整受保护音符支撑，可能在当前素材之外但算法只处理素材内相交部分。未提供等同空列表，不等同“从notes猜范围”。lead始终显式传入所有适用的保护范围（含全休止memory）；算法不能增加/移动/延长未保护音符使其完整支撑进入这些范围，不能填入受保护休止。已保护音符仅允许力度/音色提示，不改身份/pitch/start/duration。

lead事务独立按保护名义range与完整音符支持读取实际变体，校验音符集合和结构，不能只信算法自报遵守保护。全休止memory的实际相交主旋律必须仍为空；区外轻改可以合法发生，整段全部保护而无法旋律变化时如实提示。新增验收：基础phrase长3840，前四拍notes=[]，后四拍有旋律；保护[0,1920)且protected_notes=[]，在480增音拒绝，而后半段合法局部变化通过。bridge、theme、manual的不可写范围也继续按冻结记录传入，不放宽门禁。

## 10. P4 基础补全候选补充契约

SPEC_REV=curve-workflow-v2-r3
CONTRACT_REV=curve-workflow-v2-r3-p4
CONTRACT_STATUS=FROZEN

本节优先于第8/9节对应的阶段边界、版本和新增字段；旧冻结正文保留。只实现基础补全候选，不选择自动bridge、不新增bridge锁/计划、不生成连接、最终边界、FinalScore、试听候选或应用事务。`CompletedCandidate`是供P5消费的基础输入，绝不是最终推荐或成品。

### 10.1 版本、快照和空缺

内层assembly.v2和外层curve-bundle.v1保留。新工程及成功音乐编辑使用p4；支持p0/p23/p4所属版本。打开/保存/查询/计算/预览不改变当前Project版本或其指纹，旧Snapshot/Record/Attempt不重写。运行Token.contract_rev为当前处理器p4，InputSnapshot.contract_rev保持原Project版本；两个概念不能混同。

`curve_candidates.gap_items(project)->Gap[]`：按基础Placement及Blank占用的补集产生半开精确tick范围，素材内部休止不是gap。`Gap={id,start_tick,end_tick}`，id为`digest("emoblocks.gap.v1",{input_fingerprint,range})`；排序(start_tick,end_tick)。选中的ID必须在捕获输入重新查询；过期/不存在报STALE_GAP，不自动退回全部。低层不吸附、不整拍取整。每个目标必须完全落在真实gap，不能跨越放置或留白。所有固定保护（包括失败bridge范围锁）、名义memory及完整音符支撑均是不可写域；目标相交时请求报PROTECTION_CONFLICT，不能静默删除冲突目标。已有bridge素材或内含bridge组件的组合不可被P4自动新增使用。

### 10.2 不可变 CompletionRequest

精确形状：

```text
CompletionRequest = {
 schema:"emoblocks.completion-request.v1",spec_rev,contract_rev:"...-p4",
 input_contract_rev:p0|p23|p4,request_id:ID,snapshot_id:ID,
 input_fingerprint:str,project:Project,
 scope:"selected"|"all",target_gaps:Gap[],library_ids:ID[],
 contexts:[{gap_id,left:Placement?,right:Placement?,left_notes:Note[],right_notes:Note[]}],
 protection_summary:{fingerprint:str,ranges:Range[]},blank_regions:Blank[],
 seed:int[0..2^32-1],algorithm_version:"curve-completion-v1",budget:Budget
}
Budget={max_expansions,beam_width,material_limit,max_new_notes,max_candidates}
```

`project`为完整深拷贝，含实际素材库、已有情绪变体、强度与保护；不能回嵌Bundle/Attempt。上下文是按几何最近左右放置及其**实际**情绪后绝对音符；缺一侧为null和[]，不能伪造端点。library_ids只含允许的block/phrase/组合，排序ID；来源和完整快照通过project解析。blank_regions和protection_summary必须独立与project一致。request输入指纹是原版本完整Project指纹，不使用私有候选的p4指纹替代。

`curve_candidates.make_request(project,selected_gap_id=None,seed=31,budget=None,snapshot_id=None,request_id=None)->CompletionRequest`，先验证全部参数与输入、范围/版本/上下文/保护。ID缺省可产生内部身份；这些随机身份不用于音乐选择。无目标时目标列表为空，计算返回NOT_NEEDED，不产生素材、候选、持久化attempt或快照。只读旧格式不能启动计算。

### 10.3 算法接口、搜索和原始提案

算法仅实现 `curve_completion.propose(request,should_cancel=None,on_progress=None)->ProposalResult`，不访问Controller、不操作文件或Tk、不调用记忆算法或任何后续管线。回调是运行参数，不写入Request或工程。

```text
ProposalResult={proposals:RawProposal[],search:SearchInfo,error:Error?}
RawProposal={id:ID,placements:Selection[],score:Score,reasons:Warning[]}
Selection={gap_id:ID,start_tick:int,material:Material,emotion:Emotion}
Score={left_fit,right_fit,key_fit,rhythm_fit,motif_fit,emotion_fit,intensity_fit,repeat_penalty,total}
SearchInfo={expansions:int,generated_notes:int,termination:str,rejections:Warning[]}
Error/Warning={code:str,message:str,details:JSON-object}
```

提案包含实际素材快照及音符，不能提交占位、empty notes冒充填满。可以复用已有实际素材，重复计入评价；以联合有限beam搜索前后关系、音程/调性、节奏/动机、强度趋势、相邻实际情绪及重复程度。新情绪只作用新增放置，不能只机械映射强度。生成精确时长素材时是新的动机作曲，不对原件裁切或拉伸；原始时间/notes不变。生成记录满足第9.2通用字段，method=`completion_exact`，parameters含target_ticks和实际节奏方法，algorithm_version、seed、原始base_notes、来源/组合路径；provenance.completion={base_material_id,base_snapshot,target_ticks}，base_snapshot必须等于输入库对应素材，不能用来源不明的副本。新音符保留来源与派生血缘，改变时值的音符不沿用原slice。

默认Budget=256/8/24/256/2；各值为正整数，上限4096/32/128/2048/8。max_expansions计每次扩展选项，generated_notes计所有生成尝试的音符（失败与去重也计）；达到预算立即停止相应操作，返回真实终止原因。对每个扩展/新音符生成及阶段边界检查取消；取消丢弃提案，搜索不无限重试。输入库固定排序，seed只驱动明确的局部规则；不能读时间或系统随机数猜音乐。

score除total外均有限0..1，缺侧上下文对应fit=.5。total=.20*left_fit+.20*right_fit+.12*key_fit+.08*rhythm_fit+.10*motif_fit+.10*emotion_fit+.10*intensity_fit-.10*repeat_penalty。分量按所有目标及候选已选布局平均；reasons记录具体左右关系、音程/节奏/调性、强度与情绪取舍、重复数量。稳定排序total降序、实际音乐投影hash升序；不靠ID/名称/seed/力度/标签宣称差异。搜索失败仍返回预算计数、拒绝项和未解决目标。

### 10.4 独立完成门禁、情绪及记忆

lead `curve_candidates.prepare_completion(request,should_cancel=None,on_progress=None)->CompletionOutcome`调用算法取得提案，然后逐个构建、独立验证、去重、排序。纯准备不写文件、不访问当前会话。`validate_request/validate_candidate/validate_outcome`支持存储恢复时纯验证，不运行算法、渲染器或后台线程。

构建私有Project：原输入完整拷贝，仅在目标内附加新Placement及原输入库没有的实际Material；新素材仅属于candidate/staged，不分配正式显示编号。来源、label_counters、强度、总长、BPM、留白、原放置基础/位置/情绪/变体必须原样。candidateProject.contract_rev=p4，输入快照仍原版本。历史Record仅依原正式invalidate_records保留审计并失效，不新增任何后续阶段记录；既有非受管保护逐字段保留。

先用P3正式curve_memory.recompute获得新自动memory，再为新增放置从base落情绪变体；P4算法不另写记忆规则。既有放置保留输入的完整快照/变体，不能为统一新算法而改写区外音乐；若新记忆与旧音乐矛盾，候选明确PROTECTION_CONFLICT，不悄悄恢复来源或改邻块。新变体必须来自本次base、长度相同、保护内音高/起点/时值及休止完整保持。完整Project验证继续使用P3的旧手工保护、历史自动记忆和跨四拍长音兼容规则，不删除或放宽bridge锁。

独立门禁：

1. 新放置实际范围完整位于所属目标、彼此无重叠，原有放置/留白/全部固定保护未改；不移动邻块凑长。
2. 每个目标的新增占用并集等于目标完整范围，每个目标至少一条实际有效音符支撑相交。empty notes、部分覆盖、新留白、待生成bridge、只填READY均拒绝。
3. 生成后重新查询remaining_gaps，目标已无缺口，其他gap保持原范围；新主旋律没有进入保护或主动留白。素材内部自然休止仍允许。
4. 验证所有素材/来源/FK、实际变体、当前及历史保护、计划依赖，计算实际绝对notes；不信提案自报范围/score/status。
5. 私有candidateProject完整校验、实际音乐和指纹一致；不调用bridge、connection、boundary、旧planner或最终应用。

### 10.5 CompletedCandidate 与多候选结果

```text
CompletedCandidate={
 schema:"emoblocks.completed-candidate.v1",spec_rev,contract_rev:p4,id:ID,
 snapshot_id:ID,input_fingerprint:str,request_fingerprint:str,project:Project,
 added_placement_ids:ID[],staged_materials:Material[],notes:Note[],
 target_resolution:[{gap_id,start_tick,end_tick,complete:true,note_ids:ID[]}],
 remaining_gaps:Gap[],base_write_ranges:Range[],
 emotion_arrangement:[{placement_id,emotion}],memory_info:JSON,protection_summary:str,
 score:Score,reasons:Warning[],provenance:JSON-object,
 content_fingerprint:str,music_fingerprint:str,
 capabilities:{score_scope:"BASE_COMPLETION",target_complete:true,
 can_audition:false,can_apply:false,can_export_final:false}
}
CompletionOutcome={schema:"emoblocks.completion-outcome.v1",spec_rev,contract_rev:p4,
 snapshot_id,input_fingerprint,request_fingerprint,
 status:"SUCCEEDED"|"INSUFFICIENT"|"FAILED"|"CANCELLED"|"NOT_NEEDED",
 candidates:CompletedCandidate[],differences:JSON-object[],
 shortage_reasons:Warning[],unresolved_targets:Gap[],search:SearchInfo,error:Error?}
```

request_fingerprint=digest("emoblocks.completion-request.v1",完整Request)，content_fingerprint为完整私有Project指纹，candidate id按请求指纹与内容确定。notes是全部放置的实际绝对Note（含ID/血缘），emotion_arrangement只列新放置，memory_info由P3服务派生，protection_summary是实际候选保护摘要。provenance保存每个目标来源、生成方法、参数、种子、算法版本；输入/目标/评分及音乐差异可完整复现。

音乐差异域`emoblocks.completion-music.v1`：固定总长+按时间/音高/时值排序的实际音乐，排除所有身份/名称/seed/velocity/情绪标签。只合并确属同次发声的连续slice，不能合并同音高重复音；以实际P3变体后的音乐去重。不同来源ID或标签不得冒充差异；排列和句结构变化必须在实际音乐中有证据。differences列实际pitch/rhythm/排列差异及对应范围，不声称连接听感。

默认期望两套，返回至budget.max_candidates（最多8）。有效去重后至少2为SUCCEEDED，1为INSUFFICIENT并说明可用素材、受保护范围、去重或预算原因；0且有目标为FAILED，0无目标为NOT_NEEDED，CANCELLED不得保存部分候选。未完成提案不进入CompletedCandidate列表，unresolved_targets保留原目标；局部候选remaining_gaps非空不影响基础目标完成，但任何候选都没有应用/试听/整曲导出资格。搜索终止原因至少ENOUGH_CANDIDATES/EXHAUSTED/BUDGET_EXHAUSTED/CANCELLED/NO_TARGETS/PROTECTION_CONFLICT/NO_VALID_MATERIAL。

### 10.6 attempt 持久化、取消与失效

P4 Attempt保留第8.1全部字段并增加唯一`completion`：

```text
completion={schema:"emoblocks.completion-attempt.v1",spec_rev,contract_rev:p4,
 request:CompletionRequest,outcome:CompletionOutcome?}
```

旧Attempt没有completion，按原形状读取/保存，不注入新字段。P4 Attempt.records/protections/staged_materials均[]，候选的实际保护和暂存材料保存在outcome内各独立Project，不将多个候选的保护混到原编辑。输入Snapshot表引用原版本原指纹；Bundle头继续匹配当前Project所属版本，可包含自身明确版本p4的completion对象。snapshot.id=request.snapshot_id、attempt.id=request.request_id，input_fingerprint与请求/快照一致。旧同版本已有Snapshot表和Record引用保留。

Attempt.state：RUNNING；SUCCEEDED/INSUFFICIENT对应READY（只表示基础候选暂存）；FAILED/CANCELLED/INTERRUPTED；P4禁止APPLIED。输入改变后由completion_state即时判为STALE（在P4 attempt恢复/序列化中允许STALE扩展状态），不能交P5，不能用旧epoch/撤销回同内容复活。终态不能被重复回调替换；取消立即消耗token并标CANCELLED，协作检查让搜索终止；迟到结果不落库。RUNNING保存后重开为INTERRUPTED，无后台线程，outcome为null，不假成功。P4保存验证重新核验请求和全部候选，不把暂存candidate混为bundle.results。

Project.is_saved、undo/redo、库和编号不因staging改变。Controller另有不进入Project的staging_dirty：显式保存包含整个bundle；自动保存保护在music dirty或staging_dirty时执行，失败停止关闭/新建/切换，不虚报已保存。保存成功才清staging_dirty；运行/取消/失败记录也是暂存变更，UI音乐保存状态与候选状态分别表示。只读旧工程不能建立attempt。

### 10.7 Facade、事件与前端

```text
Controller.gap_items()->Gap[]
Controller.capture_completion(selected_gap_id=None,seed=31,budget=None)
 ->{token:RequestToken?,request:CompletionRequest,attempt_id:ID?,immediate_outcome:CompletionOutcome?}
Controller.finish_completion(token,outcome)->bool
Controller.cancel_completion(token)->bool
Controller.completion_state()->{status,attempt_id:ID?,input_fingerprint:str?,
 request:CompletionRequest?,outcome:CompletionOutcome?,message:str}
```

无目标capture立即NOT_NEEDED，不创建持久化attempt/snapshot、不启动线程。selectedGap/参数错误前先拒绝，不能半注册。重复completion启动拒绝DUPLICATE_REQUEST；输入改变/undo/redo/切换通过Session revision与完整token失效；完成前再次检查归属及实际candidate，成功只更新_bundle暂存，不走Session.commit/edit。cancel_job对completion转派cancel_completion；finish_job不能提前消费completion结果。generic finish_completion验证失败应将attempt置FAILED、提供详情并释放busy；验证/回调抛错也不能永久RUNNING。计算失败/取消/失效不改当前播放或选中成品。

`on_progress`传`{event_seq,phase:"BASE_COMPLETION",message,expansions}`，单调event_seq；UI在队列外封装原token，在主线程检查完整身份和序号、终态。只显示真实工作阶段及可选elapsed，不捏造百分比/预计结束。回调不操作Tk、不持久化UI计时。

前端在现有三栏内选实际gap、显示计算状态与取消、候选基础排布/情绪/remaining_gaps、不足/失败/已失效提示。可以在唯一画布切只读候选预览，明确“基础候选 · 尚未处理bridge与连接”，不改变当前工程与素材列表；退出预览恢复选择/滚动/播放对象。不新增第四栏、弹窗工作流、最终确认应用、候选完整试听或导出入口。中性素材试听不得被标为完整候选；已有素材播放器/历史成品导出保持可用。控制点/块拖动/手绘优先级保留；只有真实空缺选择入口，不能将任意手绘点击变成gap选择。主题/窗口/预览不dirty、不undo、不触发生成。

### 10.8 所有权、失败与验收

lead：curve_candidates/curve_workflow/curve_store/project/session版本、纯候选完成/范围/保护/快照服务、主流程接线与相应测试。story_engine仍仅lead；v2旧最终生成入口继续PIPELINE_NOT_AVAILABLE。算法：新增curve_completion.py及test_curve_completion.py、仓库外固定音乐样例，不改schema/记忆/UI/主流程。前端：shared curve_ui/canvas及新增curve_completion_ui.py（可选）、允许配对适配器与独立P4 UI测试，不改backend或播放器契约。verifier只审查冻结集成目录，不审查自己的副本、不修改代码。

拒绝/异常使用结构化code/message/details，至少STALE_GAP/STALE_SNAPSHOT/PROTECTION_CONFLICT/NO_VALID_MATERIAL/NO_SOLUTION/BUDGET_EXHAUSTED/INCOMPLETE_TARGET/INVALID_CANDIDATE/CANCELLED；不会静默转留白、延长总长、弱化保护或进行无限重试。输出器无法表达精确tick时OUTPUT_TIME_UNREPRESENTABLE，数据原样保留，不量化取巧。P4 UI没有candidate试听，lead验收可在隔离目录把实际基础音符交已有中性LMMS渲染，材料标为“基础拼接对照，未经过bridge/连接”，不能当最终连接听感。

必须覆盖用户十二项：240tick空缺且邻块/强度/总长不变；只选一gap；多gap联合重复控制；blank与内部rest；空notes/占位/部分覆盖拒绝；峰值gap先base记忆，组合/短尾/跨长音；手动bridge/失败锁/手工保护；post实际去重与不足；当前编辑/库/编号/saved/undo快照隔离与迟到重复取消；attempt保存及RUNNING重开INTERRUPTED；不调用P5–P7/旧planner；原始精确tick及输出拒绝。保留P3旧手工memory读取与历史自动memory长音+bridge审计回归。

契约先算法/前端只读评审、verifier独立PASS再标FROZEN并同步；实现后自测冻结verifier最多5轮。契约与实现轮数分别记录，不重置前阶段。自动后端/完整/双端契约/diff、程序化Tk、实际LMMS/设备、人工视觉/听感与Windows实机分别记录。实际渲染与设备串行，未执行明确待验。完成P4停止，不进入P5，不推送/发布/安装模型。

### 10.9 只读评审整合：精确门禁与状态矩阵（覆盖上文歧义）

- Request.selected的target_gaps恰好等于选中完整Gap，all恰好等于输入全部Gap列表；禁止子范围冒充。library_ids是完整允许集合（排除bridge及嵌套bridge），固定ID排序；material_limit只限制搜索根，不裁来源/父句/组合快照闭包。contexts与target一一对应同序，左右Placement和实际notes、blank及保护摘要必须等于独立输入查询。
- capture成功：token.request_id=request.request_id=attempt.id；token.snapshot_id=request.snapshot_id=Snapshot.id；token/request处理版本p4，request.input_contract_rev=Snapshot.contract_rev=request.project.contract_rev；原输入指纹四处相同。旧输入版本绝不因注册/计算/保存升级。
- `validate_request(request)`, `validate_candidate(request,candidate)`, `validate_outcome(request,outcome)`均返回None或结构化ProjectError；所有Budget拒绝bool。max_candidates允许1，但期望始终至少2，只有1时INSUFFICIENT。
- 原始搜索返回最多`min(32,max(beam_width,4*max_candidates))`个完整RawProposal，累计包含的素材notes不超过65536；受beam、根数量及扩展上限限制，是有限备选池，不宣称穷尽全部合法音乐。Raw终止RAW_POOL_LIMIT/RAW_POOL_EXHAUSTED/EXHAUSTED/BUDGET_EXHAUSTED/CANCELLED/NO_TARGETS/PROTECTION_CONFLICT/NO_VALID_MATERIAL，**不能**按两条raw宣布ENOUGH_CANDIDATES。lead处理整个有界池（达到最终上限可停），仅在post门禁及实际去重后至少2才将最终termination置ENOUGH_CANDIDATES。SearchInfo新增`raw_termination:str`保留实际原始终止原因；不足原因必须说明有限备选池/剪枝/去重，不能伪称所有方案无解。
- generated_notes只计算法构作新素材的实际音符（每个生成尝试，包括重复/失败），每生成一音符之前检查，不超max_new_notes；复用原件不计生成音符但计扩展，组合展开复用不算新作曲。音符预算耗尽后仍可在剩余扩展预算内复用已有素材；不能丢弃已经完整的提案。RawPool音符上限同样计复用，防止规模无限增加。未解决目标由lead基于实际Completed集合计算，不由Raw自报READY决定。取消/主线程异常未取得准确计数时SearchInfo.expansions/generated_notes可以null，不能伪造0；正常算法返回必须为实际非负整数。异常终止可为ERROR，raw_termination为UNKNOWN。
- P3 recompute对旧placement返回的变体**不得写回**；只采纳其正式新自动memory和新增placement变体，再独立验证。输入已BOUND时记忆归属/范围/结构不能移走，只有其输入基准指纹随私有布局刷新。旧快照有自定义参数/旧变体时仍逐字段保留；不能借新版默认参数重算区外声音。若与正式新记忆/保护矛盾，明确拒绝而不覆盖旧音乐。
- staged_materials恰等于私有Project新增库项，全部被新增放置使用，无额外未使用项、重复或同ID异内容；added_placement_ids和emotion_arrangement恰对应新增放置。target_resolution恰对应完整目标，其note_ids恰为实际notes中与目标相交的新增发声。base_write_ranges为目标的规范化并集。remaining_gaps恰为gap_items(candidate.project)，使用候选指纹的ID；非目标空缺仅范围保持原样。INSUFFICIENT有一套完整有效候选时unresolved_targets=[]，方案不足不等于目标没填满。
- differences形状为`{left_id,right_id,types:[pitch|rhythm|arrangement],ranges:Range[]}`；ID引用实际候选，变化范围/类型由post实际音乐独立计算。音乐投影进行slice合并前给parent_emission_id加placement发声命名空间，再要求同源、pitch一致、offset连续、绝对时间连续、parent_duration相同；只在投影中去除身份。Candidate.notes仍保留模型原始血缘，不改工程或保护。变更音高或时值的新音符都不沿用旧slice。
- RUNNING/INTERRUPTED的outcome=null；READY的outcome为SUCCEEDED/INSUFFICIENT，error=null；FAILED的outcome为FAILED，attempt.error与outcome.error相同；CANCELLED的outcome为CANCELLED且无候选；STALE可保留原outcome供审计，但无任何后续消费资格。工程有效编辑/undo/redo必须持久标记原READY/RUNNING为STALE，更新staging_dirty，返回同内容也不复活。worker不能替换终态；此规则不禁止正式编辑使READY失效。重开RUNNING→INTERRUPTED的派生改动也标staging_dirty，下一次保存可记录它；不重建旧token。
- 无目标固定返回token=null/attempt_id=null/immediate_outcome=NOT_NEEDED、candidates=[]、expansions=generated_notes=0、termination=raw_termination=NO_TARGETS。临时Request身份不登记，staging_dirty、既有暂存、saved/undo/编号/播放不变。
- 新增Facade `Controller.fail_completion(token,error)->bool`，用于计算或结果回调异常，规范化结构错误并将所属活动attempt置FAILED、释放token；无归属/过期/重复返回false，不污染新attempt。`state().capabilities.completion`仅v2可用。completion_state.status明确为IDLE/RUNNING/READY/FAILED/CANCELLED/STALE/INTERRUPTED/NOT_NEEDED，纯查询不写状态。
- UI关闭/新建/打开继续现有忙碌限制；用户先明确取消，再执行保护保存。允许显式保存RUNNING，文件如实记录运行态，重开即INTERRUPTED；不得先存RUNNING再仅内存取消并声称取消已保存。预览进入/切换/退出不调用工程切换或播放器关闭，不清缓存、不替换播放对象；画布只读，当前素材区保持原编辑库。
- 额外验收：两条raw仅标签不同、第三条实际音高不同时应得到两套post候选；真实gap只填一半Request拒绝；旧放置自定义emotion参数不被默认重算；运行播放时反复候选预览不抢播；候选编辑后undo回原内容仍STALE；暂存变化自动保存失败停止切换/关闭；旧Snapshot/Attempt归属版本和历史managed身份/跨界保护不被兼容升级破坏。

### 10.10 前端只读评审补充：公共状态与空素材

- `Controller.state()`在原字段之外公开`staging_dirty:bool`，音乐`is_saved`与候选暂存保存状态分别显示。只查询、无目标计算、候选预览不能修改两种状态。
- 现有`Controller.accepts(token)->bool`扩展支持completion：检查完整RequestToken、Session revision、所属活动任务及其RUNNING状态，纯查询不消耗token。取消A再启动B后，A的迟到进度即使输入内容指纹相同也不能通过；UI不访问Session私有字段。
- `completion_state()`新增`error:Error|null`；FAILED时与outcome.error/attempt.error一致，其余状态保留真实状态对应的详情。`fail_completion`返回false时，UI不得把该错误覆盖到较新任务。
- Candidate.memory_info使用第9.5节已冻结的`MemoryInfo`，protection_summary明确为候选实际保护的指纹。只读预览使用候选自己的记忆定位与保护，不能沿用当前编辑的标记。
- 每个新增独立Placement的实际Material必须至少有一个有效音符；整段empty-notes素材即使与其他有音符素材共同覆盖目标也拒绝。允许非空整句/组合中的自然休止，不要求每tick发声，也不把素材内部休止当作新gap。
- 候选详情显示新放置`emotion_variant.generation.warnings[].message`，尤其如实说明`melody_changed=false`；编配提示仍标为suggested-not-rendered，不声称已经完成伴奏渲染。编辑选择、gap选择、候选预览选择和播放对象独立。
- 必测旧放置自定义seed=99、max_changes=1时，P3默认重算产生不同区外变体仍不能回写；新增记忆实际冲突应拒绝，不能仅因默认重算的旧变体不同误拒合法补全。另测半个empty素材+半个有音符素材覆盖一个目标的伪完成拒绝、取消后同指纹任务进度隔离、预览内警告与真实保护来源。


## 11. P5 bridge 补充契约（FROZEN，P5-CONTRACT ROUND2 PASS）

本节已独立PASS并标FROZEN；仅授权本节P5实现，历史正文和停止边界不变。处理对象版本p5；历史p0/p23/p4规范和数据不改写。严格顺序为基础输入实际完成→位置判断→位置与全部锁原子登记→完整桥乐句及情绪→独立内容认证→P5就绪；无连接块、最终边界、正式试听／应用／成品导出。P5就绪不是FinalScore。

### 11.1 版本、输入认证与快照归属

Project/Bundle形状保持不变。P5为独立阶段对象，不因捕获、计算、预览、保存升级音乐Project；现有p4新工程／编辑规则保留，输入p0/p23/p4及其快照按原版本验证。P5请求、计划、结果、attempt扩展对象使用`contract_rev=curve-workflow-v2-r3-p5`，不与input_contract_rev混同。Session.capture增加可选处理版本参数，默认行为保留；P4处理Token仍p4，P5处理Token明确p5；旧Token/旧记录不重写。

BridgeRequest精确形状：

```text
{schema:"emoblocks.bridge-request.v1",spec_rev,contract_rev:p5,
 request_id,snapshot_id,session_id,edit_revision,input_contract_rev,
 input_fingerprint,input_project:Project,
 input_kind:"completed_candidate"|"current_complete",
 completion_ref:{attempt_id,candidate_id,request:CompletionRequest,candidate:CompletedCandidate}?,
 base_project:Project,base_fingerprint,resolved_ranges:Range[],remaining_gaps:Gap[],
 base_notes:Note[],protection_summary:{fingerprint,ranges:Range[]},
 blank_regions:Blank[],plan_id,plan_version,seed,algorithm_version:"curve-bridge-v1",
 parameters:{policy:"auto"|"none",max_windows,max_window_blocks,max_window_tests,max_notes}}
```

默认参数auto/2/8/128/512；上限分别8/32/2048/4096，均正整数拒绝bool；seed为0..2^32-1。内部有限枚举按音乐时间与音乐特征确定性排序，达到预算明示终止；不得运行时随机猜测或无限重试。policy=none是用户明确另建计划的选择，不是错误降级。

completed_candidate输入由Controller用真实completion_attempt_id/candidate_id查当前Bundle，不能接受UI自带副本。所属P4 Attempt必须READY、Outcome为SUCCEEDED或INSUFFICIENT，指定候选须唯一且通过P4纯validate_request/candidate/outcome。INSUFFICIENT的一套合法候选可用；候选数不是完成门禁。P4请求的原Project必须等于当前编辑，原输入指纹匹配，STALE/FAILED/INTERRUPTED拒绝。BridgeRequest同时保留原编辑快照和候选基础Project，不把两种指纹混用。基础来源、目标完成、真实音符、即时记忆和保护摘要重新纯认证，不重新运行P4搜索、记忆或情绪算法。

current_complete输入要求当前Project.gaps=[]；completion_ref=null，base_project=input_project原样，不创建伪CompletionRequest/Candidate或额外素材。全部主动留白可成为完整排布，但不凭空制造旋律。partial候选保留实际remaining_gaps；resolved_ranges是[0,total_ticks)扣除remaining_gaps的规范化补集（包含原占用、已补全和主动留白），不是P4 base_write_ranges。窗口完整落在某个resolved_range，不跨任何未解决范围；无正式整曲完成资格。

BridgeRequest的request_id/snapshot_id/session_id/edit_revision/input_fingerprint等于新完整Token；snapshot表保存原版本input_project，base_project私有只读。已保存READY事实可在重新加载的当前会话中经新的请求捕获认证；旧任务Token不可复用。有效编辑/undo/redo使P4及P5旧attempt持久STALE，撤销回同内容也不复活。

### 11.2 位置提案、共同边界与计划

纯算法`curve_bridge_music.decide(request,should_cancel=None,on_progress=None)->BridgeProposal`。它只做内部提案，不登记或对UI公布位置：

```text
BridgeProposal={schema:"emoblocks.bridge-proposal.v1",spec_rev,contract_rev:p5,
 request_fingerprint,decision:"selected"|"none",windows:BridgeWindow[],
 reasons:Warning[],assessments:JSON-object[],joint_boundary_conditions:JointBoundary[],
 search:{tested_windows:int,termination:str}}
BridgeWindow={id,start_tick,end_tick,placement_ids:ID[],
 context:{left:JSON-object?,right:JSON-object?,motif_note_ids:ID[],key_context:JSON-object},
 emotion_segments:[{start_tick,end_tick,emotion}],blank_mask:Range[]}
JointBoundary={id,left_bridge_id,right_bridge_id,tick,relation,reasons:Warning[],
 left_endpoint:{pitch,start_tick,duration_tick}?,
 right_endpoint:{pitch,start_tick,duration_tick}?}
BridgePlan={schema:"emoblocks.bridge-plan.v1",spec_rev,contract_rev:p5,
 id,version,request_id,snapshot_id,input_fingerprint,base_fingerprint,
 candidate_id:ID?,request_fingerprint,decision,windows:BridgeWindow[],
 inherited_bridge_ids:ID[],protection_refs:[{bridge_id,protection_id}],
 reasons,assessments,joint_boundary_conditions,search,
 range_lock_fingerprint,plan_fingerprint}
```

request_fingerprint=digest请求全对象；BridgePlan id/version来自Request。plan_fingerprint为不含自身字段的完整Plan摘要。新attempt创建新的plan_id、严格递增plan_version（当前Project历史attempt最大值+1），失败重选／改none不修改旧plan。none必须windows=[]、真实理由、预算及对照评价；异常不得转换成none。

位置先比较原排布是否自然成立，分析实际动机、调性、节奏、音域、情绪／强度走势与后方入口空间，评价采用桥与保留基础的收益；相近优先少改。允许2、3、4块及更长区域，不仅以长度／同情绪触发。assessments必须包含原布局与预期bridge收益及具体理由，确定性同分优先较少／较短修改、较早范围。无可写窗／已有音乐成立均可有明确none，算法失败不是none。

窗口范围精确tick、不重叠、不越总长、不交remaining_gaps；基础放置与主动留白覆盖整个窗口。不能切断跨窗边界的实际完整音符，必要时调整窗口或放弃。placement_ids准确列所有相交原放置；原基础Project、位置、情绪和强度一律不改。blank_mask等于原主动留白与窗口交集；主旋律不可进入mask，包括区外延音。原始拼接快照保留，桥是覆盖层，不是破坏性切素材。

所有输入保护包含RANGE_LOCKED失败锁、旧手工保护和记忆完整音符支撑；`memory.protected_ranges`是选位禁写域，不能缩小名义区间而忽略长音。手动bridge及已有自动bridge锁均进入inherited_bridge_ids，保持原实际内容与保护逐字段不变，none不解除它们。多个自动窗先统一解决冲突；共同边界在生成前冻结，相邻窗不读取被覆盖的旧端点互相猜测。真实缺侧为null，不能伪造双侧。每个实际非null端点须有确定pitch/onset/duration并在其对应窗内，结果严格兑现；null说明真实休止／不存在。共同条件不允许跨留白发声。

### 11.3 原子范围锁与保护集合

BridgeProtection沿用第8.1的Protection精确形状，不新增纯UI状态。新自动锁kind=bridge、origin=automatic、owner_id=window.id、placement_id=null、component_path=[]、plan_id/version对应Plan、input_fingerprint为Request原编辑指纹、精确范围和blank_mask对应Window。RANGE_LOCKED时notes=[]、structure_fingerprint=null；内容认证后才CONTENT_READY，保存实际绝对发声身份及结构指纹。

Controller.lock_bridge(token,proposal)独立认证提案，构建完整Plan和全部新锁，在私有Bundle拷贝上validate，成功后一次替换。事务失败不公布Plan、不留下半个锁；前端只能显示此返回的锁定数据。保护集合为基础Project原protections逐字段拷贝＋全部新自动锁；不替换记忆，不把不同候选的锁混合。初始range_lock_fingerprint绑定整个初始集合；升级内容不改Plan，在Outcome另存实际保护摘要。

已有bridge锁也参与必需结果集合。手动CONTENT_READY用原放置实际素材、绝对notes、原plan/保护登记导入结果，不自动改写；历史自动桥有实际就绪结果才能作为继承内容。任何继承的未就绪／失败桥锁继续保留并阻止整个计划P6就绪，不能遗忘它或假装只验证新桥。

### 11.4 完整乐句、来源、情绪及结果

统一旋律模块增加`curve_melody.compose_bridge_phrase`能力，由独立bridge模块调用，不能只拉长首尾音插值。输入为实际左右／窗内动机音符、精确目标长度、key、情绪与强度轨迹、禁写域、留白、共同边界、seed和明确版本。提取节奏／音程动机，在句内发展、为后句保留入口；缺侧按单侧引入／收束；原件不拉伸裁切。新自动桥以kind=phrase的完整乐句存储，bridge身份由Plan/Result/Protection绑定，实际length等于window长度；不能让子块phrase_id指向kind=bridge，也不能伪装组合children。base_material也是未处理phrase，先完整作曲再一次情绪处理，已有kind=bridge的手动素材仍走原完整保护门禁，绝不削弱P3校验。非全留白窗必须有有效notes。

实际音符合法单旋律、整数tick、不交留白／保护、不越窗。每个派生音符必须通过具体motif父音符、变换操作回到Request中真实实际音符；已知origin三字段保留，lineage是具体父链，不能借无关合法来源。改变音高、起点或时值不沿用旧slice。来源认证依据静态操作记录和真实父快照，不重新生成旧音乐。

```text
BridgeResult={schema:"emoblocks.bridge-result.v1",spec_rev,contract_rev:p5,
 request_id,snapshot_id,request_fingerprint,base_fingerprint,
 plan_id,plan_version,plan_fingerprint,bridge_id,protection_id,
 origin:"automatic"|"inherited",range:Range,status:"READY"|"FAILED"|"CANCELLED",
 base_material:Material?,material:Material?,children:Material[],
 emotion_processing:JSON-object?,operations:JSON-object[],
 notes:Note[],content_fingerprint:str?,error:Error?}
RawBridgeOutcome={schema:"emoblocks.bridge-raw-outcome.v1",spec_rev,contract_rev:p5,
 request_fingerprint,plan_id,plan_version,status:"SUCCEEDED"|"FAILED"|"CANCELLED",
 results:BridgeResult[],error:Error?}
BridgeOutcome={schema:"emoblocks.bridge-outcome.v1",spec_rev,contract_rev:p5,
 request_fingerprint,plan_id,plan_version,plan_fingerprint,
 status:"SUCCEEDED"|"FAILED"|"CANCELLED",results:BridgeResult[],
 base_fingerprint,notes:Note[]?,content_fingerprint:str?,
 protection_summary:str,remaining_gaps:Gap[],error:Error?,
 capabilities:{score_scope:"BRIDGE_STAGE",can_plan_connections:bool,
 can_audition:false,can_apply:false,can_export_final:false}}
```

基础桥音乐和情绪后音乐分别保存。emotion_processing记录算法版本、参数、seed、pass_count=1、原情绪位置段和逐音符操作；只从base_material计算一次，绝不能继续变换上次变体。原情绪位置保持，音符按起点归属单一段；各段读取同一未处理基础快照，只合并该段所属音符，任何音符最多一次处理。共同边界音符在情绪步骤冻结；编配提示如实为suggested-not-rendered，不能宣称已完成伴奏。

children为最终完整乐句按四拍切分的可追溯子块，短尾真实长度，phrase_id=material.id、相对位置、origin/lineage/slice与父快照一致。内部四拍分界不是新连接边界，不为每四拍再生成桥。base_material.generation保存目标、实际动机父快照、key、参数／seed／算法版本及逐音符变换；operations与base_material真实音高／时间／来源一一对应，最终变化由emotion_processing静态账本认证。结果content_fingerprint绑定range、blank_mask和最终实际绝对notes（用bridge_id命名发声），不含velocity的保护结构指纹另外保存。

失败／取消结果material/base_material=null、children/notes=[]、content_fingerprint=null、error非null；不冒充实际音乐完成。继承桥READY完全复用原锁和实际音乐，保留原输入保护plan引用及实际音符身份；不能重新走情绪或改写base。

### 11.5 流式认证、就绪门禁及失败状态

`curve_bridge_music.generate(request,plan,should_cancel=None,on_progress=None,on_result=None)->RawBridgeOutcome`有限生成全部新桥，并为继承桥提供事实结果；on_result仅将完成的真实BridgeResult送队列，不写Controller／Tk／文件。生成开始前必须收到真实锁定Plan；纯validate_plan可重算初始锁摘要／指纹，但不决定位置。

Controller.record_bridge_result(token,result)->bool逐项独立认证后暂存并升级所属锁；完全重复返回false，不重复写或清锁；冲突重复、未知／额外桥、错版本和非法音乐明确失败，已有认证内容与锁保留。生成或认证某桥失败允许保存此前有效结果。Controller.finish_bridge(token,raw)->bool对完整桥集合再独立校验：exactly全部automatic＋inherited，缺项、重复、额外结果拒绝；Raw与已登记结果不一致拒绝。所有CONTENT_READY且无失败、身份／版本／范围／共同端点／保护／来源／结构／外部音乐认证通过，才SUCCEEDED和can_plan_connections=true。

Outcome成功notes为原实际基础拼接删除**完整支撑位于自动窗内**的音符＋各自动桥绝对notes；原位保留所有窗外音符，跨边界音符在选位已拒绝，不能悄悄截短。继承桥是原拼接的一部分，不再次叠加。剩余空缺、原总长、强度、留白与位置仍准确；Outcome指纹对实际完整splice计算，不信算法自报。

BridgePlan内容不可变；保护轴独立于attempt终态。状态phase=BRIDGE_DECISION/BRIDGE_LOCKED/BRIDGE_GENERATION/BRIDGES_READY；state=RUNNING/READY/FAILED/CANCELLED/INTERRUPTED/STALE。bridge_state无任务时status=IDLE、phase=null、request/plan/outcome/preview=null、集合为空、所有P5下游能力false。失败、中断、取消、过期均不解除锁或丢弃已认证内容，不能进入P6。无桥也是完整Plan版本，正常none可READY；存在失败继承锁则不能READY。重新选位或none另建attempt和递增版本，旧数据原样保留审计。

旧／重复／取消后回调不得改终态、消耗新任务或清锁。编辑/undo使原RUNNING/READY持久STALE，同时消耗完整Token；该次STAGING变化单独标dirty。pure恢复检查状态对应facts，不自动改变桥音乐或重判none。未知／错版本报PLAN_VERSION_MISMATCH，非法输入STALE_SNAPSHOT/INVALID_CANDIDATE，非法锁PROTECTION_CONFLICT，未就绪BRIDGE_NOT_READY，实际生成失败BRIDGE_GENERATION_FAILED。

### 11.6 暂存、纯保存与恢复

P5 Attempt保留原八字段并增加唯一`bridge`：

```text
bridge={schema:"emoblocks.bridge-attempt.v1",spec_rev,contract_rev:p5,
 request:BridgeRequest,phase,plan:BridgePlan?,results:BridgeResult[],outcome:BridgeOutcome?}
```

外层attempt.id=request_id、snapshot_id=请求原编辑快照ID、input_fingerprint=原编辑指纹。records=[]；protections为基础保护＋新锁（决策前为基础保护），staged_materials仅认证的新桥最终material和children，不写当前库和编号。只有新bridge子对象使用p5，旧completion／一般Attempt形状／所属版本保持。

RUNNING无outcome，可已有Plan/锁/部分results；READY要求完整SUCCEEDED；FAILED/CANCELLED保留Plan/锁/部分音乐及有对应终态Outcome/error；STALE保留原事实并无后续资格；INTERRUPTED保留当时Plan/锁/results、outcome可null。纯存储验证请求、原版本快照、Completion引用闭包、计划／锁／实际结果一致，禁止状态字段冒充就绪。不依赖算法模块以生成旧内容；决策、compose、emotion、render、后台thread在加载/保存/validate全部禁用时仍能读写合法事实。

RUNNING保存后重开变INTERRUPTED（标staging_dirty），不恢复线程或活动Token。staging_dirty沿用P4，计算/锁/结果/取消/失败/失效均参与自动保存保护；音乐is_saved、undo、素材与编号不因stage变化。自动保存失败停止新建／打开／关闭，不丢旧文件或工作。旧Project仅打开／保存不迁移。不得把P5暂存写入bundle.results，不能用P4或旧planner生成正式整曲。

### 11.7 Facade、主流程与前端线程接口

```text
Controller.capture_bridge(candidate_id=None,completion_attempt_id=None,seed=31,parameters=None)
 ->{token,request,attempt_id}
Controller.lock_bridge(token,proposal)->BridgePlan
Controller.begin_bridge_generation(token,plan)->bool
Controller.record_bridge_result(token,result)->bool
Controller.finish_bridge(token,raw)->bool
Controller.cancel_bridge(token)->bool
Controller.fail_bridge(token,error)->bool
Controller.bridge_state()->{status,phase,attempt_id,request,plan,protections,results,
 outcome,preview,remaining_gaps,capabilities,error,message}
Provider.decide_bridge(request,should_cancel=None,on_progress=None)->BridgeProposal
Provider.generate_bridges(request,plan,should_cancel=None,on_progress=None,on_result=None)->RawBridgeOutcome
```

Controller.capture_bridge无candidate参数只允许当前无gap的完整排布，否则提示先P4补全／选候选。提供candidate时同时提供所属completion_attempt_id，错配／STALE/无效拒绝且无半注册。duplicate bridge或completion正在运行时明确拒绝；其他输入任务与bridge仍受现有busy约束。Session.accepts检查完整阶段Token；finish_job不得绕开桥专属结果认证，cancel_job转派cancel_bridge。

bridge_state为纯查询深拷贝。preview=null（尚无Plan）或`{project:base_project,overlays:JSON-object[],protections:Protection[],memory_info:MemoryInfo,notes:Note[]?}`；overlays来自后端真实Plan/结果，含id/range/status/material?；未就绪notes=null，不假造音乐。记忆来自对应base纯定位，桥标记独立，当前编辑与播放对象不变。capabilities.bridge仅v2可用；generate_final仍false。bridge_state.remaining_gaps等于当前请求的基础剩余空缺，capabilities为Outcome能力（不在READY则can_plan_connections=false）；界面不从音乐saved或原候选数推断就绪。运行中显式保存BRIDGE任务允许，关闭/新建/打开仍需明确取消后保护保存。

后台只计算纯对象；主线程锁事务成功后，再启动生成。Controller.begin_bridge_generation认证已锁Plan完整ID/version/hash及活动Token，原子将phase改为BRIDGE_GENERATION，不消耗Token；phase表示生成请求已开始，线程启动失败立即fail_bridge并保锁。前端不能自行推断阶段，lock_bridge绝不走generic DONE终态清理。工作消息封装完整Token、stage_id（DECISION或GENERATION:plan_id:version:hash）和该stage内单调event_seq；decision的迟到进度不能覆盖generation，取消A再开始B的同内容也不能通过。UI只显示后端真实阶段和已用时间，不虚构百分比/预计耗时。多个生成结果按同一队列送主线程，先独立认证，再显示CONTENT_READY；回调/线程启动异常经fail_bridge保锁并退出busy，不永久RUNNING。

三栏、单画布内显示桥决定/位置已保护/生成中/就绪/失败/失效；none与失败文字不同。候选只读预览使用后端preview的真实保护，失败锁不是普通可补空缺。可退出预览返回编辑且恢复选择与滚动；P4基础预览和P5桥预览互斥。不增加第四栏或弹窗流程，不提供最终应用/完整方案试听/成品导出。素材和旧成品的共用播放器与逐格式导出保持原契约。

### 11.8 所有权、依赖与验收

lead独占新增curve_bridges.py（纯请求/计划/结果/保护认证与预览）、curve_workflow/curve_store/curve_session公共扩展、story_engine主流程与对应新test_curve_bridges.py；必要版本兼容改curve_project，保留P4来源闭包/纯恢复/P3兼容。算法只改curve_bridge_music.py、curve_melody的统一桥乐句能力、对应test_curve_bridge_music.py及仓库外样例；不改schema/UI/story_engine。前端只改shared新增curve_bridge_ui.py、curve_ui/curve_canvas必要接线、独立test_curve_p5_ui.py，保留删除键修复；必要配对适配器先报告，不改音乐/schema/播放器。不能交叉写同一公共文件。P5冻结契约先同步；lead接口实现提交并通知后worker更新，不各自猜字段。

必测十五项：无效／未完成／STALE／篡改基础候选；current无gap；单合法候选和局部remaining_gaps；2/3/4及长区域selected与自然none；悬挂生成前所有锁已登记且原子失败；一就绪一失败；手動桥加none；相邻／单侧／不同key／休止；记忆主题手工留白跨界长音；改pitch/start/duration/extra/延音/origin/lineage/hash拒绝；取消重复迟到编辑undo不复活；保存重开全算法禁用；实际音乐可复现；无P6连接／最终边界／旧planner调用；精确tick不量化、不可表达时拒绝输出。

提供固定输入基础拼接与bridge后actual notes/来源、窗位置和none理由、锁挂起/部分失败/就绪证据；实际LMMS和设备串行，声音只称P5桥对照，非最终连接作品。后端／专项／完整/check_frontends/diff全部按范围运行；两主题×1020×700及更大窗口程序化Tk，视觉截图、实体Mac鼠标键盘／触控板、人工听感、Windows实机分开记载。契约与实现各最多5轮，匹配RUN/TASK/ROUND/HEAD和完整代码指纹的独立PASS方可交付。完成P5停止，不进入P6、不推送发布或安装模型。


### 11.9 已收前端评审后的补充／音乐账本形状（FROZEN）

- 失败结果分派在独立p5 bridge子对象验证，不送P0 Record桥结果的非空素材校验；旧Record规则完全保留。Plan不承担mutable FAILED状态；attempt失败与各锁及结果READY分轴，防止一桥失败令已认证兄弟结果无效。原P4候选放置只在base_project作用域解析，不拿当前input_project替代。
- 新自动完整桥为phrase，独立children为block，phrase_id指向最终phrase.id；继承手动kind=bridge保持原形状，其children可以为空且不强行切新子块。新自动全主动留白窗口不得被选择为作曲窗口，不用empty notes掩盖生成失败。
- `curve_melody.compose_bridge_phrase(request,window,joint_boundary_conditions,should_cancel=None)`返回未处理的phrase，普通derive六方法及已有bridge受保护规则不改。request已包含seed/预算/轨迹；不在音乐模块读Session/文件/Tk。window.context精确左右上下文为`{placement_id,notes:Note[]}`或null（几何最近未被本计划覆盖的实际放置）；相邻桥端点来自Joint而非被替换的基础端点。motif_note_ids只能引用窗内或这两个实际邻接上下文的发声ID，不任意选库内无关来源。
- Bridge基础generation精确必需字段沿9.2，加method=bridge_phrase，parameters含target_ticks、实际节奏／动机方法，base_notes为实际motif父音符快照。operations含每个输出音符唯一的cell：`{operation:"bridge-motif-cell",input_note_id,parent_ref:{placement_id,component_path:ID[],material_snapshot_id,note_id},output_note_id,motif_index,cycle_index,rule,from_pitch,to_pitch,start_tick,duration_tick}`。rule为opening/sequence/answer/rhythm/arrival；onset/duration相对完整句。input_note_id是父实际绝对发声ID；parent_ref指向其真实放置／实际变体snapshot／本地note及基准组合occurrence路径，重复嵌套使用不能借同来源的其他叶。from_pitch和origin/lineage独立回指真实父音符，output_note_id与音符严格一一，变化后slice=null，后端不只验证字符串血缘存在。每桥音乐流由Request内容、窗口、冻结共同条件及seed派生，生成顺序或兄弟失败不能改变它。结构／来源篡改而只更新hash仍应拒绝。
- emotion_processing精确形状`{pass_count:1,algorithm_version,segments:[{range:Range,emotion,seed,variant:Material}]}`。range/情绪恰等Plan情绪轨迹；每个variant从同一base_material调用已有P3规则，保护区外段和共同端点，最后只采纳起点归属该段的音符。原强度点不改，不从其他segment结果继续处理，不绕过已有桥保护。静态验证核对P3参数、base_notes、实际差异、来源／发声、操作和幅度，不调用emotion算法。
- 最终material.generation.method=bridge_emotion_once，保存完整base_notes、算法/参数/seed/key、音符操作和segments输入身份；provenance保留实际父快照。Result.operations为base generation逐音符账本；情绪账本在emotion_processing，不把P3变化说成原始作曲。joint端点在所有情绪步骤保持pitch/start/duration。
- P5的can_plan_connections仅表示可供未来P6重新捕获的合法就绪输入，P5本身不调用P6。存在remaining_gaps时只允许resolved_ranges范围的未来规划，can_export_final/can_apply/can_audition始终false，不能因none提升为最终乐谱。
- 验收补充：第二个窗冲突整批锁不发布；锁后线程启动异常释放busy但保锁；保存部分成功、禁用所有音乐生成/情绪/重算/渲染后恢复；取消阶段切换与同内容新任务不相互覆盖；P4/P5互斥预览的删除键／控制点／情绪／素材批次均不可编辑；播放中锁、失败、切预览不抢播。


已收算法初审确认：现有P0 Record的FAILED父计划不能包含READY子结果，P3 emotion对已有kind=bridge严格保护；P5采用独立阶段对象分派及未处理phrase→一次情绪→最终phrase/子块，保留这些历史门禁。inherited_bridge_ids覆盖全部原活动bridge锁，手动锁原plan_id/version不重绑；新attempt只复制当前基础自身保护，不复制其他旧P5attempt的失败锁到新活动作用域。全部自动窗与共同端点统一发布；reverse-order实际音乐须相同。CONTRACT_REVIEW ROUND2已独立PASS。


### 11.10 双角色ROUND2整合与最终计算约定（FROZEN）

- `max_notes`为每个新自动桥base_material的实际作曲音符上限，每产生一音符之前检查并协作取消。最终情绪保持音符数量，children/segment快照不重复计数，继承桥不计；超限失败，不截短，不按兄弟成功/失败重分配。生成顺序反转不改变实际音乐。
- 指纹固定使用第8.3 canonical/digest。Request域`emoblocks.bridge-request.v1`取完整Request；Plan域`emoblocks.bridge-plan.v1`取删除plan_fingerprint的完整Plan；Result域`emoblocks.bridge-content.v1`取`{range,blank_mask,notes}`；Outcome域`emoblocks.bridge-splice.v1`取`{total_ticks,notes}`。notes为实际绝对Note全字段（包括velocity），排序(start_tick,pitch,duration_tick,id)；mask排序(start_tick,end_tick)。失败/取消未完成音乐指纹null。保护结构指纹沿旧域并排除velocity，初始range_lock_fingerprint沿model.protection_summary；就绪摘要另列，不能混用。
- BridgeOverlay精确形状`{id,range:Range,protection_id,status:RANGE_LOCKED|CONTENT_READY,result_status:null|READY|FAILED|CANCELLED,material:Material|null,error:Error|null}`。保护轴取实际对应Protection，结果轴取已认证Result；没有结果时后三字段null。整体失败不把保护退回未锁状态，范围不是普通空缺。
- 所有Result的plan_id/version/fingerprint（包括inherited）绑定本次P5包装Plan；继承Protection的原plan_id/version与内容不改。继承认证不得要求旧锁计划等于新包装计划。手动桥直接核对真实放置及原保护；历史自动桥只在原计划与实际結果已READY且可解析时继承为READY，否则保锁并在本次结果返回BRIDGE_NOT_READY。
- 音乐随机流排除request_id/snapshot_id/session_id/plan_id/version及bridge随机ID；以base_fingerprint、seed、窗口范围和共同边界的音乐字段（tick、pitch/start/duration、relation，排除ID）派生。身份可以每次新建，固定音乐输入/参数/seed的实际音高时间必须一致；情绪segment seed同样采用该音乐种子规则，不依赖生成顺序、墙钟或失败项。
- lead可扩展curve_candidates中既有静态情绪验证的复用入口（保留原P4调用及平静语义），供P5纯验证完整P3快照；不得调用emotion_variant或改变P4来源/完成门禁。普通六方法、已有kind=bridge完整保护及旧Attempt验证保持原样。
- 前端必要时可修改curve_completion_ui的预览互斥接线；基础/P5控件使用现有三栏内分阶段折叠显示，避免同时堆叠压缩唯一画布。1020×700仍保持画布/底部播放可达，主题及展开不写音乐工程。frontend需检查配对适配器并保留最新Mac删除键行为。

以上为两个只读评审ROUND2的具体修订，未增加P6能力或音乐格式。独立verifier ROUND2已PASS；仅本节P5范围授权实现。


### 11.11 独立契约ROUND1修订：公开锁映射及计划前终态（FROZEN）

**公开完整桥身份域。** 自动bridge_id就是Window.id；inherited_bridge_ids是base_project.protections中kind=bridge的owner_id，不是保护ID、素材ID或旧Plan ID。同一活动bridge owner须唯一；重复归属拒绝，不静默选择一个。BridgePlan.protection_refs精确且唯一覆盖windows[].id＋inherited_bridge_ids，shape为`{bridge_id,protection_id}`。新锁ID由lead登记事务分配并立即放入Plan映射；继承锁ID必须逐项等于原基础锁id。所有保护ID互异，自动新锁不得占用输入已有保护ID。生成器用此公开映射填Result.protection_id，不读Controller私有状态，不自行分配或猜测锁ID。

纯Plan验证可仅凭Request＋Plan恢复初始保护集合：原base_project.protections完整拷贝，按Window与protection_refs构建新RANGE_LOCKED（第11.3固定字段）；再算range_lock_fingerprint。Plan/全部锁发布仍同一事务，Result与映射及真实锁完全一致。无桥Plan映射仍完整覆盖继承桥。补测公开捕获→锁定→仅用Request/Plan生成→认证往返、映射缺项/重复/额外/错锁ID、继承owner_id与旧plan_id域不混。

**计划创建前失败／取消。** capture已成功但decision线程启动失败、decide抛错或锁定前取消：attempt.state=FAILED或CANCELLED，bridge.phase=BRIDGE_DECISION，bridge.plan=null，bridge.results=[]，records=[]，staged_materials=[]，protections恰等base_project原保护。必须有对应BridgeOutcome：status等于终态，request_fingerprint及base_fingerprint照原事实；plan_id/plan_version等Request预留身份，plan_fingerprint=null（唯一允许null的计划指纹情形）；results=[]、notes=null、content_fingerprint=null，protection_summary=原基础保护摘要，remaining_gaps原样、所有下游能力false，error为实际结构化错误并等attempt.error。预留身份不是Plan，不创建none或伪锁，不公布位置。

已锁后的失败／取消Outcome用实际Plan指纹；保留每条已认证READY及CONTENT_READY，尚未产出项按固定Plan集合登记明确FAILED/CANCELLED事实行（material/base_material/null，notes/children=[]），注明未生成及终止原因，不造音符。终态bridge.results与outcome.results恰为完整必需集合；未验证的错误/额外回复不落库。全部已认证内容恰进入staged_materials，原锁不退级；整体终态仍无P6资格，即使刚好所有内容已READY。运行／中断可保留真实部分集合，未伪造已完成。

STALE保留此前Plan/锁/结果/Outcome/error不变；决策前RUNNING重开INTERRUPTED时plan/results/outcome仍null/[]/null；决策前FAILED/CANCELLED恢复上述终态，不再生成计划。补测计划前线程异常／计算异常／取消保存重开、禁用全部生成函数、重复迟到回调不创建锁或none、旧失败记录不复活；锁后部分成功＋取消/异常仍保留真实音乐。


## 12. P6 连接块补充契约（FROZEN）

SPEC_REV=curve-workflow-v2-r3；CONTRACT_REV=curve-workflow-v2-r3-p6。历史p0/p23/p4/p5冻结正文保持原样。本节仅P6，不授予P7最终处理、应用、完整试听或正式导出能力。

### 12.1 输入和身份门禁

音乐Project头仍为所属版本（当前p4），p6仅阶段对象/请求处理版本；打开、查询、保存不迁移。新的ConnectionRequest由当前Session完整Token捕获，引用存储中真实READY的P5 attempt；先纯验证P5 Request/Plan/Outcome、全部保护及P4目标实际完成。P5 parent必须仍READY、输入Project恰等当前捕获Project；输入变化后撤销回同内容也不能复活STALE。保存恢复后的READY事实可由新会话重新捕获，但旧Token无权回调。

`bridge_ref={attempt_id,request,plan,protections,results,outcome}`复制真实P5事实。期望bridge集合精确等Plan.windows[].id＋inherited_bridge_ids，缺失/重复/额外/失败/RANGE_LOCKED/旧版本均拒绝。none必须有有效Plan及理由，仍包含手动/继承桥全部结果。不能根据计数或布尔标识放行。

ActualLayout为纯JSON `{total_ticks,bpm,notes,base_project,bridge_overlays,protections,blank_regions,remaining_gaps}`：notes恰为P5已独立认证Outcome.notes（bridge实际拼接）；base_project保持原基础选择，bridge_overlays保存实际结果及精确范围。分析左右音符必须读notes，禁止用被桥替换的旧基础末音。剩余gap保留，所有连接窗须落在已解决范围；素材内部休止与主动留白不是gap。记忆/主题/手工保护保留原事实，含受保护的休止和跨四拍完整音符支撑。

`ConnectionRequest={schema:"emoblocks.connection-request.v1",spec_rev,contract_rev:p6,
 request_id,snapshot_id,session_id,edit_revision,input_contract_rev,input_fingerprint,input_project,
 bridge_ref,actual_layout,layout_fingerprint,protection_summary,plan_id,plan_version,
 seed,algorithm_version,parameters}`。所有字段必需，新增Plan ID及严格递增版本；输入保护摘要从bridge_ref实际保护重算。Request与原版本Snapshot匹配。候选/请求/桥依赖不变才能规划或回调。

### 12.2 公开接口、提案与计划

意图沿用 `plan_connection_blocks(completed_candidate,ready_bridge_plan,protections,bridge_results)`；当前已有P5包含current_complete和CompletedCandidate两输入，因此实际纯provider统一为 `plan_connection_blocks(request,should_cancel=None,on_progress=None)->ConnectionProposal`，四项输入通过request.bridge_ref完整绑定，不虚构补全候选。

`generate_connection_blocks(request,plan,actual_layout,should_cancel=None,on_progress=None,on_result=None)->ConnectionRawOutcome`。公开输入输出不含Tk/线程/文件句柄；验证器不调用provider。lead facade先认证/发布Plan，随后执行独立生成；story_engine专用P6入口，不路由旧planner、bridge重生成或P7边界。

默认有限预算parameters `{policy:"auto",max_windows:3,max_window_tests:128,max_window_ticks:3840,min_window_ticks:240,max_notes:512}`；上限8/2048/15360/4096（min_window_ticks正整数，不大于max_window_ticks）。种子整数，algorithm_version="curve-connection-v1"。无无限重试；每窗/每音符检查取消，确定性排序以音乐评分、少改写、起点/终点/规则排序。随机流从layout_fingerprint、seed和窗口音乐字段派生，排除请求/计划/窗口随机ID、墙钟和生成顺序。

`ConnectionProposal={schema:"emoblocks.connection-proposal.v1",spec_rev,contract_rev:p6,
 request_fingerprint,decision:"selected"|"none",none_reason:null|"NOT_NEEDED"|"NO_LEGAL_WINDOW",
 windows:ConnectionWindow[],reasons:Warning[],assessments:JSON-object[],
 joint_boundary_conditions:ConnectionJoint[],search:{tested_windows:int,termination:str}}`。

`ConnectionWindow={id,start_tick,end_tick,technique,context:{left:Note|null,right:Note|null,motif_note_ids:ID[]},
 original_notes:Note[],reasons:Warning[]}`。
technique为diatonic_guide/motif_reply/density_shift/retain_develop/breath_close；不是P7的边界微调标签。original_notes精确等实际Layout中支撑与窗口相交的音符，全部音符支撑必须完整落窗内；不截断原音符。left/right为排除本批全部窗口后的几何最近实际音符（不能拿旧base端点）。motif_note_ids只能来自原窗及此实际左右上下文。窗口长度至少min_window_ticks，有真实时长发展，不用单音音高修正冒充本阶段。

`ConnectionJoint={id,left_connection_id,right_connection_id,tick,relation,
 left_endpoint:{pitch,start_tick,duration_tick}|null,right_endpoint:{pitch,start_tick,duration_tick}|null}`；相接窗口必须恰有一条共同条件，tick为共享边界，端点落各自窗口，null表示对应边界休止；生成逐项兑现。非相接窗口不得伪造共同条件；无互等或取已覆盖旧端点。全部窗先统一互斥/依赖校验。

`ConnectionBlockPlan={schema:"emoblocks.connection-plan.v1",spec_rev,contract_rev:p6,
 id,version,request_id,snapshot_id,request_fingerprint,bridge_plan_id,bridge_plan_version,
 bridge_plan_fingerprint,layout_fingerprint,protection_summary_fingerprint,
 decision,none_reason,windows,reasons,assessments,joint_boundary_conditions,search,plan_fingerprint}`。
计划发布为单后端事务；非法第二窗整批拒绝，不留下半计划。连接分配不能修改桥锁。none要明确原因和真实分析；异常是FAILED，不可变none。

必要性联合实际动机、调性、音程/音域、节奏密度、句尾休止、情绪、强度趋势和桥已完成衔接；收益接近优先保留。无窗口时保留音乐交P7考虑轻量处理，不释放锁；不识别主副歌、不默认鼓填充。窗口可以替换较长片段，理由须说明保留/替换取舍。

### 12.3 独立保护及音乐结果认证

保护禁写域是原锁名义范围＋全部受保护音符的完整支撑＋主动留白＋未解决gap。半开区间相接允许；完全包围、部分侵入、跨桥均拒绝。即使原音符起点在窗外，延音相交也不可切断。range合法而生成音符延入桥仍拒绝。桥的pitch/start/duration及完整结构、内容休止保持；允许的力度/音色/伴奏不授权P6修改主旋律结构。本阶段默认保留保护区实际音符全部字段。

每条实际连接结果为
`ConnectionBlockResult={schema:"emoblocks.connection-result.v1",spec_rev,contract_rev:p6,
 request_id,snapshot_id,request_fingerprint,plan_id,plan_version,plan_fingerprint,
 connection_id,range,status:"READY"|"FAILED"|"CANCELLED",original_notes,notes,
 operations,content_fingerprint,error}`。
READY notes是绝对tick、合法单旋律、nonempty并在窗内；失败notes/operations为空、content_fingerprint=null，error为Warning形状。原音乐含自然休止可保留/发展，但不能侵入主动留白；无需作曲的窗口不得用empty READY伪装成功。

逐音符operations精确对应notes：`{operation:"connection-motif-cell",input_note_id,output_note_id,
 rule,from_pitch,to_pitch,start_tick,duration_tick}`；input_note_id是真实窗/左右动机父音符ID；rule为窗口technique或preserve。变换音符origin三字段、完整lineage回指该实际父音符，改变pitch/time必须清除slice，不借无关来源/清空来源。preserve必须逐字段等真实父音符，可保留原ID及slice；派生新ID不得冒用原发声身份。来源验证不只检查合法库ID，逐父音符实物认证，不通过重新生成来验证。

全局拼接仅移除各窗original_notes并加实际连接notes，其他音符逐字段不变。独立校验原布局/实际桥/所有保护休止与完整支撑、留白、互斥、固定总长及共同边界，不信impact声明。新增/删除/移位/延长/缩短全部从实际前后音乐判定；Result不能自报较小范围掩盖越权。

`ConnectionRawOutcome={schema:"emoblocks.connection-raw-outcome.v1",spec_rev,contract_rev:p6,
 request_fingerprint,plan_id,plan_version,status:"SUCCEEDED"|"FAILED"|"CANCELLED",results,error}`。
results必须精确覆盖Plan.windows IDs；缺失/重复/额外不就绪。流式认证允许真实部分成功暂存，终态失败保留成功事实，未生成项明确FAILED/CANCELLED。

`ConnectionOutcome={schema:"emoblocks.connection-outcome.v1",spec_rev,contract_rev:p6,
 request_fingerprint,plan_id,plan_version,plan_fingerprint,status,results,notes,content_fingerprint,
 layout_fingerprint,protection_summary,remaining_gaps,error,capabilities}`；SUCCEEDED才能有实际拼接notes/内容摘要；未发布Plan失败允许plan_fingerprint=null，其余失败不可伪造none。
capabilities精确 `{score_scope:"CONNECTION_STAGE",can_plan_boundaries:bool,can_apply:false,can_audition:false,can_export_final:false}`；只有当前READY且全部实际结果就绪允许未来P7捕获，remaining_gaps仍不能整曲完成。

### 12.4 指纹、状态、保存与失效

canonical/digest沿8.3（UTF8 canonical JSON排序key、有限数字）。Request域emoblocks.connection-request.v1取完整对象；Layout域emoblocks.connection-layout.v1取完整ActualLayout；Plan域emoblocks.connection-plan.v1取删自身plan_fingerprint完整对象；Result域emoblocks.connection-content.v1取 `{range,notes}`；Outcome域emoblocks.connection-splice.v1取 `{total_ticks,notes}`。notes固定(start_tick,pitch,duration_tick,id)排序；保护摘要沿model.protection_summary，不混同原桥初始锁摘要/就绪摘要/旋律结构摘要。

Attempt外形沿P4/P5八字段＋`connection`；私有stage `{schema:"emoblocks.connection-attempt.v1",spec_rev,contract_rev:p6,request,phase,plan,results,outcome}`。
phase为CONNECTION_PLANNING→CONNECTION_PLANNED→CONNECTION_GENERATION→CONNECTIONS_READY；attempt.state RUNNING/READY/FAILED/CANCELLED/INTERRUPTED/STALE。records和staged_materials均[]，protections恰等P5实际保护事实（连接结果独立notes，不占当前库或显示编号）。

capture/发布/认证/结束全为原子Bundle验证事务。输入Snapshot原版本；bridge_ref必须解析真实父attempt，活动子不能消费失效父。音乐编辑/undo/redo标旧P4/P5/P6持久STALE，保留全部记录/锁/结果；新重试有新Request/Plan与递增version。取消消费Token，失败和重复/迟到结果无权写入终态；有效同一流式结果重复是幂等no-op，冲突重复失败并保留先前实际结果。线程启动和回调异常释放busy，不清桥锁。

计划前失败/取消：plan=null、results=[]、outcome为对应失败/取消，plan_fingerprint=null、notes/content=null，真实错误；计划后失败保留Plan及全部bridge保护，部分连接READY保留，不授予P7。INTERRUPTED保留Plan/实际部分，不凭空补终态音符；STALE保留既有事实不重活。保存恢复只验证持久化事实和指纹，不调用任何规划/生成/情绪/记忆重算/渲染/线程；RUNNING恢复INTERRUPTED且staging_dirty=true。音乐saved、库、编号、undo和播放器完全隔离；staging_dirty沿自动保存保护，失败停止切换/关闭。

### 12.5 前端接口与可用能力

Controller新增 `capture_connection(bridge_attempt_id=None,seed=41,parameters=None)` 返回 `{status:"STARTED",token,request}`；`plan_connection(token,proposal)` 返回实际认证Plan；`begin_connection_generation(token,plan)`；`record_connection_result(token,result)`；`finish_connection(token,raw)`；`fail_connection(token,error)`；`cancel_connection(token)`；`connection_state()`。
state沿bridge模式，额外 `phase/status/message/request/plan/protections/results/outcome/capabilities/preview`；preview为 `{project,overlays,protections,memory_info,notes,connection_overlays}`，前五项沿P5实际只读桥预览，notes为P5实际音乐或READY连接拼接；connection_overlays每项 `{id,range,status,result_status,notes,reasons,error}`。桥/记忆标识始终可辨，连接不能视觉遮盖。没有Plan时preview=null；失败Plan保留真实范围与失败，不能显示可普通补全gap。

三栏候选区域分阶段折叠，唯一画布只读显示影响与理由；P4/P5/P6预览互斥，退出恢复当前编辑选择/滚动。规划→计划→生成→就绪/none原因/失败/失效，进度真实阶段及elapsed，不假百分比。UI不推断锁、不抢播放器或选素材，不增BPM/画笔/弹窗工作流，不开放最终应用/完整试听/整曲导出。Tk和Facade事务都在主线程，worker只纯计算；队列绑定完整Token＋stage＋计划指纹，不让过期回应切状态。

### 12.6 文件归属和验收

lead独占curve_connections.py（新增纯认证）、curve_workflow/curve_store/curve_session、story_engine及test_curve_connections.py。算法只改新增curve_connection_music.py和test_curve_connection_music.py，仓库外音乐样例；不改公共schema/UI/主流程。前端只改新增curve_connection_ui.py、curve_ui/curve_canvas以及P4/P5互斥接线必要改动、test_curve_p6_ui.py；检查双端适配但不改播放器契约。已有保护兼容与删除键行为全部保留。公共接口先提交同步，worker不猜字段。

必须覆盖：真实P5父和目标/候选校验、无自动但手动READY、旧末音与桥实际不同、三类侵入、合法窗超边音符、两侧无空间、全局冲突和相邻端点、长音记忆/组合/短尾/留白/内部休止、伪自报影响、迟到取消重试重复、纯恢复、快照隔离、独立保护校验与音乐确定性。固定样例保存基础/桥/连接三个actual notes、来源/摘要、理由/范围；真实LMMS串行连续渲染且标尚未最终块间处理，设备串行。双主题三尺寸实际映射Tk坐标与截图/人工/Windows各自报告，不用模拟替代实测。契约/实施独立各最多5轮，匹配实际HEAD和前后同指纹PASS。P6完成停止，不进入P7。


### 12.7 双角色只读评审整合：精确形状与计算（FROZEN）

本节细化12.1–12.5的字段，不修改任何历史冻结版本。两个角色ROUND1只读FAIL提出的接口缺口统一如下，worker不得另猜字段：

- ActualLayout.bridge_overlays为11.10精确BridgeOverlay[]（由bridge_ref自身事实纯构造，不借当前BridgeUI）。原BridgeResult[]在bridge_ref.results；base_project恰等bridge_ref.request.base_project，notes恰等bridge_ref.outcome.notes，protections恰等bridge_ref.protections，blank_regions/remaining_gaps等该P5输入事实。P6当前编辑等P5 request.input_project，不误要求等私有基础候选。
- Request.protection_summary精确`{fingerprint:str,ranges:Range[]}`。fingerprint=model.protection_summary(P5实际protections)；ranges为所有锁名义范围与其notes完整支撑的排序合并并集（所有保护类型，不只是memory）。blank/gap独立在actual_layout中，不能借ranges漏掉它们。Outcome.protection_summary沿P5为同一fingerprint字符串。
- Window增加`key_context:{tonic:int0..11,mode:"major"|"minor",confidence:0..1,method:str}`及`parameters:{target_ticks:positive-int,unit_ticks:1|10}`；target_ticks=end-start，unit_ticks为1或10，10只能在原窗/实际上下文起点与时值全为10的倍数时用，否则必须1。数据层不量化；输出不可表达仍明确拒绝。调内pitch_classes为tonic加major[0,2,4,5,7,9,11]或minor[0,2,3,5,7,8,10]取模12。
- Result增加`generation:null|Generation`，READY必须Generation；失败为null且仍保存准确Plan.original_notes。Generation精确字段沿9.2：`{method:"connection_phrase",parameters,seed,rng_version:"python.random-v3",algorithm_version,input_fingerprint,input_material_ids,base_notes,key_context,operations}`。parameters/key_context恰等Window；base_notes为motif_note_ids按顺序映射的实际父Notes；operations与Result.operations相同。input_material_ids排序去重来自每个实际父快照。
- operations增加`parent_ref:{kind:"bridge"|"placement",owner_id,component_path:ID[],material_snapshot_id,note_id}`。先从bridge_ref.results[].notes精确解析父发声（唯一bridge），对应Result.material的本地note_id、snapshot和空组件路径；否则从base_project placement实际emotion_variant或base_snapshot解析，并沿P5 parent_ref几何/occurrence路径找到组件。源三字段精确等实际父origin；派生lineage=list(dict.fromkeys(parent.lineage+[parent.id]))，slice=null；派生ID不得等输入任何实际发声ID。preserve必须是original_notes成员且Notes全字段相同，操作parent_ref仍按真实归属认证。整个Layout/结果发声ID唯一，新增结果不能借受保护发声ID。

音乐随机流与认证摘要分开：

```text
music_projection={total_ticks,bpm,
 notes:[{pitch,start_tick,duration_tick,velocity}]按音乐字段排序,
 intensity_points:[{tick,level}],
 emotion_segments:[{start_tick,end_tick,emotion}]按时间排序,
 protection_ranges:Range[]排序合并,blank_regions:Range[]排序合并,
 remaining_gaps:Range[]排序合并}
```

emotion_segments来自base_project所有放置的时间/情绪，intensity_points沿真实Project形状直接复制；不含任何ID/名称/计划/种子/来源身份。music_fingerprint=digest("emoblocks.connection-music.v1",music_projection)。每窗seed=int(digest("emoblocks.connection-music-seed.v1", `{music_fingerprint,seed:Request.seed,range,technique,parameters,key_context,joints}`)[:8],16)；joints取相关共同条件删除id与左右connection_id并按canonical排序。完整layout_fingerprint仍只用于认证，绝不播种。

Generation.input_fingerprint=digest("emoblocks.connection-compose-input.v1", `{layout_fingerprint,range,technique,parameters,key_context,motif:base_notes,joints,seed,algorithm_version}`)。这些纯helper由lead提供，算法复用；不通过回放随机作曲认证保存数据。Request.seed是0..2**32-1整数，bool拒绝；policy仅auto或none（none仅显式保留，reason NOT_NEEDED，不能代替错误）。max_notes为每窗实际输出总音符上限，含preserve，不含日志；超限失败，不截短或按生成顺序挪预算。其它预算拒绝bool，max_window_tests≤2048、max_windows≤8、max_window_ticks≤15360、max_notes≤4096。

### 12.8 实际发展、端点与保护比较（FROZEN）

所有READY窗口至少两个发声，actual `(pitch,start_tick,duration_tick)`音乐序列必须不同于original_notes；ID/名称/血缘/seed/velocity/标签差异都不算发展。纯单音改高、全preserve或只换ID一律不能READY。不重新执行全轮情绪算法。以下静态规则是必要条件，不宣称听感质量：

- diatonic_guide：全部输出音高在key_context音阶，至少两个攻击；有right时最后音高到right的距离不大于第一音高到right的距离。
- motif_reply：至少三个攻击、至少两个不同音高，派生音符至少引用两个不同的实际motif父发声；调内输出。
- density_shift：至少两个攻击，攻击数与original_notes不同，调内输出。
- retain_develop：原窗前半结束的音符逐字段保留，至少一条后半起音的派生音符，后半pitch/time序列确有变化。
- breath_close：至少两个攻击，末音结束≤end-max(1,min(120,(end-start)//8))，有真实句尾休止。

Plan中的Joint非null端点恰等READY结果第一/最后音符pitch/start/duration；left null表示末音end<left_window.end，right null表示首音start>right_window.start。每个相接边界恰一Joint，冻结后生成反序也必须兑现；不引用被本批其他窗替换的旧端点。

保护记录原样保留，结构认证沿已有排除velocity规则，不能恢复旧力度。P6前后保护/区外的全字段比较基准始终是ActualLayout.notes中的P5实际发声（例如原锁80、合法实际100，none保留100）。名义范围保护休止，跨界note完整支撑同样禁写。失败锁/手动保护/历史审计不删除或放宽。

规划预算耗尽且未证明不存在合法有收益窗口时返回结构化SEARCH_BUDGET_EXHAUSTED失败，不写none_reason=NO_LEGAL_WINDOW；已有合法selected方案可返回预算终止提示。自然无需连接和确实无合法窗口分别NOT_NEEDED与NO_LEGAL_WINDOW，均有对应具体assessment/reason。同一句的内部四拍分界不自动触发连接，须有真实音乐关系需要。

### 12.9 Facade、队列和预览返回（FROZEN）

Controller.state().capabilities.connection=not readonly，仅表示可请求该阶段，实际父门禁在capture。capture_connection(None)只解析Controller当前_bridge_id，失效/失败就拒绝，不静默回退旧父；显式bridge_attempt_id可以选择仍READY父。返回`{status:"STARTED",token,request,attempt_id}`且attempt_id=request_id。所有预留版本（包含计划前失败/取消）都参加严格max+1。

plan_connection返回认证Plan（无效抛ProjectError，调用方fail关闭任务）；begin/record/finish/fail/cancel返回bool。非法流式Result返回false且持久FAILED/error；完全相同重复Result返回false保持RUNNING，不误判为失败；冲突重复终止并保留原结果。首个生成失败停止后续作曲，终态补齐Plan全部ID失败行，保留此前实际READY；raw必须逐字段一致于已认证结果。生成回调异常传播给Facade，不吞异常或伪none。

connection_state精确`{status,phase,attempt_id,request,plan,protections,results,outcome,preview,remaining_gaps,capabilities,error,message}`。IDLE为phase/attempt_id/request/plan/outcome/preview/error=null，protections/results/remaining_gaps=[]，message非空，capabilities默认false。其它status用attempt.state；capabilities.can_plan_boundaries仅当前READY为true，STALE/FAILED即使保留旧SUCCEEDED事实也false。

preview的桥部分严格由本次request.bridge_ref生成；没有Plan时preview=null。整体READY时notes为认证连接拼接，其余为P5实际notes，部分成功通过connection_overlays展示。每项覆盖层精确`{id,range,status:"ALLOCATED"|"CONTENT_READY",result_status:null|"READY"|"FAILED"|"CANCELLED",notes:Note[],reasons:Warning[],error:Warning|null}`；id/range/reasons恰等Window；READY才CONTENT_READY和实际notes，其他为空。不声称连接窗口是bridge RANGE_LOCKED。

队列绑定完整p6 Token、PLANNING或`GENERATION:plan_id:version:fingerprint`及阶段内单调整数seq。progress是非空可读字符串，纯provider调用on_progress(message)；没有百分比/假阶段。Plan发布不消费Token；begin成功后才启动生成线程，线程启动异常走专属fail。所有Tk/Facade在主线程，worker只计算纯输入；终态/取消/阶段错配/乱序迟到都不可更新状态。generic finish_job拒绝CONNECTION，cancel_job转专属取消；保存白名单、Store中断暂存标记及STALE传播正式扩展CONNECTION。保存运行中事实可用，恢复不重启线程。

两个角色只读评审问题已整合，独立P6-CONTRACT ROUND1 PASS，FROZEN；未开始功能实现。


## 13. P7 最终处理、完整推荐与一次应用补充（FROZEN）

SPEC_REV=curve-workflow-v2-r3
CONTRACT_REV=curve-workflow-v2-r3-p7
STATUS=FROZEN

历史第8–12节冻结正文保留。本补充必须经算法/前端只读评审、lead整合及verifier独立PASS后才能FROZEN和实施。本轮完成P7后停止，不进入P8。所有公开对象是JSON纯数据、音乐时间为PPQ480精确整数tick、半开区间，不含Tk/线程/文件句柄。运行记录/素材样例/渲染输出在仓库外。

### 13.1 产品范围与顺序

每套方案必须真实基础补全→bridge位置→同事务全锁→全部bridge实际READY→保护外连接规划/生成→最终局部边界→整曲独立校验→编配→编配后复核→真实LMMS音频→完整方案。不得共同分配bridge与连接窗口、先连接后桥、调用旧轮换planner或重跑全轮情绪。当前工程无gap时直接已验证真实排布，不伪造P4；选单gap只解决该目标，剩余gap不变，允许明确未完成局部试听/应用，禁止正式整曲导出。P4/P5/P6中间结果不变成最终推荐。

五种最终局部功能是自然延续、动机回应、渐进铺垫、留白进入、回落收束，另有明确none。根据真实句尾/休止/弱起/节奏/情绪/强度选择，不每四拍添加过渡、不默认鼓填充/目标音预示。无空间允许保留主旋律或仅表演/伴奏交接；最终边界不缩桥/重做连接。先收集全部操作，再统一冲突和实际端点检查，一次应用，禁止后写吞掉前写。

### 13.2 初始对象草案与职责

RecommendationRequest绑定完整不可变输入Project、input_contract_rev、原编辑Token(project/session/request/snapshot/revision/content)、selected_gap_id与重新认证的目标、全保护/留白、seed、算法版本、有限搜索budget和mode(melody_only/arranged)。RecommendationOutcome包含有限有效FinalCandidate列表、终止/不足原因与错误；FinalCandidate通过最终处理后按实际pitch/onset/duration/排布/乐句重新去重，力度、名字、ID、seed、情绪标签不算不同。少于两套诚实说明，一套合法可试听/应用；无合法结果保持工程不变。自动补全消费同一Outcome中最高排名合法候选，一次事务应用，不存在绕过桥/保护的另一条路径。

阶段事实保存在独立attempt及对应快照中：基础、桥、连接、边界、谱和音频按明确ID/版本/指纹引用，公共结果不相互覆盖、不把循环嵌套工程作为依赖。原输入、P4候选及当前工程/库/显示编号/undo/player在计算和预览阶段不变。music dirty和staging_dirty分开；取消/失败/迟到/重复/重试各有终态审计，重试新request；undo同内容不能复活原session/revision请求。

### 13.3 BoundaryRequest/Plan/FinalScore 初始接口

lead将当前认证P6 request/plan/outcome/全results及原P5集合组装成actual_layout，验证READY精确集合、none有效性及全部来源/指纹/保护。无P6父或缺失/失败/旧版本禁止进入。

算法接口为`plan_boundaries(boundary_request,should_cancel=None,on_progress=None)->BoundaryProposal`，输入包括真实连接后Layout、bridge_plan、protections、connection_results及固定种子参数；lead认证并公布`BoundaryPlan`，再`apply_boundaries(request,plan)->FinalScoreProposal`。`validate_final_score(request,plan,score)->ValidationReport`是lead独立纯校验器，不能用重运行算法验证旧结果。

精确对象见13.10–13.13：请求Token/候选/计划/算法版本，边界ID和真实放置/演奏所有者、完整原始音符快照、局部许可范围、操作类型及输入/输出音符、奏法/音色/力度/伴奏提示、共同端点与冲突依赖、保护摘要、音乐和源血缘指纹、剩余gap及完成能力。声明READY或自报impact不构成保护通过。

桥内pitch/绝对onset/duration/内部休止不变，不得新增主旋律；保护完整记忆跨界音符、组合/短尾、主题/手工/留白。合法边界相接可用，音符实际支撑不得越界。受保护休止不得被填满，素材内部休止不是gap。变换音符保留具体motif父和完整来源，变音高或时值不得复用旧发声slice。只合并同一次放置/演奏、同一原音符、同音高且连续切片；重复用同素材重新起音，不能只凭source_note_id合并。句内四拍线不是独立边界。

### 13.4 编配及输出

新FinalScore直接接现有情绪音色/力度、和声/低音/节奏/条件鼓组能力，不接旧planner，不再次旋律情绪改写。主旋律与伴奏角色有独立来源；禁止将违规新增主旋律改标签伴奏。仅主旋律关闭全部伴奏，统一主旋律音色/力度，保留同一已经规划旋律。

编配前后独立对比固定总长、实际目标完整覆盖/remaining_gaps、全部保护/桥结构/休止/留白、每个主旋律音符时间和来源、合法slice合并、候选及各Plan依赖。伴奏有明确受限生成规则和可独立复核的实音符，不接受任意贴标签层。

MIDI/MMP/WAV和音频对比资产绑定同一已校验score_fingerprint、mode、candidate/版本，记录body_ticks/body_seconds与含尾音audio_seconds。沿用真实LMMS连续渲染和尾音，不用中性素材试听冒充方案。初始约束沿用现有MMP10tick表达能力；任何不可无损表达的onset/duration/全长返回OUTPUT_TIME_UNREPRESENTABLE，不量化/移动/截断保护。精确MIDI能力若扩展须先列冻结接口/文件范围。

### 13.5 试听与资产状态

每候选保存一致快照/模式的原基础拼接comparison_score和处理后FinalScore；二者乐谱先独立认证，真实各自渲染，文件存在/音频可读/内容hash与元信息绑定后才AUDITION_READY。不能拿旧cache或其它候选音频替代。不自动抢播，点击卡只选择，明确Play才使用第三栏底部播放器；后台返回不改当前选材/播放/导出对象。

保存恢复纯事实，不调用作曲、情绪、渲染/线程。RUNNING恢复INTERRUPTED；文件删除/修改/版本失配时对应试听不可用，不假播放就绪。渲染失败/取消结束busy保原工程/历史，不静默换音频。实际文件可用性每次播放/确认/导出重新检查；是否仍可应用独立于正式整曲导出资格，不允许绕过已试听绑定。

### 13.6 一次应用与依赖草案

确认只消费已保存且完整认证的同一FinalCandidate乐谱/阶段/模式，禁止重新随机或重新生成。重新核对工程/session/revision/input snapshot/精确目标gap/所有候选和计划版本及资产；过期拒绝。重复确认transaction_id幂等，无二次素材/编号/undo。

一次事务包含目标基础填充、确实保留的新素材/完整源/整句子块、桥及保护、连接/边界覆盖层、记忆与接受记录；撤销恢复全部先前音乐，重做保存结果不作曲。临时未采用/失败/取消素材不登记。原source文件缺失可用已有快照读取。历史task审计独立于音乐undo。

初始建议：新增p7显式音乐版本，仅在新建或确认事务按明确契约产生；旧p0/p23/p4 Project打开/保存头不迁移。Project保留原基础放置，accepted_overlay保存小型有界引用与实际谱/保护/依赖绑定；所有原输入及完整阶段事实在Bundle快照/attempt registry，不能在每层Project内重复嵌套其历史完整Project。应用后的绑定使用排除自指字段的规范音乐投影，与原input fingerprint区分；事务自身revision增加不使结果失效。后续用户音乐编辑标记受影响结果失效、不静默保留错误连接、不擅自重生成；桥固定保护不会因结果失效被释放。该设计的精确形状及旧stage服务如何读取实际已接受覆盖层需只读评审明确，不能worker自行猜测。

### 13.7 前端契约草案

原三栏/唯一二维画布/底部共用播放器内提供推荐卡、简短差异理由、原始/处理后对比、明确Play/确认/取消/自动补全。区分当前编辑、选中候选、播放对象、已接受/生成版本和导出目标。局部未完成明确余gap并阻止正式整曲导出；无桥/无窗/none合法；不足两套/实际失败/失效直接显示，不新增窗/第四栏/试听窗口/复杂向导。Soft UI/静态Vibrancy、记忆叠放、无右栏BPM/涂色画笔不变；最小1020×700窄窗优先收来源。所有Tk与Controller应用在mainthread，后台纯快照计算及真实渲染，queue完整token/阶段/版本门禁，取消原事件能力不新增另一个框架。

### 13.8 文件所有权草案

lead：curve_final.py、curve_recommendations.py、curve_final_render.py、curve_application.py（新增纯公共服务），curve_project/curve_session/curve_store/curve_workflow、story_engine接线、精确输出兼容与自己的对应tests。算法：独立curve_boundary_music.py及test_curve_boundary_music.py，不改公共schema/UI/story_engine；前端：shared curve_recommendation_ui.py、curve_ui/curve_canvas及必要既有stage/player UI、UI tests，配对适配器仅明确契约需要；verifier只读冻结集成，不改需求/源码/测试。

### 13.9 必验路径与停止

全gap→真实基础/P5/P6/P7/编配/实际音频→明确试听→确认→保存重开；单gap余gap不变/局部确认/不能正式整曲导出；none/无窗/无专门边界；桥pitch/onset/duration/桥内加音/记忆跨界/留白/漏影响独立拒绝；slice同演奏合并与重复起音；最终收敛去重/不足诚实；试听和取消不改工程，确认同谱、幂等、一次undo/redo不作曲；计算期间修改/迟到/重复/session失效；渲染失败/取消/缺文件/运行恢复/已应用后编辑失效；两mode旋律一致/伴奏表达切换/三格式绑定。

固定素材记录基础→桥→连接→最终的实际notes、依赖/源/保护、至少两套实际不同推荐乐谱和真实音频（不足原因另测）。实际窗口坐标、LMMS/设备串行，自动、Tk、渲染、设备、人工视觉听感、Mac/Windows分类，不以模拟替代P7真实渲染。必跑backend-only/check_frontends/full/diff。契约与实现分别最多5轮，匹配RUN/TASK/ROUND/HEAD/前后同fingerprint明确PASS。完成P7停止，不派P8。


### 13.10 双角色评审整合：最终边界精确对象（FROZEN）

统一Ref=`{id,version,fingerprint}`。所有schema前缀emoblocks、版本v1；本节对象spec_rev=r3/contract_rev=p7。所有Note沿用P3八字段，音高12–119，不夹紧；时间精确tick。字符串ID不能为空，数字/预算禁止bool。

BoundaryRequest精确字段：`schema spec_rev contract_rev id token input_contract_rev input_fingerprint candidate_ref connection_ref actual_layout layout_fingerprint protection_summary plan_id plan_version seed algorithm_version parameters`。schema=emoblocks.boundary-request.v1，token为P1八字段p7 Token，candidate_ref为P4 candidate的Ref或无gap时null。connection_ref精确`{attempt_id,request,plan,results,outcome}`，全部P6对象独立认证；input_project、P5完整桥集合和目标从实际P6请求追溯，不能相信caller布局。新Boundary request不得以STALE父授予能力。algorithm_version=curve-boundary-v1。

ActualLayout精确`{total_ticks,bpm,base_project,notes,segments,coverage_ranges,remaining_gaps,protections,blank_regions,emission_ledger}`。notes精确等P6已认证outcome.notes；base_project为P5 request.base_project；coverage由基础放置、主动留白与真实剩余gap推导，不用新增空notes填表。Segment=`{id,performance_id,owner_ref,start_tick,end_tick,phrase_id,component_path,emotion,key_context,intensity_start,intensity_end,kind}`；kind=placement|bridge|connection|blank。桥及连接按真实覆盖范围替换显示所有者，原排布保留，内部四拍不另切边界。ledger每实际Note一条`{note_id,parent_ref,performance_id}`，parent_ref=`{stage,owner_id,note_id,component_path,material_snapshot_id,content_fingerprint}`，stage=placement|bridge|connection|final_score；从真实P6结果与P5/放置数据逐项解析，禁止用材料/source ID冒充演奏所有者。performance_id绑定真实placement与嵌套occurrence，桥/连接绑定各自执行实例。只读阶段不改变current库或编号。

Boundary参数精确`{policy,max_boundary_ticks,max_operations,max_pitch_shift,max_time_shift,max_modified_notes,max_added_notes}`，默认auto/240/64/2/120/2/1；policy=auto|none，限制boundary_ticks<=240、operations<=256、pitch<=2、time<=120、modified<=2、added<=1，均正整数（added允许0）。seed 0..2**32-1。边界从实际Segment的所有者交接、留白进入与末尾推导，不把乐句内部四拍当边界；未解决gap不充作合法弱起/填音窗口。

BoundaryProposal精确：`schema spec_rev contract_rev request_fingerprint decision none_reason boundaries operations joints join_groups performance_hints assessments reasons search`。Boundary=`{id,tick,left_performance_id,right_performance_id,method,editable_ranges,operation_ids,reasons}`；method=natural_continuation|motif_reply|gradual_build|blank_entry|resolve_close|none。editable_ranges由每侧240tick与允许音乐域相交，减去全保护完整支撑/休止、留白、未解gap及已就绪连接的结构范围；P7本实现不再结构改写P6窗口，仅允许其表演交接。none_reason=NOT_NEEDED|NO_LEGAL_OPERATION|POLICY_NONE，异常不是none。

Operation=`{id,boundary_ids,kind,input_refs,consumed_note_ids,outputs,permitted_ranges}`，kind=replace|remove|add；输出为`{note,parent_note_ids,performance_id}`。所有原音符和parent_ref取自同一原Layout，不读取本批新输出。replace消耗一个原音符并产一个，remove消耗一个短弱音（原长<=120）无产出，add引用一个真实局部父动机但不消耗它、输出长<=120且范围合法。每边界最多修改2/新增1；改变pitch/start/duration的新ID由request/operation/真实note结构派生，保留精确origin和完整父lineage、slice=null；未改结构保原ID/来源/slice，力度交接另走hint。每原音符只能一个结构写入者，各实际新增/删除/移位/延长/缩短与许可域、完整保护和原始单旋律逐项比对。多个范围或音符冲突在Plan公布前拒绝，不能顺序覆盖。

PerformanceHint=`{id,boundary_id,note_id,performance_id,velocity_delta,tone_hint,accompaniment_hint}`；velocity_delta=-12..12，tone_hint=null或soft/bell/dark/pluck/brass，accompaniment_hint=none|fade_in|reduce|sustain。只可引用该边界实际左右端点或局部原音符，一个note最多一个hint；无结构修改时允许桥/记忆内有限表演变化，力度仍1..127。仅主旋律忽略这些表现差别、统一soft/80。无条件默认目标音预示/鼓填充禁止。Joints记录所有共享原端点的边界组，精确`{id,boundary_ids,note_ids,original_endpoints,final_endpoints}`，null是真实无音；P6原joint不修改，新的统一最终端点须精确等一次应用实际结果。

JoinGroup=`{performance_id,input_note_ids,source_emission_id,render_event}`。逻辑Note不因播放合并改其保护结构；只有同演奏/同slice父/同origin/同音高、时刻和offset连续才生成一个物理事件，采用首次起音力度/音色，后片不重新起音。重复放置或嵌套occurrence不能共用performance_id。join_groups由lead纯归一化独立重算，规范音乐差异用这些真实播放事件，不将同一长音的不同分块算两套音乐。

BoundaryPlan为Proposal加`id version token layout_fingerprint protection_summary_fingerprint connection_plan_ref original_notes plan_fingerprint`，指纹除自身字段。`plan_boundaries(request,should_cancel=None,on_progress=None)->BoundaryProposal`为算法独立模块；lead `make_boundary_plan`完整认证后公布。`apply_boundaries(request,plan)->BoundaryResult`仅一次纯拼接和已知表演变化，不作曲/随机/重跑情绪。BoundaryResult精确`{schema,spec_rev,contract_rev,id,request_fingerprint,plan_ref,notes,emitted_notes,join_groups,operations,performance_hints,remaining_gaps,content_fingerprint}`。notes从全部原Layout同时消耗/产出，JoinGroup只影响emitted_notes。校验器重新从原Layout/已认证操作构造并比较全部结果，包括漏报影响/额外音符和桥内休止；不是接受生成器的READY。

### 13.11 FinalScore、编配和资产（FROZEN）

FinalScore精确`{schema,spec_rev,contract_rev,id,boundary_request_ref,boundary_plan_ref,connection_plan_ref,kind,mode,total_ticks,bpm,notes,emitted_notes,join_groups,performance_map,layers,remaining_gaps,target_resolution,protection_summary_fingerprint,source_fingerprint,music_fingerprint,score_fingerprint}`。kind=final|comparison，mode=melody_only|arranged；comparison来自同一候选P4完成后的真实基础排布，无gap时当前有效实际音乐，不能对比另一个候选或尚未补齐的编辑。所有谱ref与输入快照/候选链一致；notes逻辑保护不变，emitted_notes由合法JoinGroup规范化。谱fingerprint对全部字段除id/score_fingerprint计算，id由谱fingerprint派生，不自指；music_fingerprint仅total/bpm/实际发声pitch/start/duration，排除ID/label/velocity/seed/mode。不把基础candidate音符差异当最终差异。

每Layer精确`{id,role,name,preset,volume,pan,drum,notes,rules}`；role权威由允许的规则/ID/实际来源确定，不信字符串标签。主旋律事件逐项由emitted_notes派生，仅arranged允许已登记情绪preset/表达；solo仅单一soft主旋律/velocity80、无伴奏，实际pitch/onset/duration完全相同。陪衬规则profile=curve-arrangement-v1：从实际主旋律调性推导三和弦，和声逐拍/低音克制时值、按真实强度/情绪触发节奏与条件kick/snare/hat；每个伴奏Note保存具体规则、拍位置、和声/父音乐来源。独立validator按有限规则解析真实音符与参数，禁止任意新增旋律改名为harmony骗过；不允许复制主旋律或默认handoff。全部层总长精确固定，伴奏留白只克制延续，不新增主旋律。

`validate_final_score(request,plan,score)->ValidationReport`精确`{status,score_fingerprint,music_fingerprint,layout_fingerprint,protection_summary_fingerprint,checks,remaining_gaps}`，status=VALID才可渲染。边界前/后与编配后逐一校验完整桥集合、逻辑保护及物理合法合并、目标实际覆盖/音符支撑、来源、留白、剩余gap、固定总长/单旋律以及所有依赖版本。validation是独立返回，不放入自身乐谱hash产生循环。旧compile_score不直接用于P7，复用preset/和声原理/序列化/LMMS/尾音，另建同谱适配。

AudioAsset精确`{schema,spec_rev,contract_rev,id,version,candidate_ref,score_ref,kind,mode,renderer_version,files,body_ticks,body_seconds,audio_seconds,tail_policy,asset_fingerprint}`；files=`{wav:{path,sha256,bytes},mid:{path,sha256,bytes},mmp:{path,sha256,bytes}}`，kind=comparison|final，renderer=curve-final-lmms-v1，tail_policy=fixed-1s-existing-finish-audio（不宣称任意长尾音）。真实LMMS连续渲染并验证WAV可读/声道/长度/非静音、MIDI/MMP实际音符时间与绑定的表现谱；谱与文件完整就绪才AUDITION_READY。输出前总长及全部层onset/duration必须10tick可表达，否则OUTPUT_TIME_UNREPRESENTABLE，无任何量化；MIDI本身虽能精确tick，本轮完整三格式绑定仍明确按共同无损能力拒绝，原数据完整保留。

保存与加载只验证持久化事实，不重新安排/作曲/渲染；磁盘文件缺失/被换时音乐可读取，动态capability不可试听/确认该推荐。每次Play/Confirm/Export验证ref/hash/实际文件和模式；取消原生导出不改工程/选中/播放，atomic_export保护源与已有目标，三格式逐项可用，正式整曲导出要求remaining_gaps=[]。旧历史输出保持逐格式兼容。

### 13.12 完整推荐、有限搜索和前端Facade（FROZEN）

RecommendationRequest精确`{schema,spec_rev,contract_rev,token,input_project,input_contract_rev,input_fingerprint,scope,target_gaps,mode,seed,parameters,algorithm_version,request_fingerprint}`，scope=all|selected|current_complete；mode绑定输入settings，可显式只作为输出模式捕获（不修改工程）；参数精确`{completion_budget,bridge_parameters,connection_parameters,boundary_parameters,max_pipeline_candidates,max_recommendations}`；原三参数按各冻结版本验证，最后预算默认4/2，上限8/4。固定输入/seed排序可重现，取消每阶段/循环/渲染之间检查，不无限重试、不强行凑第二套。需要渲染时真实renderer槽全局串行。

推荐内部独立Controller/staging_bundle先P4(有gap)再P5原子锁/真实READY、P6、P7每套；没有gap不调用P4、不造新素材。可以处理P4 INSUFFICIENT中的合法单候选。每候选失败保具体阶段错误和全部保护/已有合法事实，另一套完整有效候选保留。全部finalScore完成后真实音乐再去重，按P4真实评分/处理收益和少改动排序，排除种子/名称/力度差异，有限预算内不足至少两套明确原因。

FinalCandidate精确`{id,version,request_ref,stage_refs,final_score_ref,comparison_score_ref,music_fingerprint,remaining_gaps,rank,reasons,assets,capabilities,modes}`；stage_refs精确`{completion_attempt_id,completion_candidate_id,bridge_attempt_id,connection_attempt_id,boundary_request_id,boundary_plan_id,boundary_result_id}`，无gap completion二字段null。capabilities精确`{score_scope,target_complete,can_audition,can_apply,can_export_final,blocking_reasons}`，scope=FULL|LOCAL，AUDITION_READY且当前输入授权才can_apply；LOCAL可确认但can_export_final=false。只把全部谱/资产完成的候选列有效，失败阶段事实仍有审计，不能以rendering标假READY。

RecommendationOutcome精确`{schema,spec_rev,contract_rev,request_fingerprint,status,candidates,facts,stage_bundle,search,insufficient_reason,failures,error,outcome_fingerprint}`；status=SUCCEEDED|INSUFFICIENT|FAILED|CANCELLED，facts为本轮新增有界叶事实，stage_bundle是独立P4/P5/P6注册表/快照，不含本轮P7attempt/outcome递归嵌套；源Project为p7时可携带其既有扁平final_facts闭包，不能递归嵌套历史完整registry。search精确`{tested_candidates,completed_candidates,duplicate_candidates,termination}`。none、无合法窗口可继续；桥/连接真正失败中止该候选。Final去重对象是最终emitted_notes，完全同音且只不同ID不能保两套。

Controller接口：
- `capture_recommendations(selected_gap_id=None,seed=31,parameters=None,mode=None)->{token,request,attempt_id}`；重复活动recommendation拒绝。capture注册快照及独立P7attempt，不改音乐。
- 后台纯`prepare_recommendations(request,source_facts=None,should_cancel=None,on_progress=None)->RecommendationOutcome`，source_facts为原有registry有限闭包，不嵌入持久化Request。on_progress事件`{seq,phase,message,candidate_id,stage_bundle}`；phase=BASE_COMPLETION/BRIDGE_DECISION/BRIDGE_LOCKED/BRIDGE_GENERATION/CONNECTIONS/BOUNDARIES/VALIDATION/ARRANGEMENT/RENDERING。锁真正公布后才BRIDGE_LOCKED，partial bundle包含真实锁与事实；主线程`record_recommendation_progress(token,event)`完整Token及seq按13.16登记，原型不混到新attempt。
- `finish_recommendations(token,outcome)->bool`独立认证所有实际谱/来源/事实/资产后暂存，成功不抢播/不应用。`fail_recommendations(token,error)`/`cancel_recommendations(token)`结束busy保阶段事实和旧音乐；终态旧回调拒绝。
- `recommendation_state()->{status,phase,attempt_id,candidates,error,message,search,insufficient_reason}`；status=IDLE/RUNNING/READY/FAILED/CANCELLED/INTERRUPTED/STALE/APPLIED，phase上列或AUDITION_READY，不暴露大registry给UI反复拷贝。候选DTO=`{id,version,title,scope,remaining_gaps,rank,reasons,score_ref,music_fingerprint,assets,capabilities,preview}`；preview=`{project,notes,protections,bridge_overlays,connection_overlays,boundary_overlays}`，全部对应候选私有实际谱，不借当前编辑标记。
- `recommendation_asset(candidate_id,kind='final',mode=None)->AudioAsset`重核实际文件、版本/模式/谱，不开始播放；UI明确Play才app.start_playback共享player。选卡与后台完成不自动播放、不改变原来playing_target。
- `apply_recommendation(candidate_id,transaction_id=None)->{changed:bool,receipt:ApplyReceipt}`同谱/同阶段原子认证应用；自动补全在完成后只对最高有效候选调用同一方法。取消视图/不确认不污染库。
- `effective_music()->EffectiveLayout`与`accepted_state()`返回实际可读音乐和ACTIVE/STALE接受状态；`history()`包含明确历史接受版本/各格式可用性，`history_asset`与`export_history`绑定选定score，同样LOCAL不能正式导出。

前端新RecommendationUI在既有候选区及stage选择器增加“完整建议”，查看建议/自动补全入口可达；四个中间stage依然如实不可应用。候选选择、原始/处理后对比选择、明确播放、确认、取消、重试都有明确状态。P7单一read-only preview覆盖画布，桥/记忆独立标记，返回恢复编辑选中/滚动。Tk/Controller提交只mainthread，thread只纯Request/源facts与取消Event/queue，完整token+seq/stage门禁；故障/result callback异常一定恢复可操作。stage计算不启动播放器，显示主体/含尾音真实时间与正在听对象。

### 13.13 接受状态、事实注册表与一次事务（FROZEN）

显式P7阶段允许外层Bundle升级`emoblocks.curve-bundle.v2`，原v1读取/另存保持v1和原音乐头。v2精确原六字段加`final_facts`，contract_rev仍等Project自身所属音乐版本（capture时可p4，确认后p7）；new_bundle无P7任务仍原v1。final_facts有限注册表条目`{id,kind,version,fingerprint,data,dependencies}`，Ref指纹=domain(kind)+canonical data，dependencies只引用同表Ref；kind=boundary_request/boundary_plan/boundary_result/final_score/audio_asset/application。每表最多2048条，图无环、依赖深度<=32、总文件上限128MiB（原v1仍20MiB）；Request.source_facts运行时快照但不存递归registry。P7attempt另有推荐request/outcome/phase/接受receipt，APPLIED是独立P7状态，不修改冻结P4/P5/P6状态枚举；其stage_bundle与源快照一并持久化，运行中恢复INTERRUPTED，不重建线程。纯恢复独立认证源/所有阶段、候选与refs/应用指纹；仅ref存在或hash自报不够。

Project顶层形状不变，只有明确确认事务设置contract_rev=p7。accepted_overlay是现有final_score Record载荷中的`p7`对象，保存Ref、实际FinalScore/桥叶覆盖信息/依赖写域/accepted_binding_fingerprint；accepted_candidate记录原输入snapshot与transaction_id，不嵌完整Project或registry。完整音乐source事实在Bundle/snapshot/attempt/final_facts中。P7 Project与快照读取需解析并认证Registry的完整有限依赖闭包，旧版本不迁移。保留目标基础放置、原始source/材料；实际自动桥额外登记原P5保护与适配后的P1桥Plan/Result记录，不能只存UI标签。原手工/失败桥锁不删除、活动桥音符由实际覆盖读取，谱与保护投影一致。

`accepted_binding_fingerprint`只对音乐有效依赖投影计算（project_id/ppq/bpm/total/基础placements/intensity/blank/settings/活动protections），排除自身记录/ref、文件路径、音乐saved/undo/session、显示标签及编号。应用后才绑定此投影，原input snapshot fp只作来源，两者不得混用。新资料导入不改已接受音乐依赖时保留有效层；任何音乐编辑/undo后未应用旧候选授权不可复活。已应用音乐undo/redo恢复保存状态本身，读取绑定重新校验，不调用generator或重新编号。

接受读取统一`curve_application.effective_music(project,fact_registry=None)`：ACTIVE时返回同一FinalScore实际notes与合法emitted/层；无有效最终层时返回当前实际基础＋仍锁定的已接受bridge事实，并明确连接/边界失效，不整体丢桥或偷用旧基础端点。`curve_project.current_notes`的p7分派、P4上下文/候选notes、P5 actual_notes及P3固定桥/记忆检查必须经该有效读取接线，不造假p4输入绕认证；旧contract分支原样。基础选择与前情绪Snapshot保持原状，原bridge保护永不因派生层失效解除。若新强度/位置使完整记忆与既有桥固定锁矛盾，正式重算事务拒绝且工程/undo/saved不变，说明需明确新计划，不能删除任何保护来放行。

ApplyReceipt精确`{transaction_id,candidate_ref,score_ref,input_snapshot_id,pre_revision,post_revision,accepted_binding_fingerprint,registered_source_ids,registered_material_ids,accepted_record_id,result_id}`。候选/谱/阶段/资产都已验证且同输入；确认时不重新抽样/生成/渲染。后台完成消耗原活动Token，确认授权检查持久化attempt身份和原session/revision及当前Project fingerprint；load后旧回调永远拒绝，已持久化READY候选仅在原输入仍精确匹配时由新session的明确确认动作创建新应用授权，编辑→undo或saved STALE不重活。事务本身revision递增只改变应用绑定，不直接失效新接受层。

新增专用`ProjectSession.apply_prepared(project,expected_revision,expected_fingerprint)`，只供已认证应用事务；预先准备/validate完整Project及Bundle/facts/素材/labels/源/桥保护/记忆/覆盖与接受记录，全部通过后一次commit音乐、request生命周期和注册表。任何失败不留下source/编号/历史半提交。只登记本次实际采用P4素材及桥乐句/子块，没用/失败临时材料不进库。每candidate固定transaction_id重复确认幂等，若已应用绑定仍当前返回同receipt且包装changed=false；undo/redo只音乐状态，审计和已输出文件保留，历史版本标明当前/历史不冒充当前编辑。后续派生层失效保audit_context（仅placements/protections）与原registry叶，不循环嵌套快照。

全部gap已解的接受版本才正式导出；局部版本保存/试听/应用合法但余gap明确。输出/播放选择历史已接受版本时绑定其已认证原谱/资产，与当前编辑或推荐选择独立，后续编辑不覆盖旧文件。缺失原导入文件用已有Source快照；缺音频不把工程读坏。自动补全仅选择本完整Outcome最高合法候选走同一Apply，不存在“简化补全”。


### 13.14 二次评审整合：模式、授权与UI能力（FROZEN）

本节裁决13.2–13.13中概括措辞；精确字段以本节及前述精确形状为准。初轮算法/前端只读均指出具体缺口，旧编配与素材tie反例已复现；不以这些探针冒充P7实测。

两mode共用同一经过P4–P7确定的逻辑主旋律与播放事件结构。输出mode是表现/渲染选择，不改Project音乐设置、不重跑补全/桥/连接/边界。新增`prepare_candidate_mode(request,candidate_id,mode,source_facts,should_cancel=None,on_progress=None)->ModeOutcome`明确仅从同一已认证BoundaryResult编配并渲染该mode的一对谱/资产；ModeOutcome=`{candidate_id,mode,final_score,comparison_score,assets,error}`，source阶段身份仍相同，结果由独立门禁登记为新增mode refs，不替换另一mode资产。另有`capture_recommendation_mode(candidate_id,mode)->{token,request,candidate_id,mode,source_facts}`与`finish_recommendation_mode(token,outcome)`，迟到/重复/失效拒绝，不抢播/改音乐dirty。FinalCandidate初始mode由RecommendationRequest.mode捕获；每mode单独管理谱/资产/能力，推荐身份取忽略mode的BoundaryResult/阶段Ref而非表现ScoreFP，避免模式切换成为新推荐。AudioAsset.candidate_ref指纹为request+stage_refs+BoundaryResult内容身份，排除rank/asset路径/表现mode；AudioAsset.score_ref仍绑定具体mode表现谱。music去重不因mode/力度而变化。

候选DTO保留13.12精确字段，并增加`modes`映射，仅melody_only/arranged键；每mode精确`{status,final_score_ref,comparison_score_ref,assets,error,capabilities}`，status=SCORE_READY/RENDERING/AUDITION_READY/FAILED/MISSING。assets精确`{comparison:AudioAsset|null,final:AudioAsset|null}`；两侧都完整认证才该mode AUDITION_READY。所谓已试听绑定是资产已准备且认证，不要求用户听完整段，自动补全无需人为播放。当前mode绑定选中/确认/导出明确对象，UI不得把missing当ready。

capabilities精确扩充为`{score_scope,target_complete,can_preview,can_play_comparison,can_play_final,can_apply,can_export_final,blocking_reasons}`；只单侧文件有效可显式播放该侧，确认要求同mode两侧有效且完整输入授权，can_export_final仅已接受历史FULL结果，不对尚未确认推荐开放正式导出。UI从后端能力取值，不猜READY/count/路径。缺文件读取音乐仍成功，用户明确重试准备mode资产，新render Token拒绝旧回调，不重新作曲；保持原播放对象。

RecommendationState精确`{status,phase,attempt_id,candidates,error,message,search,insufficient_reason,accepted_ref,capabilities}`，accepted_ref为已接受Ref或null，capabilities=`{can_calculate,can_cancel,can_auto_complete}`。候选选择与输出模式可保留各自UI偏好，不产生music dirty或undo。准备mode可使用既有P7正常job框架，不新增任务框架；相同候选/mode重复在RUNNING时拒绝。

ConfirmationRef精确`{session_id,edit_revision,input_fingerprint,candidate_ref,mode,final_score_ref,comparison_score_ref,asset_pair_fingerprint}`。`confirmation_ref(candidate_id,mode=None)`仅纯认证当前输入/谱/双资产，返回当前session授权，不启动播放/写音乐。`apply_recommendation(candidate_id,transaction_id=None,mode=None,confirmation_ref=None)`包装changed与13.13 Receipt，确认Ref若传入必须全部匹配，模式不能与已准备资产不一致；默认由当前选中mode明确捕获并同一次调用复核。先检查已应用同transaction/同candidate/同谱幂等，再核旧修订；同transaction不同谱拒绝，undo后再确认旧transaction不能重新应用（可查看审计），redo只恢复保存音乐。

应用前先完整准备并认证所有未来Project/Bundle/registry/素材/编号/保护及新的接受绑定，然后可靠保存当前暂存facts/输入快照（调用已有快照自动保护），保存失败终止且不改音乐/库/undo/编号。保存真的成功才mark_saved，不显示假已保存。随后同mainthread一次提交音乐和接受audit；事务中不再作曲/渲染/编号二次分配。P7 attempt的APPLIED不能改变旧P4/P5/P6状态；审计在外层保留，undo音乐恢复原version/header和全部数据，redo恢复保存p7音乐。

已应用后任意依赖音乐编辑保守使连接/边界层失效，明确显示当前编辑有未生成修改；仍有效固定Bridge覆盖与保护保留，不能自动回旧基础绕开桥。实际有效音乐由统一读取给P3/P4/P5/后续生成，BaseProject仍保用户原选择。材料/显示编号/UI偏好不在接受绑定音乐投影中；注册表Ref必须与对应实际谱/音符来源/计划事实一致，而不只是存在。ACTIVE可播放接受历史，STALE后历史文件仍按原版本明确试听/导出（FULL限制），当前编辑不会误用其无效连接。自动bridge固定音乐不能直接映射到被遮盖的旧placement编辑；前端显示只读保护范围/理由，后续明确桥移动/删除另需正式更新事务，不能擅自释放。

Renderer串行单次LMMS超时240秒，每候选双资产逐个；全搜索max_pipeline_candidates<=8/max_recommendations<=4，并在阶段之间、循环中、slot等待和渲染结束检查cancel。取消不伪造另一个成功音频。真实正常路径至少两套不同推荐及两mode的实际WAV/MIDI/MMP证据；故障路径模拟允许但明确区分。对比分数取已补齐基础（保手动桥）而非原未补齐编辑；接受谱=播放处理后谱=导出谱，记录Ref/文件hash/实际输出音符证明。


### 13.15 末次整合：音乐账本、规则、来源和持久化形状（FROZEN）

本节补齐R2双方明确缺口，独立verifier仍须审查；历史8–12节正文不修改。Ref.version无显式版本的不可变对象统一1，Plan/Asset用自身version。所有hash继续8.3的域+canonicalJSON规则，所有排序明确禁止靠caller顺序混拼。

指纹：RecommendationRequest/request_fingerprint域emoblocks.recommendation-request.v1排除自身字段；BoundaryRequest全文域emoblocks.boundary-request.v1（无自身hash字段）；Layout全文域emoblocks.final-layout.v1；BoundaryPlan域emoblocks.boundary-plan.v1排除plan_fingerprint；BoundaryResult域emoblocks.boundary-result.v1排除id/content_fingerprint；FinalScore域emoblocks.final-score.v1排除id/score_fingerprint；AudioAsset域emoblocks.final-asset.v1排除id/asset_fingerprint；Outcome域emoblocks.recommendation-outcome.v1排除outcome_fingerprint。Registry Ref.fingerprint使用对象原生指纹，不再用另一个kind域偷偷替换；entry.id/version必须等对象id/version（无version用1）。ApplicationFact的Ref对13.13 Receipt全文域emoblocks.application.v1；ID=transaction_id。CandidateRef对request_ref+stage_refs+BoundaryResult内容Ref域emoblocks.final-candidate.v1，排除mode/表现谱/asset/rank，id由该digest产生，version=1。实际音乐指纹只排序`(start_tick,pitch,duration_tick)`的emitted_notes，含bpm/total_ticks；不以ID/label/seed/力度/mode计差异。

Boundary.search精确`{tested_boundaries,attempted_operations,termination}`，分别计算实际几何边界评估数、提出并检查的具体操作数；termination=COMPLETE|POLICY_NONE|BUDGET_EXHAUSTED。预算没搜索完且没有合法操作时抛SEARCH_BUDGET_EXHAUSTED，不返回NO_LEGAL_OPERATION；有已认证部分操作可提交并明确预算终止，不伪称全搜索。assessments逐边界`{boundary_id,method,accepted,reasons}`；reasons是非空字符串列表。Structural预算按消费/产生原Note逐一计Δpitch/Δstart/Δduration，不只看范围；remove的弱音必须duration<=120且velocity<=80、起点非四拍强拍、非受保护（并不移除任何目标唯一音符支撑）。可合法不移除而用奏法，不能为达到某类型强造弱音。

Joint端点列表按boundary_ids的排序排列，每端点精确`{boundary_id,left:Endpoint|null,right:Endpoint|null}`，Endpoint=`{note_id,pitch,start_tick,duration_tick}`，original为同一原Layout的真实最近端点，final为一次应用后的对应最近端点；原Note消失时不能保留假ID。join_group.render_event是P3八字段Note，ID=域emoblocks.final-emission.v1对performance_id/source_emission_id/按时间排序input_note_ids，origin取共同origin、pitch/start取首片、duration精确加和、velocity取首片、slice=null、lineage为按input次序去重全部原lineage与ID；单片不生成JoinGroup且保原Note。FinalScore.performance_map精确列表`{emitted_note_id,logical_note_ids,performance_id,preset}`，逐事件完整覆盖，无重复/遗漏，逻辑ID解析自该Score.notes和JoinGroup，不猜不透明ID。保护逻辑原Note结构不变，物理事件独立通过原发声/归属/连续offset检查；旧独立place误合并反例必须拒绝。

来自已接受p7音乐且不是当前base/BridgeResult/ConnectionResult中原Note的ledger父：stage=final_score，owner_id=已认证旧Score.id、note_id=实际接受Note.id、material_snapshot_id=null、component_path=原performance的完整路径；content_fingerprint=旧Score.score_fingerprint。此事实须从source registry与Project真实绑定独立解析，不能退回旧A素材。为旧P4/P5/P6服务新增p7输入分派，旧输入仍原路径。P5/P6旧五字段ParentRef在input_contract_rev=p7时允许kind=accepted_score，owner_id=旧Score.id、material_snapshot_id=null、note_id=该Score真实logical Note.id、component_path保持原演奏；原p0/p23/p4输入绝不能使用此新kind。纯验证解析已接受Score叶事实，保已知origin/完整父血缘，不能清空或借无关合法来源。lead仅在curve_completion/curve_bridge_music/curve_bridges/curve_connections的源读取/父解析处接公开数据适配，不改既有音乐规则或旧版本校验；算法worker只新boundary文件，避免冲突。

P7专用`captured_music` Record只用于私有P4候选保持输入有效音乐：payload精确`{source_score_ref,source_input_fingerprint,source_notes,performance_map,base_binding_fingerprint,added_placement_ids}`，source_notes是捕获输入实际接受逻辑谱，不含新填充；实际基底=原source_notes＋新增放置实际音符，原桥/连接/最终音符不因候选填另一gap而消失。candidate/Source验证从P4 original request逐字段重建此记录，source registry匹配真正旧Score，不能caller填一个hash冒充；仅contract_rev=p7分派，普通用户音乐编辑将captured_music失效，只有明确当前accepted ACTIVE或私有候选carry绑定合法才读取。实际P4 contexts/notes与P5读取均走统一函数，不能拷成p4壳绕门禁。

对比谱保护分支：comparison精确P5 request.base_project的有效音乐，含其既有桥/记忆/主题/手工/留白，但不要求含本轮尚未加入的自动桥；final必须完整就绪P5桥及P6/边界实际结果。两者共享同一候选来源/快照/模式，不用当前未补全工程与之混比。

Layer.rules精确`{profile,entries}`，profile=curve-arrangement-v1；entries每实际note一条`{note_id,rule,source_note_ids,region,start_tick,duration_tick,pitch,velocity,key_context,intensity,emotion}`。rule=melody/harmony/bass/pulse/kick/snare/hat。source_note_ids只能该Score实际发声父，不能随意给一个合法source标签。melody逐emitted_note一一输出，音高/绝对时刻/时值精确不变，arranged按onset emotion及合法tone_hint选soft/bell/dark/pluck/brass、velocity沿用已校验表达，solo固定soft/80，volume=35、pan0/drumnull。mainNote不可复制到两层。

伴奏有限公式：region为实际音乐Segment或主动留白首拍的克制延续；key_context从该段已认证材料调性/实际旋律推导（无材料调性用既有infer_key纯数学），大/小调尺度沿用现有七音，选七个三和弦中对本段实际notes按时值加权最多的degree，同分最早degree。voicing根48+pc，其余向上最近chord音；harmony每PPQ480一个和弦，span=min(PPQ,region.end-tick)，duration=span，velocity=round(28+20*level)、preset=dark(sad/suspense)否则pad、volume14；bass根低12，duration为span*.8向下选新伴奏10tick单位、velocity=round(40+28*level)、volume20。pulse仅level>.35且非sad的奇拍，stride=120(level>.8)/240(level>.6)/480，按voicing轮换加12，duration=min(span,stride*.6)的合法10tick新伴奏单位，velocity=round(30+25*level)，presetpluck/volume15；suspense每第三细分按已有克制规则跳过。kick/snare/hat仅crisis/resolve且level>.45，kick偶拍pitch36 duration<=100 velocity=round(50+25*level) volume20，snare奇拍pitch38 duration<=100 velocity=round(45+20*level) volume15；hat每240，crisis且level>.8时每120，pitch42 duration<=60 velocity=round(30+20*level) volume10。drum对应既有bassdrum01/snare01/hihat_closed采样，MIDI GM音高与MMP采样key57的既有映射明确记录，不当成主旋律移调。

在主动留白内无pulse/鼓/新增melody，只有前实际和声可延续最多一拍，velocity<=35；若没有前音乐则不生成。局部未解gap内不生成新主旋律或将其算完整；伴奏也不偷偷填完该gap。层角色和notes必须与这些有限rule/slot的实际来源、音高、时值、强度及数量逐项对应，不能仅验证role字符串/profile或自报保护通过。不使用旧compile_score量化/夹紧/目标音预示/双重主旋律。新的伴奏选10tick单位仅是它自身的明确生成规则，不改原主旋律tick；若region起点或span令最终实际层不可无损表示，整体输出明确拒绝。

final_score.payload精确P1必需`{total_ticks,notes,protection_summary_fingerprint,validation}`加p7对象；p7精确`{schema,candidate_ref,score_ref,final_score,mode,binding_fingerprint,bridge_overlays,connection_overlays,boundary_operations,write_ranges}`，schema=emoblocks.accepted-overlay.v1。bridge_overlays元素`{id,range,notes}`，与真实P5结果/固定锁逐项等；connection_overlays=`{id,range,notes}`，对应P6结果，不作为新Bridge锁；boundary_operations原认证Operation列表，write_ranges为所有实际结构变化支持域。完整FinalScore是小型无Project/Registry嵌套叶，数据必须与score_ref解析的Registry事实逐字段一致（不是自签hash）；validation为实际ValidationReport，顶层notes同FinalScore.notes。INVALIDATED状态追加原有audit_total_ticks与仅placements/protections的audit_context，p7原载荷事实保留，不覆盖原音乐历史。接受记录使用P1 accepted_candidate字段并加`mode candidate_ref score_ref application_ref result_id`，任何引用必须闭合于当前Bundle.final_facts和原snapshot，不悬空。

P7Attempt精确原通用`id snapshot_id input_fingerprint state records protections staged_materials error`加`recommendation`；records/protections/staged_materials都为空（实际保护在私有stage_bundle，不混到current Project）。recommendation精确`{schema,spec_rev,contract_rev,request,phase,last_seq,cancel_requested,partial_stage_bundle,outcome,mode_bindings,mode_jobs,receipt}`。schema=emoblocks.recommendation-attempt.v1；phase未开始null，partial_stage_bundle开始null；outcome/receipt未完成null；mode_bindings为`{candidate_id:{mode:{final_score_ref,comparison_score_ref,comparison_asset_ref,final_asset_ref,asset_version}}}`，只有完整同版本双资产才原子更新，不挑两侧最新文件混拼。mode_jobs列表`{token,candidate_id,mode,asset_version,status,error}`，status=RUNNING/READY/FAILED/CANCELLED/INTERRUPTED/STALE；未知模式/ID拒绝。FinalCandidate.modes持久化相同绑定解析出的13.14状态/谱Ref/完整资产/能力，全部必须与唯一mode_bindings匹配，重试新asset_version且保旧事实，不能恢复时猜模式。P7Attempt state增APPLIED，仅该schema；旧attempt不增枚举。

### 13.16 最终Frontend DTO、取消审计及模式终态（FROZEN）

补全preview精确13.12六字段加memory_info；memory_info沿P3原格式`peak_tick lookup_tick state placement_id component_path range protection_id`，由对应私有基底/保护真实定位，不借current标记。boundary_overlays元素精确`{id,tick,method,editable_ranges,operation_ids,performance_hint_ids,reasons}`。bridge/connection overlays复用已有P5/P6 preview形状，阶段ID/真实notes对应本候选。

EffectiveLayout精确`{project_id,total_ticks,bpm,notes,emitted_notes,segments,protections,remaining_gaps,memory_info,accepted_ref,derived_layers_status}`；derived_layers_status=ACTIVE|STALE|NONE。`accepted_state()->{status,candidate_ref,score_ref,result_id,mode,remaining_gaps,message}`；status=NONE/ACTIVE/STALE，NONE引用null/remaining_gaps为当前gap，保stale来源供历史标识。Bridge前后实际读取不能自造忽略覆盖的placement音符；只读保护帧不能被编辑事件映射到其底下旧素材。

历史条目在现有`history()`基础上新增P7数据但不破坏旧格式访问：`{id,label,generated_at,version,scope,mode,score_ref,modes,availability,application_status}`；scope=FULL|LOCAL|LEGACY，application_status=CURRENT|HISTORICAL（按当前音乐绑定，不按last result）。availability每格式单独bool，LOCAL正式三格式导出皆false（不删除真实开发文件）。`history_asset(id,mode=None)->AudioAsset`、`export_history(id,format_,destination,mode=None)->Path`显式mode，不提供对应模式资产时错误不回退。旧legacy接口无新增mode数据仍按旧三格式/sourcePath合同，只读规则不变；P7按该history result的已保存谱/模式/资产，不用current editor替代。

Queue envelope精确`{token,seq,kind,payload}`；kind=progress/result/error，seq来自worker同request单调递增，progress.payload含同seq及13.12 event字段。controller `record_recommendation_progress(token,event)->{accepted,continue_processing}`，相同seq重复返回false且不当新失败，低seq/身份错误拒绝；完整验证stage_bundle属于该原request Project和原版本，既有锁/已认证事实不可从新snapshot删除或改版本，才能登记/显示。UI对progress提供ACK Event，backend锁登记后必须等待mainthread确认progress审计再继续音乐生成；ACK不是Tk对象，worker不访问Controller/Tk。每个桥部分READY也在继续下一桥前发布审计。锁是真正private backend事务事实，不是UI先显示再找锁。

`cancel_recommendations(token)`先设置cancel_requested、phase=CANCEL_REQUESTED，取消Event阻止下一阶段；provider完整收拢已产生阶段事实后finish CANCELLED、消耗Token并恢复操作，不在锁事件仍排队时丢掉它。取消进度可只登记审计，不继续音乐；明确P7队列ACK/取消标志实现，不能把未收拢称已完成。允许专属审计路径为STALE/FAILED/CANCELLED旧attempt登记经认证的真实partial_stage_bundle（同原Token/输入/plan/单调seq、保护/事实只保留不删除），返回continue_processing=false；绝不改变终态、授予READY、替换current/new attempt/播放器或应用音乐。旧result/确认仍拒绝，这条路径仅防止输入改变或回调异常导致有效锁审计丢失。取消最终锁/READY内容都可持久化验证，不能靠重复发送任务恢复。

`fail_recommendations(token,error,stage_bundle=None)`恢复终态，若带partial事实先独立认证并保留；invalid事实拒绝且保已信任旧审计，不将假锁持久化为有效。Thread.start失败直接该接口（无private线程/锁）。`fail_recommendation_mode(token,error)`和`cancel_recommendation_mode(token)`只该mode Job失败/取消，不消耗原candidate/其它mode有效谱资产；mode准备异常/result登记异常同样恢复操作。保存中RUNNING mode_job恢复INTERRUPTED，不启动线程、不撤销已有其它mode READY；mode Token原epoch永失效，显式重试新version。APPLIED/历史候选准备另一mode凭该保存接受Score/BoundaryResult新当前session只读render授权，不能用原input token再次应用。

ModeOutcome/asset registration必须两个资产同candidate/mode/asset_version与各自score_ref一致；任一侧失败不发布新pair、不冒充AUDITION_READY。已有另一mode/旧同谱有效pair保留，只解释本次失败；不能回退别的候选音频当成功。mode rendering/cancel不改音乐saved/undo/选材/playing对象，只staging audit。推荐缺文件后用户可明确重试mode；不重新补全/生成/桥/连接/边界。

前端可独立依冻结 DTO/Facade实现mock行为测试，但真实集成必须再用真实Controller、真实算法及LMMS验证。所有渲染与设备任务互斥串行，生成到音频/明确Play/确认/保存重开是本轮交付，不留模拟音频到P8。完成P7独立验收后停止；P8建议只供后续用户授权。


### 13.17 独立契约R1修复：请求身份与来源闭包（FROZEN）

独立R1明确FAIL F1/F2，前后200文件/HEAD/完整manifest一致；只修本节精确缺口，仍不开始产品实现，不重置计数。

BoundaryRequest增加必需`id`（13.10字段列表同步），由域emoblocks.boundary-request-id.v1对精确`{recommendation_request_id:token.request_id,candidate_ref,connection_attempt_id:connection_ref.attempt_id,plan_id,plan_version}`计算；不取默认token ID、不借Plan ID。一个推荐request多candidate各有独立P6 attempt/plan，因此Request.id唯一；即使无gap candidate_ref=null，不同真实connection attempt仍区分。Ref.id即此id、version=1、fingerprint=13.15 BoundaryRequest全文摘要（含id）；stage_refs.boundary_request_id与FinalScore.boundary_request_ref及Registry.entry.id必须一致。旧Token随事实保存不重写，加载纯重算公式验证；确认新session授权不会改变已有BoundaryRequest身份。重复ID但不同数据/父/计划一律拒绝，不把两候选串到同一请求。

FinalScore.source_fingerprint唯一公式：域emoblocks.final-source.v1对精确`{kind,notes,sources,parents}`的规范JSON。kind=final|comparison。notes列表元素精确`{id,origin,lineage,slice,parent_ids}`，从该Score全部逻辑notes取实际四字段（不取velocity/渲染层/path）；parent_ids按字典序去重。notes按id字典序排序，ID不可重复。对final未结构变化Note，parent_ids为同一BoundaryRequest.actual_layout原Note ID；replace/add必须从该已认证Plan Operation逐项读取真正parent_note_ids，remove不产生descriptor。对comparison各Note即已补齐真实base的Note，parent_ids为其本身；用单独从P5 request.base_project有效音乐重建的基底ledger，不误拿被本轮自动Bridge替换后的父。不同mode不改变此逻辑来源投影。

parents元素精确`{note,parent_ref,material_snapshots,accepted_score_ref,accepted_source_fingerprint}`，note是实际原始父的完整P3八字段（含其velocity、来源、lineage、slice），parent_ref为13.10六字段NoteRef，必须由真Layout/base/源registry独立解析，不接收caller自填。parents按note.id排序、唯一完整覆盖notes.parent_ids，无额外或遗漏。placement的material_snapshots为该次基础快照与实际情绪变体（若有）的真实完整快照；bridge为该结果的base_material与material（继承分支只取真实现有非null快照）；connection的快照为空，其真实发声通过原P6 Result.content_fingerprint解析；final_score父快照为空，但accepted_score_ref精确旧源Score的Ref，accepted_source_fingerprint等该旧Score真实source_fingerprint。其余类型后二字段均null。material_snapshots按id排序去重，同ID不同数据拒绝，组合children与generation保持原实际快照，不压成标签。

parent_ref.content_fingerprint：placement为域emoblocks.material-snapshot.v1对实际使用Snapshot全文（emotion_variant或base_snapshot）；bridge/connection用原结果content_fingerprint；final_score用旧Score.score_fingerprint。父Note必须在该具体Snapshot/Result/旧Score中按真实演奏映射解析，不能借另一合法Source或另一place的同名音符。旧accepted父由源Registry与原输入Project实际绑定授权，旧score/source摘要经其本身独立闭包验证；当前Score不得作为自身父，Registry全图无环。Ref/旧来源指纹是叶锚点，不在source投影中递归嵌套整谱/整Project。

sources为上述全部逻辑notes、父notes及material_snapshots的notes/children/generation.base_notes中所有非null origin.source_id的精确闭包。每Source从该BoundaryRequest对应已认证P5 base_project.sources取真实完整`{id,label,length_ticks,notes,provenance}`，Sources按id排序，各Source.notes按(start_tick,pitch,duration_tick,id)排序；其余字典canonical排序，lineage/component_path保持语义次序。不查询原文件是否存在，不从UI/当前后来修改工程取Source。known origin三字段必须解析到具体原Note/track，不允许清空/错指另一合法来源；Parent变换血缘按原完整lineage+真父ID核对，hash不是授权。无origin的真实手工基础Note闭包Sources可空，但不能把原已知origin伪称手工清空。

固定摘要向量（只证明摘要算法，不授予音乐READY）：空投影`{"kind":"final","notes":[],"sources":[],"parents":[]}` → b7e9e8d9b68a835c5828297af15ecc977f7aa8c096059a073d598e904c87fd88。非空手工来源向量如下，预期摘要 9f5f557644d0f0d7e769b47cd9eb00671af1b1de6554b096ac684878c30e4e24：

```json
{"kind":"final","notes":[{"id":"p:n","lineage":[],"origin":null,"parent_ids":["p:n"],"slice":null}],"parents":[{"accepted_score_ref":null,"accepted_source_fingerprint":null,"material_snapshots":[{"children":[],"generation":null,"id":"m","kind":"block","label":"fixed-vector","length_ticks":480,"notes":[{"duration_tick":480,"id":"n","lineage":[],"origin":null,"pitch":60,"slice":null,"start_tick":0,"velocity":80}],"phrase_id":null,"provenance":{"method":"manual-fixed-vector"}}],"note":{"duration_tick":480,"id":"p:n","lineage":[],"origin":null,"pitch":60,"slice":null,"start_tick":0,"velocity":80},"parent_ref":{"component_path":[],"content_fingerprint":"93e617d632a20c7078f33d2b870f55e2a401e904b6a2411ddc7b0d90b40dba33","material_snapshot_id":"m","note_id":"p:n","owner_id":"p","stage":"placement"}}],"sources":[]}
```

实现专项必须机械复核这两个常量；并在真正P4/P5/P6实际最终请求上模拟清空origin、借另一个合法Source、伪造lineage/parent_ref/旧accepted_score来源，重新计算source/score/asset元数据hash后仍独立拒绝。保存重开重算同来源指纹且不调用任何生成/渲染。scope=LOCAL与FULL、comparison和final各按自身真实父闭包认证，不把比较谱要求含本轮自动桥。

### 13.18 运行时来源闭包补充（DRAFT）

服务契约修订 `CONTRACT_REV=curve-workflow-v2-r3-p7-runtime1` 是第13节已冻结音乐对象之上的可加运行时捕获修订；第13.1–13.17及其对象schema/数据头 `contract_rev=curve-workflow-v2-r3-p7` 保持原版，P4/P5/P6对象及旧Project/Bundle也保持所属版本，不迁移持久化数据。各新任务使用runtime1服务修订，token和Boundary/FinalScore/AudioAsset仍使用已冻结p7数据版本。第13.12 capture返回形状由本节明确扩充，旧调用只读取原三个字段仍兼容。

`capture_recommendations(selected_gap_id=None,seed=31,parameters=None,mode=None)` 返回精确 `{token,request,attempt_id,source_facts}`；source_facts是与本次input_project同时捕获的当前Bundle.final_facts有限深复制（旧v1输入为[]），在主线程完成。它只用于后台 `prepare_recommendations(...,source_facts=...)` 的运行时闭包参数，不写入RecommendationRequest、每个Project或嵌套历史快照。worker不得自行读取可变Controller/当前工程代替该捕获。

后台私有Controller建立后、任何阶段捕获前先登记并纯校验该原闭包。不能用旧接受音符去构造没有依赖registry的阶段Bundle；完整旧Score/Boundary请求与计划的原生引用必须解析。只需要源事实的有限引用闭包，最多沿用2048条/32层/128MiB预算，不读取原导入文件、不生成或渲染来补事实。闭包缺失、篡改、跨工程或版本不匹配中止本次请求，不改当前编辑、保护与undo；输入随后变化由原Token/修订/seq门禁拒绝。

源读取文件范围补充：lead可在 `curve_melody._bridge_parent_table` 与其 parent_snapshots 键解析处加入p7 accepted_score源适配，保存真实旧FinalScore叶快照和Ref；只改源读取、父身份、真实现有快照解析，不改变旧P5构作音乐规则、算法版本或旧输入验证。算法worker仍仅curve_boundary_music与对应测试，公共入口/源适配由lead独占。

验收：已接受p7工程→新推荐捕获→私有P4/5/6→最终score，保原真实音乐/桥锁与完整来源；捕获后立即编辑、撤销同内容与取消均不能用旧闭包绕过会话门禁；缺闭包/借另工程合法闭包/伪造旧Score重新计算hash均拒绝；保存重开不调用生成/渲染。新项目的source_facts=[]兼容原正常路径。只读评审与独立PASS后才能将本节标为FROZEN并实施新增捕获字段。
