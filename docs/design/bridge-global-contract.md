# Bridge全曲分析与定位最小契约增量
STATUS=FROZEN
SPEC_REV=curve-workflow-v2-r3
CONTRACT_REV=curve-workflow-v2-r3-bridge-global1
BASE_SHA=88dca8cef8f97e908c7f3e4958cc0318c15c37be

仅补全曲分析、预测定位和公平搜索，不改UI/工程schema/来源体系/Bridge生成旋律算法或P6-P7保护门禁。服务版本与已有工程音乐版本分开；旧P5–P8对象按所属版本验证。F01/F05/F06保持独立任务，不混入本分支。

## 权威输入与流程
已验证BridgeRequest.base_project/base_notes为唯一音乐依据：来自实际CompletedCandidate.project或无空缺的当前排布，current_notes包含合法有效情绪结果及已有接受覆盖层。禁止只读library原件或历史猜当前音乐。先验证candidate/sourceclosure/targetcoverage/locks/blank/time；完整流程是基础候选→全曲分析一次→位置与全锁原子登记→生成Bridge且全READY→连接块→最终边界，不交换顺序。

## 版本与接口最小变化
新分析模块curve_phrase_analysis：analyze(request,should_cancel=None)->WholeScoreAnalysis，validate(request,analysis)->None（纯事实验证、不作曲、不渲染），window_features(analysis,range)->WindowGlobalFeatures。
新定位算法版本curve-bridge-global-v2，分析版本curve-phrase-analysis-v1，版本进入请求现有algorithm_version及search.analysis，不新增第二套Project。curve_bridges.make_request(...,*,algorithm_version='curve-bridge-v1')保持旧低层默认兼容；明确支持这两个算法。当前Controller.capture_bridge和完整recommendations调度显式global-v2，每套候选独立一次analyze，同一次decide后续每窗口复用同analysis。story_engine路由仍lead独占；old request仍旧算法，不自动升级或重跑旧音乐。旧search形状tested_windows/termination保留；global-v2 search精确tested_windows/termination/analysis/coverage，Plan现有search字段持久化，plan/request指纹自然绑定。没有UI字段变化。

## WholeScoreAnalysis精确形状
{schema:'emoblocks.whole-score-analysis.v1',algorithm_version:'curve-phrase-analysis-v1',base_fingerprint,layout_fingerprint,protection_fingerprint,total_ticks,occurrences,boundaries,phrases,motif_relations,trajectory,analysis_fingerprint}。
layout_fingerprint=curve_bridges.splice_fingerprint(total_ticks,request.base_notes)，protection_fingerprint=request.protection_summary.fingerprint，base_fingerprint与request相同。analysis_fingerprint=curve_project.digest('emoblocks.whole-score-analysis.v1',analysis去掉analysis_fingerprint)。digest沿既有domain+LF+canonical(JSON sortedcompact UTF8 finite)规则。只读输入不变，所有音乐时间整数tick，不转秒猜边界。

