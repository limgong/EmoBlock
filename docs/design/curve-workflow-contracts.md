# 强度画布 v2 r3 公共契约草案

SPEC_REV=curve-workflow-v2-r3
CONTRACT_REV=curve-workflow-v2-r3-draft1

**状态：DRAFT。未通过 P0 独立检查，未冻结，未实现。** 产品依据为 [r3完整规格](curve-workflow-v2.md)。本次只更新文档；以下对象、方法名、字段和错误码是候选接口，不代表现有代码能力。公共接口不依赖 Tk，旧规划不得用来绕过 r3 门禁。

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
