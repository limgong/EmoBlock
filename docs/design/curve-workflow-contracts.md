# 强度画布 v2 契约草案

**状态：DRAFT。** 仅定义协作边界与候选数据结构，未实现、未冻结为公共 API；P0 由 lead-backend 完成契约定稿，再允许依赖任务实现。产品约束以 [已确认规格](curve-workflow-v2.md) 为准。旧 `emoblocks.assembly.v1` 与 `emoblocks.story.v1` 只读兼容入口独立，新内层 schema 为 `emoblocks.assembly.v2`；外层工程封装继续兼容，禁止自动迁移旧作品。

## 1. 时间、身份与公共边界

- 音乐时间统一为整数 tick，`PPQ=480`，1 拍=480 tick，四拍格=1920 tick；导入非480 PPQ文件由后端统一归一化。公共域对象不混用拍数、像素和秒。
- 区间为半开 `[start_tick,end_tick)`，长度严格为正；相邻边界可接触。秒数仅在播放器/渲染适配层由 tick 和 BPM 推导；实际 WAV 秒数/尾音另作真实音频元数据，不能代替音乐主体长度。
- BPM 有限且为正，沿用现有40–220验证范围；改 BPM 不改 tick 位置。初始 `grid_count=8`、`bpm=120`，`total_ticks=grid_count*1920`，没有预填放置。
- ID 为独立稳定字符串，名称/标签仅供展示。来源、完整版本、分块、组合、放置、情绪变体、建议方案、生成请求、成品各有独立 ID。
- 公开输入/输出是可深复制、JSON 可序列化的纯数据；无 Tk 控件、像素坐标、线程对象、音频句柄。后台不能访问 Tk。

## 2. 素材版本、分块与组合

候选字段：`sources`（原始导入快照）、`melody_versions`（A/B/C/D完整版本）、`materials`（分块/组合）、`label_counters`（稳定展示编号）。

完整版本记录 `id, source_id, kind, notes, length_ticks, key, provenance, transform_version`。A保持原始；B/C/D对应规格中的三种预处理，D是可替换旋律而非新增声部。版本准备在导入后进行，不在用户选定分块后的生成过程中偷偷换版本。

音符快照字段 `pitch,start_tick,duration_tick,velocity`，时间相对素材起点，合法MIDI音高/力度；有休止的时间也计入 `length_ticks`。B/C/D的具体变换参数与时值策略由P0进一步定义，不能由前端自行补齐。分块保留四拍窗口的实际时间，短尾不补长。

分块记录 `id, version_id, label, length_ticks, notes, origin`；origin含原始来源、版本、局部起止、变换链和文件指纹/快照。显示编号跨重复导入稳定延续，已有编号不重排、不作为内部主键；候选规则为各A/B/C/D族独立递增序号，实际计数器持久化，P0定稿。

组合记录 `id, kind=combination, length_ticks, notes, components, provenance`。components为按顺序排列的独立子素材快照及相对偏移；支持重复引用与嵌套，递归图不得成环。总长度等于实际子长度之和，音符与完整来源可追溯。原素材不删除。组合草稿是临时UI/请求数据，只有确认才新增库素材并提交一次撤销；取消/试听不得写入工程。

## 3. 固定时间轴与独立放置

候选工程域字段：`schema, project_id, grid_count, total_ticks, bpm, sources, melody_versions, materials, label_counters, placements, intensity_points, blank_regions, settings`。

放置记录 `id, material_id, base_material_snapshot, start_tick, length_ticks, emotion, emotion_variant`。基础快照不可被情绪结果覆盖，独立于素材库原件与其他使用；长度来自实际快照。一个组合放置一个外框、一个情绪，其内部来源边界仍可查询。

规则：起点为480 tick整数倍；范围位于固定总长内，不与其他放置或主动留白重叠。移动只改该放置起点，删除只删除该放置；其他放置和强度点不搬动，空缺显式保留。缩短总长若截断任一放置或有效留白则拒绝，并返回冲突区间；不自动裁切、压缩或拉伸。

画布宽度对应长度，中心强度为 `evaluate_curve(start_tick+length_ticks/2)`，厚度为UI常量。中点计算允许半tick评估，但不改变持久化整数时间；像素映射由共享前端处理。

## 4. 强度控制点与留白

`intensity_points=[{tick,level}]` 按tick严格递增，level有限且处于0–1；曲线覆盖0与total_ticks，插值规则由后端统一（候选为现有分段线性）。初始强度值不在产品规格中强行添加新选择，由P0给出一致默认。

控制点编辑与手绘轨迹简化输出同一格式。手绘过程为临时数据；结束验证、归一化后提交一次事务/撤销，取消不写入。改BPM、移动素材、试听、主题、滚动均不改强度点。