occurrences每项{id,placement_id,material_snapshot_id,component_path,start_tick,end_tick,note_ids,source_refs,emotion,source_phrase_ref}。每顶层放置一条，嵌套组合每leaf另条完整路径；相同素材复用也不同id/位置。id=digest('emoblocks.phrase-occurrence.v1',{placement_id,component_path})。范围取实际placement+component offsets不压时间；note_ids引用真实base_notes起音/支撑，与实际owner/accepted_parent_ref闭包一致，不重新生成源音。source_refs为去重排序[{source_id,track_id}]，没有来源时[]，不可借用同名合法Source。source_phrase_ref=null或{source_id,phrase_id,relative_start_tick}，仅真实来源线索，不当硬禁选规则。
boundaries每项{tick,confidence,evidence,occurrence_ids}；confidence0..1有限，evidence=[{kind,weight,details}]，kind限start/end/rest/attack/rhythm_cadence/contour_turn/source_hint/placement_edge，weight0..1/details有限JSON。至少综合当前休止、起音、时值和走向；每四拍仅非强制线索，不自动建句。start0/endtotal明确。不能在完整音符支撑中间伪造可切点。
phrases每项{id,start_tick,end_tick,note_ids,occurrence_ids,contour,rhythm,confidence}；id绑定analysis版本/base_fingerprint/range；contour音程整数列表、rhythm完整实际起音偏移及duration [{onset_tick,duration_tick}]。真实边界决定segments，允许不同长度及休止，任何遗漏/重复归属有明确范围规则。source hints不等于当前phrases。
motif_relations每项{left_phrase_id,right_phrase_id,relation,contour_similarity,rhythm_similarity,reason}；关系限repeat/variation/response/return/contrast，similarity0..1规则相似性，不声称音乐质量。至少非相邻乐句比较，排序按实际时间与id；重复/回应/回归考虑转调相对轮廓与节奏，休止不伪造notes。reason Error同形{code,message,details}。
trajectory精确{samples,segments,peaks,emotion_changes}。samples=[{tick,level}]来自实际无过冲插值；至少控制点与各occurrence/phrase中点及端点，有限level0..1。segments=[{start_tick,end_tick,start_level,end_level,signed_delta,slope}]，signed_delta=end-start，不以max-min当方向；slope每tick变化率，峰谷与相同峰最早tick记录。peaks=[{tick,level}]；emotion_changes=[{tick,from_emotion,to_emotion,placement_id}]按当前真实位置，不凭素材库情绪猜。

## 全曲关系实际进入定位
window_features精确{phrase_cut_cost,motif_preservation_cost,return_preparation,repetition_development,trajectory_alignment,global_gain,reason_codes}；所有值有限，理由对应analysis真实phrase/occurrence/relation IDs。预测收益以既有local评估加明确global_gain，并减真实完整乐句/主题损失和换写范围成本。窗口assessment.features追加global对象和analysis_fingerprint，reason code说明“预测收益”，不是已生成音频质量比较。局部大音程/对比不是自动缺陷；连续同情绪2–4块只线索；保留原音乐收益相近优先少改。长句内部仍可合法窗口，不用sourcephrase边界绝对封禁。
评分公式/权重及固定验收样例由算法只读评审补充后冻结，不能实现时猜常量。全局关系应至少在一个固定例改变最终定位，而不只改无效说明。

## 搜索覆盖与统一冲突选择
保留weighted interval DP/统一多窗口冲突选择，不按遇到顺序即占位。候选范围只现有合法完整音符/保护/解决区域边界，合法长句内部允许。公平排队：先各主要时间区域及乐句交界至少覆盖，再按预测价值/稳定tie顺序细化；每次合法/非法候选评估均算预算。相同音乐与版本确定排序，不根据request随机id改变评分。
coverage精确{regions,evaluated_regions,unevaluated_regions,evaluated_boundaries,unevaluated_boundaries,generated_candidates,selection_method,coverage_complete}；regions为按总长均匀最多8个实际时间范围（不足按实际非零tick分），evaluated/unevaluated与regions同结构；边界列表引用analysis.boundaries.tick，generated_candidates为去重候选数，selection_method='weighted-interval-dp-on-evaluated-candidates'。记录每region是否评估合法候选，不把被保护没窗口的区域假称已充分搜索。termination限EXHAUSTED/WINDOW_BUDGET/REGION_BUDGET/POLICY_NONE；coverage_complete仅全部实际候选枚举且无预算中止true。none+预算不足理由SEARCH_INCOMPLETE，不宣称整曲确定无需Bridge；none+完整且收益不足NO_PREDICTED_GAIN；none+无合法窗口NO_WRITABLE_WINDOW；取消抛CANCELLED不发布假成功，已有锁不清；过期由现request/session门禁拒绝。

## 持久化和独立门禁
analysis随proposal→Plan.search保存，锁在make_plan/Controller同事务不变；验证analysis包含真实输入指纹/实际owner/support/source/shape/hash/有限值/关系引用，searchcoverage与assessments实际窗口重算覆盖，不只自报bool。纯加载/保存/校验只认证持久数据，禁止重新decide/generate/analyze填缺失字段；旧算法search2字段走旧分支。缓存如使用只内存并绑定base+layout+protection+analysisversion，取消/失败不登记完成analysis，别的候选及撤销同内容新请求无授权复活。不得清Bridge/记忆/主题/手工锁或减完整跨界保护。公有音乐schema/Controller事务不改，后续P6/P7真实READY校验继续。

