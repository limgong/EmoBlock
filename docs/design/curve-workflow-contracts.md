# 强度画布 v2 r3 公共契约草案

SPEC_REV=curve-workflow-v2-r3
CONTRACT_REV=curve-workflow-v2-r3-p0

**状态：FROZEN。P0 ROUND=2 独立检查 PASS；规范已冻结，功能尚未实现。** 产品依据为 [r3完整规格](curve-workflow-v2.md)。本次只更新文档；以下对象、方法名、字段和错误码是候选接口，不代表现有代码能力。公共接口不依赖 Tk，旧规划不得用来绕过 r3 门禁。

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