`blank_regions=[{id,start_tick,end_tick,kind=intentional}]` 为主动留白。未被放置或主动留白覆盖的补集是待补全空缺；后端返回精确gap区间及稳定操作目标，不依赖Canvas坐标。分块自身休止不是待补全空缺。

主动留白不得填入主旋律，可有克制伴奏/自然尾音。生成前存在待补全空缺时，返回可执行的补全/推荐/标留白提示；不能隐式填满。

## 5. 情绪变体与峰值保护

候选请求 `EmotionRequest(snapshot_version,placement_id,emotion,algorithm_version)`；结果含 `base_fingerprint, placement_id, notes, length_ticks, arrangement_hints, transformation, protection`。每次从该放置的基础快照计算，不从上一次变体继续变换。长度、基础身份、其他放置和素材库不变。

自动峰值计划记录 `peak_tick, state, placement_id, component_path, protected_range`。state区分已落位、待落位空缺、主动留白。峰值在B2时保护该基础B2情绪处理前的音高和节奏；组合内定位该子素材的对应四拍片段（短尾按实际片段），不恢复A2、不把保护扩展到其他使用。允许配器情绪变化，主动留白内不制造主旋律。

## 6. 连接计划与音乐处理

候选 `ConnectionPlan`：`id, snapshot_version, algorithm_version, original_splice_snapshot, decisions, protected_regions, melody, arrangement_hints`。

decision含 `type, left_placement_id, right_placement_id, reason, impact_ranges, available_window, original_notes, planned_notes`。类型包括 `natural_continuation,motivic_response,gradual_build,silence_entry,falling_resolution`，也允许显式 `none` 或无窗口时的轻量衔接。

先分别落实五类实际音乐处理，再决策；依据关系、情绪、强度趋势和时间。影响范围可较大，但不得移动/延长放置和总长，不破坏记忆保护、主题/乐句约束与主动留白。不引入主副歌标签，不以鼓填充充当默认连接。原拼接快照和选择原因持久可追溯，支持共用播放器对比试听。

## 7. 自动补全与建议方案

请求 `CompletionRequest(snapshot_version,target_gap_ids,mode,algorithm_version)`：选中gap时仅该处，否则全部gap。结果包含有效 `candidates` 和 `insufficient_reason`；至少两套实际音乐不同的有效候选才标为双方案，不能仅改ID/标题伪造差异。

候选含 `id, base_fingerprint, targets, placement_changes, connection_plan, score_reasons, audition_snapshot`。须考虑左右连接及整体重复程度，只操作待补全范围，不覆盖已有放置/主动留白、不改变总长。试听不写入；确认时校验当前快照与基线匹配，统一事务应用；自动补全也一次撤销恢复。缓存/过期候选不能自行应用。

## 8. 快照、生成与历史成品

`SnapshotVersion`候选含 `schema, content_fingerprint, edit_revision, request_id, producer_version`。content_fingerprint规范化全部音乐持久化数据，包括库、基础快照、放置位置、强度、留白、情绪、已接受连接/补全状态、BPM与仅主旋律设置；排除播放位置、选择/悬停、滚动、主题、UI缓存及未确认草稿。撤销回保存内容时hash应恢复一致。

revision/request身份用于并发门禁，不单独使内容变dirty。保存时还持久化已有成品元数据；“编辑已保存”和“编辑已生成”分开判断。

生成请求绑定不可变快照，结果带原snapshot_version、实际主体与音频长度、输出文件、计划/映射、日志详情。旧消息与过期结果不能覆盖新编辑或新任务状态；成品历史记录原输入，播放对象与所选成品ID分别管理。所选历史试听/导出不自动使用当前编辑。

保留整曲编配、MIDI/MMP与LMMS连续WAV/尾音；仅主旋律去伴奏且统一音色/力度，保留已经规划的旋律、情绪处理和连接。

## 9. 兼容、错误与预留接口

lead-backend负责v2路由、序列化与主流程接线。旧格式读取保留、成品文件逐格式检查可用性，旧工程不开放完整v2编辑，不自动迁移。播放器两平台 `play/status/pause/resume/close` 契约保持；新的共用播放对象由shared前端映射，后端无Tk依赖。

错误输出候选 `code,message,details,conflict_ranges,recovery_actions`：范围/重叠/过期快照失败不部分改写工程；异步失败恢复busy与历史；缺失源文件可使用已保存快照，缺失历史输出如实禁用对应操作。

哼唱和外部模型仅预留快照输入/输出provider边界，不引入依赖或网络接入。接口定稿、公共变更与版本兼容必须先更新本文并通知受影响角色。