## 文件归属与验收
lead独占curve_bridges.py、curve_workflow.py、curve_recommendations.py、story_engine.py、契约/集成保存回归；算法仅curve_phrase_analysis.py新模块、curve_bridge_music.py定位/本地requestvalidator允许新版本（不改generate/emotion音乐）和tests/core/test_curve_phrase_analysis.py/test_curve_bridge_music.py。frontend只仓库外风险报告，不改UI/测试。verifier只冻结集成结果/契约，最多各5轮身份/HEAD/全文件前后指纹。
新增远主题局部同窗改变评分并固定定位差异、排列重排、多次重复独立位置、密集开头后段仍评估、长句内部合法窗口、原保护/留白/完整跨音不变、none/预算不足/取消/过期真实状态、确定复现、纯保存重开撤销无重新生成、完整推荐同候选试听应用。保存新旧对象混存兼容，旧schema/search读取不偷偷补analysis。
隔离固定样例存原拼接/旧定位/新定位、实际notes/seed/versions/reasons/ranges/hash，渲染须待F06模型lease释放再串行LMMS，音频设备另排队。真实约束、模型（本run无新模型）、渲染、设备、人耳/平台分开。backend-only/check_frontends/fulltest/diffcheck全部运行。人工听感未验不得称新定位更自然。


## Normative completion after algorithm read-only review

The following sections replace conflicting provisional occurrence IDs, ownership, peaks shape, scores, limits, queue, DP, and policy-none rules above. They are normative, not optional implementation guesses. Existing P5 object contract_rev remains curve-workflow-v2-r3-p5; the supplement is a service revision. No product implementation begins until independent contract PASS.

### 1. 版本、调用与恢复规则（M01、M08）

curve_bridges.make_request保持低层默认algorithm_version='curve-bridge-v1'，仅接受curve-bridge-v1和curve-
bridge-global-v2。

既有Controller.capture_bridge保留全部原参数，增加可选关键字参数：

algorithm_version='curve-bridge-global-v2'

当前UI及完整推荐调度使用默认global-v2。旧事务测试通过显式传入curve-bridge-v1执行，不放宽global-v2认证。
根据已存请求重建认证输入时，必须显式传入该请求原有版本，禁止套用当前默认值。

global-v2仅改变全曲分析、定位、搜索和选择。生成音乐继续使用原curve-bridge-v1规则、音乐种子公式及
generation.algorithm_version='curve-bridge-v1'；不得因planner版本变化改变同一音乐窗口的生成内容。

旧v1的Request、Proposal、Plan及两字段search保持原形状和字节语义。global-v2的search精确为：

{tested_windows, termination, analysis, coverage}

未知版本、字段缺失、额外字段、混用v1/v2形状均拒绝，不自动补充、迁移或重新选位。

### 2. 实际归属与分析对象（M02）

仅修改新WholeScoreAnalysis.occurrences的项形状，在草案字段上增加：

role: 'aggregate' | 'terminal'
owner_ref: OwnerRef
performance_id: string | null

OwnerRef精确为以下之一，既有音乐ParentRef不改变：

{kind:'placement', placement_id, component_path, material_snapshot_id}
{kind:'accepted_score', owner_id, component_path, material_snapshot_id:null}

归属必须由既有curve_bridges.parent_ref及对应权威performance_map解析：

• 普通放置的terminal对应实际叶组件完整路径；重复、嵌套复用分别登记。

• accepted音符的terminal按解析出的accepted owner、component_path、原performance_id分组。
  placement_id=null，不得按时间投射到当前placement。

• 普通terminal范围使用真实放置与累计组件偏移；accepted terminal范围使用其实际音符支撑包络。

• combination可保留一条aggregate及各terminal。aggregate的performance_id=null，音符集合仅为真实子归属集合
  的并集。

• 非组合放置仅建立terminal，禁止同时建立重复计数的root条目。

• 音符统计、密度、动机及来源比较只计terminal。每个实际base_notes.id必须恰好属于一个terminal。

• 缺父、歧义performance、重复音符归属或路径不一致返回SOURCE_CLOSURE_INVALID，不能采用历史note-ID扫描或时
  间邻近回退。

occurrence ID改为：

digest('emoblocks.phrase-occurrence.v1',
       {role,owner_ref,performance_id,start_tick,end_tick})

source_refs来自真实来源闭包，去重后按source_id、track_id排序；来源为null时使用[]。source_phrase_ref仅保
存可独立验证的来源乐句事实，否则为null。库名称、情绪标签和素材ID不能冒充来源乐句。

accepted音符的情绪、调性依据必须沿逻辑音符→performance_map→实际emitted音符→原Score旋律规则项读取。缺少唯
一归属时拒绝；不得从同时间的旧placement猜测。整个分析不改变原音符、来源、演奏身份或保护。

### 3. 有界分析、乐句及动机公式（M03）

global-v2固定以下分析上限，不新增公开可调参数：

 项目                                        上限
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━
 实际主旋律音符                              4096
─────────────────────────────────  ───────────────
 顶层放置                                     512
─────────────────────────────────  ───────────────
 occurrences总数 / terminal数         1536 / 1024
─────────────────────────────────  ───────────────
 分析端点                                    2048
─────────────────────────────────  ───────────────
 强度控制点 / trajectory samples       512 / 8192
─────────────────────────────────  ───────────────
 phrases                                      128
─────────────────────────────────  ───────────────
 候选范围全集                              262144
─────────────────────────────────  ───────────────
 analysis canonical JSON            16MiB、深度64

组合深度沿用既有16层门禁。超限返回结构化ANALYSIS_LIMIT；候选全集超限返回SEARCH_LIMIT。不得截断后声明分析
完整或返回成功none。取消返回CANCELLED，不登记完成analysis、不解除保护。

保留既有请求预算：默认max_window_tests=128，最高2048；其他max_windows/max_window_blocks/max_notes的默认
值及上限不变。

端点与边界。 端点集合E为以下整数tick的去重排序集合：

• 0、总长；
• 实际音符起点与完整释放点；
• 实际placement/叶组件边缘；
• resolved ranges、名义保护、完整音符支撑及主动留白的边缘；
• 可验证来源乐句起点。

删除位于任一实际音符完整支撑内部的端点。不得额外加入四拍网格作为自动句界。

每个端点的evidence按以下固定顺序登记，同kind最多一项：

 kind              weight
━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 start/end         对应0/总长为1
────────────────  ─────────────────────────────────────────────────────────────────────
 rest              最大真实无音符区间两端：.60*min(1,gap_ticks/480)
────────────────  ─────────────────────────────────────────────────────────────────────
 attack            实际起音为.10
────────────────  ─────────────────────────────────────────────────────────────────────
 rhythm_cadence    前音释放点：.20*min(1,d_prev/(2*median(last≤3 durations)))
────────────────  ─────────────────────────────────────────────────────────────────────
 contour_turn      连续两个非零音程反向处的起音：.20
────────────────  ─────────────────────────────────────────────────────────────────────
 source_hint       terminal具有真实source_phrase_ref且relative_start_tick=0的起点：.10
────────────────  ─────────────────────────────────────────────────────────────────────
 placement_edge    实际放置/叶组件边缘：.10

confidence=min(1,sum(weight))，保留8位小数。重复同tick起音或来源提示不累加同kind权重。

phrases由0、总长及内部confidence>=.60的边界依次分段。音符按起点唯一归属；上述端点规则保证不裁完整支撑。
空休止段可登记，但不参与动机比较。rhythm保存完整相对起点及原时值；contour保存实际连续有符号半音音程；
phrase confidence取两端confidence较小值。

动机。 至少3个实际音符的phrase为eligible。全部eligible无序对均比较，最多8128对，不抽样。按时间排序后保存
唯一left/right。

每个phrase取16个等序位样本：

q(k,m)=floor(k*(m-1)/15), k=0..15

轮廓样本取音程序列，夹至[-12,12]：

CS = 1 - mean(min(1, abs(cA-cB)/12))

节奏样本取音符序列，将相对起点、时值除以该phrase长度：

shape = 1 - min(1, 2*mean(abs(onsetA-onsetB)+abs(durationA-durationB)))
RS = .75*shape + .25*min(note_countA,note_countB)/max(note_countA,note_countB)

这些归一化只用于特征比较，不修改音乐tick。

关系按以下优先级唯一判定：

1. return：CS、RS均≥.85；两句之间至少隔一个eligible句；其中至少一个中间eligible句与left的CS或RS<.60。
2. repeat：完整contour、完整rhythm及phrase长度相同。
3. variation：CS、RS均≥.75。
4. response：两句在非空乐句序列中相邻，反转right音程符号后CS≥.85，且RS≥.75。
5. 其余为contrast。

保存全部比较，包括contrast。reason引用真实phrase及数值，不评价听感。

由repeat/variation/return且min(CS,RS)>=.75的边组成连通分量。每个分量最早phrase为软动机anchor，salience为
其最大关联min(CS,RS)。这不是新增硬保护，不替代记忆、主题或手工锁。

强度轨迹。 使用现有无过冲插值函数及原控制点，sample tick取E、原控制点、occurrence/phrase端点与整数中点的
并集。不得把新增sample当控制点重新插值。

segments记录相邻samples，signed_delta=end_level-start_level，slope=signed_delta/tick_span。peaks项增补
kind:'peak'|'trough'；依据原控制点的相邻level run判定，平台取最早tick，端点仅在单侧严格极值时登记，常量
曲线无极值。emotion_changes记录真实放置控制状态变化，不用于改写音符归属。

### 4. 窗口收益与阈值（M04）

先执行原硬合法性门禁。完整支撑、记忆、主题、手工、bridge及主动留白规则不因任何收益放宽。

对窗口W=[a,b)，使用原实际音乐局部特征：

roughness = mean(max(0,abs(interval)-7)/17)
rhythm = mean(abs(log2(next_duration/duration)))
key_changes = 相邻实际音符调性变化比例
edge = 两侧已有实际邻音的max(0,abs(leap)-7)/17平均值
C = (.65*roughness + .08*rhythm + .15*key_changes)
    * (窗口内实际发声时值之和/1920) + .25*edge
H = .13 + .01*ceil((b-a)/1920)
L = .8*C - H

缺少音程对、节奏对或某侧实际邻音时，对应项为0。调性按第2条实际归属读取；缺少调性元数据时，使用既有纯调性
推断作用于该实际owner音符，不能读取旧素材端点。

设ρ(f,W)为窗口内完整包含的f音符时值之和除以f总发声时值：

phrase_cut_cost =
  .5*(a严格位于非空phrase内部的指示值
      + b严格位于非空phrase内部的指示值)

motif_preservation_cost =
  max(软anchor.salience * ρ(anchor,W))

return_preparation取符合以下条件的return关系最大min(CS,RS)：b等于return目标phrase起点，且W含目标之前最近
非空phrase的至少一个实际音符。没有则为0。

repetition_development取repeat/variation关系的最大：

min(CS,RS) * max(0,2*ρ(right,W)-1)

right必须不是软anchor。没有则为0。

expected_sign在有return_preparation时取最早对应目标完整contour之和的符号，否则取W内同phrase相邻音程之和
的符号：

trajectory_alignment =
  expected_sign * clamp((I(b)-I(a))/.25,-1,1)
  * max(return_preparation,repetition_development)

global_gain =
  .40*return_preparation
  + .25*repetition_development
  + .20*trajectory_alignment
  - .30*phrase_cut_cost
  - .45*motif_preservation_cost

benefit = round8(L + global_gain)
baseline_score = round8(1-C)
bridge_score = round8(1-(.2*C+H-global_gain))

仅benefit>.03进入选择。长度、同情绪、强度变化本身不产生global正收益。

global-v2的intensity_trend为I(b)-I(a)；v1不改。features.global按冻结WindowGlobalFeatures形状保存全部值，
并绑定analysis_fingerprint。reason_codes使用{code,message,details}，引用对应实际关系及范围，明确为生成前
预测。

### 5. 公平候选全集和预算语义（M05）

U为E中全部去重[a,b)：

• a<b；
• 沿用原2<=ceil((b-a)/1920)<=max_window_blocks；
• 范围完全落在既有resolved范围扣除名义保护与完整保护音符支撑后的可写区域。

保留原blank mask门禁；不得将“窗口含blank”擅自升级为整窗禁止，也不得在blank内生成音符。U是有限范围全集，
不是已生成音乐池。

regions按总长均分，R=min(8,total_ticks)：

region_i=[floor(i*T/R),floor((i+1)*T/R))

窗口按start所属region归类。

构造固定队列：

1. 每个有候选的region取一个代表，排序键为距region中点的start距离、窗口长度、start、end；按region时间顺序
   入队。

2. 内部confidence≥.60的phrase边界，按递归中位数广度优先顺序访问，偶数取较早中位数、同层左先右。每个边界
   取触及该tick的最短候选；平局取窗口中心距离、start、end。

3. 上述代表首次出现去重后为Qseed。

4. 其余U按以下粗优先级降序排列，再按较短窗口、start、end：

priority = confidence(a)+confidence(b)
           + return_strength_at_b
           - .01*ceil((b-a)/1920)

return_strength_at_b仅取目标起点为b的return关系最大min(CS,RS)。建立队列时不执行未计数的局部音乐评估。

每次取出窗口均计一次tested_windows，包括实际合法性失败；失败assessment保留范围及结构化原因，分数为null。
assessments必须恰为队列前缀，不能丢弃失败以补用预算。

终止规则：

• 耗尽U：EXHAUSTED；
• 预算耗尽且Qseed未完成：REGION_BUDGET；
• Qseed完成、U未完成：WINDOW_BUDGET。

generated_candidates=|U|。evaluated_regions仅表示实际评估过合法窗口的start区域；evaluated_boundaries仅表
示实际合法窗口触及的上述phrase边界。其余必须如实列入unevaluated。保护导致没有合法窗口的region不冒称已覆
盖。

coverage_complete=true仅当U全部完成评估且termination=EXHAUSTED；它表示有限范围全集穷尽，不表示听感、生成
质量或所有区域可写。

显式policy none不运行分析或DP：analysis=null、tested_windows=0、generated_candidates=0、evaluated列表为
空、coverage_complete=false、termination=POLICY_NONE。这是analysis唯一允许null的分支。

无选中窗口时：

• 非完整搜索：SEARCH_INCOMPLETE；
• 完整搜索无合法窗口：NO_WRITABLE_WINDOW；
• 完整搜索有合法窗口但无正阈值收益：NO_PREDICTED_GAIN。

部分搜索仍可选中已评估窗口，但必须保留不完整标记，不宣称全曲最优。

### 6. 相邻代价DP（M06）

仅使用实际评估合法且benefit>.03的候选。按end、start排序，令：

u_i = round(benefit_i * 100000000)
J = 35000000

D(k,i)表示恰选k个窗口且最后为i的最佳状态：

D(1,i)=u_i

D(k,i)=u_i + max(
  D(k-1,j) - J*[end_j == start_i]
  for j with end_j <= start_i
)

不存在的状态为负无穷，不能初始化成0。必须分别维护end_j<start_i和end_j==start_i前驱；不得以单个prefix最佳
路径替代末端相关状态。

最终在空集合收益0及所有k<=max_windows的D中选择。平局依次取：较少窗口、较少改写总tick、按时间排序的范围序
列字典序较小者。请求UUID、计划ID、标签及来源ID不得作为音乐选择tie依据。实现上限为O(K*M*log M)，
M≤max_window_tests。

选定后统一构造现有joint endpoints，再由backend原子登记全部范围锁。不得逐窗口先占锁或通过改变生成音乐解决
选择冲突。

必须验收固定反例：

A=[0,3840), benefit=.50
B=[1920,5760), benefit=.60
C=[5760,9600), benefit=.50
max_windows=2, adjacent_penalty=.35

应选A+C，收益1.00；不得选B+C，收益.75。

### 7. 一次分析与纯认证（M07）

每个当前候选的auto决定过程成功分析一次，窗口复用同一analysis。分析完成前不得发布完整analysis或成功none；
取消、异常不解除已有锁。

validate(request,analysis)、Plan/coverage认证、保存及打开：

• 不调用analyze/decide/generate；
• 不补字段、不重新发布Proposal、不更改选中范围；
• 通过有界纯算术核对实际归属、来源、音符、边界权重、分句、全部动机关系、轨迹、指纹；
• 核对U、固定队列前缀、计数、覆盖及已存assessment公式；
• 对已存assessment执行第6条算术证明，比较已存选择；不生成未评估音乐，不修复错误计划。

允许复用无副作用的底层事实计算函数，不允许以调用决策入口代替独立认证。

缓存仅限当前纯验证操作内，并在实际输入认证后绑定分析版本、base/layout/protection/analysis指纹。缓存不得
赋予请求授权，不得使撤销同内容、旧token或取消请求恢复有效。

当前实际notes与所属请求、保护、父闭包任何不一致均拒绝。保护先于评分；失败保留原锁。

### 8. 固定数据验收及证据边界（M04、M05、M08）

远主题对照使用总长19200，五个3840tick放置，start分别为0、3840、7680、11520、15360。每段三个音符，局部起
点0、1200、2400，时值均960；C大调、calm、强度常量.25。

P0：A版 [60,64,67]；X版 [84,72,60]
P1：[72,60,48]
P2：[60,62,64]
P3：[60,64,67]
P4：[52,40,28]

固定保护范围为[0,7680)及[11520,19200)，完整支撑与保护指纹分别从实际输入重建。唯一可写区域为
[7680,11520)。无主动留白。参数固定seed31、max_windows1、max_window_blocks2、max_window_tests2048。

A/X仅远处P0音高不同；目标窗口、局部音符、两侧实际邻音、调性、强度、可写范围相同。两版都通过真实Source/
Material/placement构造和现有request认证，禁止直接篡改base_notes绕闭包。

按上述公式，完整目标窗口预期：

A：return_preparation=1，
   repetition_development=161/192 (0.8385416666666666)，
   benefit=.48904718

X：return_preparation=0，
   motif_preservation_cost=161/192 (0.8385416666666666)，
   benefit=-.49793199

验收需实际枚举并认证全部有限候选：A选[7680,11520)，X为完整搜索none；旧v1两版均保持原局部决定。这里的数值
是公式推导，尚不是新provider运行结果。

另外必须执行：

• 15360tick、预算128的固定输入：有合法候选的八个region均在Qseed优先访问，不能只评估开头480tick。
• request/plan UUID变化及输入列表重排不改变音乐评分和范围选择。
• 重复、嵌套、accepted owner与普通placement同时存在时，terminal统计不重复。
• 长句内部合法窗口、名义休止、跨界完整音符、手工bridge及原保护门禁保持。
• v1/v2混存纯重开，不调用决策或生成；缺analysis、伪coverage、换父归属及未知版本均拒绝。
• 取消、预算不足、过期结果及锁失败保留原保护，不能伪装none。

固定证据保存实际notes、来源、保护、seed、版本、assessments、队列覆盖、选择及差异。旧DP与开头偏置收据只作
为确定性算法反例；新定位不据此声称音乐更自然。


## Exact arithmetic vector (contract review R1 correction)

The existing 16-sample q rule remains unchanged. For contours [4,3] and [2,2], the first interval is sampled 15 times and the second once: CS=1-(15*2+1)/(16*12)=161/192; RS=1. C=5/136, H=15/100, L=(4/5)*(5/136)-15/100. A: L+40/100+(25/100)*(161/192), round8=0.48904718. X: L-(45/100)*(161/192), round8=-0.49793199. These are reproducible arithmetic expectations; complete finite-window enumeration and actual provider-selected/none outcomes remain mandatory IMPLEMENTATION tests, not contract-review execution claims.
