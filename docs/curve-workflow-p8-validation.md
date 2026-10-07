# P8 综合验收矩阵与运行记录

SPEC_REV=curve-workflow-v2-r3
CONTRACT_REV=curve-workflow-v2-r3-p7-runtime1
RUN_ID=curve-v2-p8-20261007-492036f5
BASE_SHA=c47c5dca9c14e84216cbc9fce904cf0f0d611e85
状态：本机实施自查完成，等待第3轮实施独立验收；矩阵及定向修复契约第2轮独立PASS（不代表实施验收）。P8只验证并定向修复已有工作流，不扩展产品。

## 基线与证据门禁

P7实施TASK_ID=P7-IMPLEMENTATION、ROUND=4、VERDICT=PASS；RUN_ID=curve-v2-p7-20261007-345861bc。受检HEAD等于本轮BASE_SHA，209文件检查前后及本轮现场指纹均为906de19d0761326c30315c1c679abbead880c4e471dfbe6d73f21f063ee8990b，完整manifest逐项一致。真实P7-final-receipt、P7-R4-review和pane结果在对应仓库外运行目录。契约PASS和agent空闲不作为实施PASS。

启动基线时集成目录和两个worker均干净，交付已集成，实际源码字节一致；四角色Python导入各自目录，复用原解释器。不删除历史或覆盖修改。本轮产物位置为本机EmoBlocks/dev-runs/<RUN_ID>，动态映射、矩阵JSON、音频、截图、工程副本和日志均在仓库外。

服务版本runtime1与音乐对象p7分开；P0/P23/P4/P5/P6旧对象按原版读取。验收本身不升级数据格式。涉及公共接口、数据含义、音乐规则或输出策略的修复，必须先独立检查具体契约增量，不放宽保护和资源认证。

## 每条证据的字段与状态

每条完整记录包含：id、场景、预期、输入文件/生成配方和SHA256/输入指纹、HEAD/源码指纹、操作系统、Python/Tk/LMMS版本、执行方式、实际结果、证据路径、状态、缺陷负责人。矩阵JSON保留各字段，不用汇总表代替具体记录。

状态只有PASS / FAIL / NOT_TESTED / BLOCKED。证据类别分别为自动约束、程序化Tk、真实窗口视觉、物理鼠标/触控板/键盘、实际渲染、设备播放、人工音乐听感、Mac实机、Windows实机。自动驱动实际窗口也不算人实际使用触控板；同一场景可有多条不同类别记录。

环境基线：macOS 26.6.2 arm64；既有Python 3.11.16，Tk/Tcl 9.0；LMMS 1.3.0-alpha.2、Qt 5.15.19。doctor及设备枚举已记录，未改默认设备、权限或电源设置。目标Windows及其软件版本未采集，不以本机适配器模拟填写。

输入索引：I1=P7隔离fixed-input.mid（SHA256 eb7a88ef1285c6e33ca379447efa67243114b4c4e0fd14a88ce13abf96eb8801）；I2=仓库已有MIDI/MMP样例（执行前逐项hash）；I3=本轮隔离配方/快照（记录精确tick、seed和算法版）；I4=P7已认证ready/accepted/LOCAL副本（只读原件并hash）；I5=partner在目标机器复制后复核hash的本地交接材料。旧证据仅作继承，不能改写为本轮新执行。

## 检查矩阵草案

下列未开始项目均NOT_TESTED，负责人不是通过结论。最终结果与证据在每行ID的JSON记录中。

| ID | 场景与预期 | 输入 | 类别 | 负责人 |
| --- | --- | --- | --- | --- |
| PRE-01 | P7明确实施PASS、HEAD及完整前后指纹匹配 | I4 | 自动约束 | lead |
| FLOW-01 | 真实公开入口导入MIDI及MMP，分块/按句或块生成，不自动填作品 | I1/I2 | 程序化Tk、真实窗口 | frontend/lead |
| FLOW-02 | 全空缺：补全→锁桥→READY→连接→边界→真实试听→确认→保存重开→导出 | I1/I3 | 自动、Tk、实际渲染 | lead |
| FLOW-03 | 单目标空缺：精确补240tick，其他空缺保留，局部应用且正式导出拒绝 | I3 | 自动、Tk、实际渲染 | lead |
| FLOW-04 | 无空缺直接真实排布，不伪造P4任务 | I3 | 自动、实际渲染 | lead |
| FLOW-05 | 自动桥、手动桥、显式none，位置即锁，所有结果逐项READY | I3 | 自动 | music/lead |
| FLOW-06 | 没有合法连接空间或无需边界处理：明确理由，保音乐 | I3 | 自动、实际渲染 | music |
| FLOW-07 | 嵌套组合、整句、短尾、跨界长音，独立演奏与来源保持 | I2/I3 | 自动、Tk | music/frontend |
| FLOW-08 | 主动留白、内部休止、记忆跨界保护不被填主旋律 | I3 | 自动、实际渲染 | music/lead |
| FLOW-09 | 两套实际不同、最终去重、不足两套如实说明 | I1/I3 | 自动、实际渲染 | music/lead |
| FLOW-10 | 完整编配/仅主旋律同规划旋律，试听、应用、导出同谱同模式 | I1/I4 | 自动、Tk、实际渲染 | lead/frontend |
| FLOW-11 | 取消、重试、编辑/undo同内容、迟到/重复回调不抢播或部分应用 | I3 | 自动、Tk | lead/frontend |
| FLOW-12 | 一次undo全恢复，redo不重新生成；保存读取纯数据；旧工程只读历史可用 | I3/I4 | 自动、Tk | lead/frontend |
| OUT-01 | 独立解析真实MIDI音高/时间/时值/力度/tempo/meter/channel/program及同tick顺序 | I1/I3 | 自动、实际输出 | lead |
| OUT-02 | 实际MMP主音高、mute/solo、路由、循环/效果/自动化/音符逐项核对 | I1/I3 | 自动、实际输出 | lead |
| OUT-03 | 采样缺失/空/错误同名拒绝；合法相同内容副本允许；列依赖和版本 | I3 | 自动、实际输出 | lead |
| OUT-04 | MMP资源路径在目标平台真正解析，不以basename或放宽认证修复 | I5 | 自动审查、Windows实机 | lead/frontend |
| OUT-05 | 实际WAV完整PCM、帧数/声道/采样率/有效声音；截断/静音反例 | I1/I3 | 自动、实际渲染 | lead |
| OUT-06 | 峰值、削波、末尾包络和固定1秒尾音风险实测，指标不作听感PASS | I3 | 实际渲染、人工听感 | lead/music |
| OUT-07 | 精确tick不可表达明确OUTPUT_TIME_UNREPRESENTABLE，音乐保留 | I3 | 自动、Tk | lead |
| OUT-08 | 各格式独立可用；MMP资源失效不禁用有效WAV；安全写入和中文/空格路径 | I3 | 自动、实际输出 | lead |
| EXT-01 | 既有LMMS实际GUI打开MMP并检查乐谱/时间/资源，不以CLI渲染代替GUI打开 | I3 | 真实窗口、Mac实机 | frontend/lead |
| EXT-02 | 可用MIDI/WAV软件实际打开，记录软件版本及音符/时间 | I3 | 真实窗口、Mac实机 | frontend/lead |
| VIS-01 | 双主题×1020×700/1280×800/1440×900×来源展开/折叠实际窗口截图 | I3/I4 | 真实窗口视觉 | frontend |
| VIS-02 | 多素材、长中英文、长路径；统一卡、长句展开，关键按钮可达 | I3 | 真实窗口视觉、Tk | frontend |
| VIS-03 | 选择/hover/focus/disabled/error/busy清楚，正文AA，常驻关键状态 | I3 | 真实窗口视觉、自动诊断 | frontend |
| VIS-04 | 单画布，bridge/连接/记忆可辨，曲线与坐标清楚，无右栏BPM/情绪涂色画笔/第二时间轴（保留强度手绘） | I3/I4 | 真实窗口视觉、Tk | frontend |
| VIS-05 | 缩放/滚动/主题切换不改工程、undo、播放或文件，不留旧资源 | I3 | Tk、真实窗口视觉 | frontend |
| MAC-01 | 实体纵/横滚动、双指、滚动后拖放及控制点命中 | I3 | 物理输入、Mac实机 | user/frontend |
| MAC-02 | 实体左右组合、确认/取消、拖入/移动/删除/Esc | I3 | 物理输入、Mac实机 | user/frontend |
| MAC-03 | Delete/Backspace、Command及焦点、原生下拉/焦点说明 | I3 | 物理输入、Mac实机 | user/frontend |
| MAC-04 | 共享播放器暂停/恢复/停止/重播/切换，不自动播放 | I3/I4 | 程序化Tk、设备、物理输入 | lead/frontend/user |
| DEV-01 | 当前内置扬声器真实可用性/通道/采样率与串行播放，记录设备 | I3 | 设备播放、Mac实机 | lead |
| DEV-02 | 实际可用耳机/蓝牙/外接；无设备则NOT_TESTED，不切默认设备 | I3 | 设备播放、Mac实机 | user/lead |
| WIN-100 | Windows实机100%缩放：字体/中文/菜单/焦点/三尺寸 | I5 | Windows实机 | partner |
| WIN-125 | Windows实机125%同矩阵 | I5 | Windows实机 | partner |
| WIN-150 | Windows实机150%同矩阵 | I5 | Windows实机 | partner |
| WIN-INPUT | 滚轮、拖放、Delete/Ctrl、命中与取消 | I5 | 物理输入、Windows实机 | partner |
| WIN-AUDIO | 播放/暂停/重播及实际设备错误 | I5 | 设备播放、Windows实机 | partner |
| WIN-FILE | Unicode/空格路径，保存重开、三格式导出、目标LMMS资源实际解析 | I5 | Windows实机、实际输出 | partner |
| MUS-01 | 相近素材自然延续 | I3 | 固定对照、实际渲染、人工听感 | music/user |
| MUS-02 | 同动机重复与变化 | I3 | 固定对照、实际渲染、人工听感 | music/user |
| MUS-03 | 差异较大素材交接 | I3 | 固定对照、实际渲染、人工听感 | music/user |
| MUS-04 | 强度上升与下降 | I3 | 固定对照、实际渲染、人工听感 | music/user |
| MUS-05 | 句尾休止、弱起、主动留白 | I3 | 固定对照、实际渲染、人工听感 | music/user |
| MUS-06 | 记忆块附近及跨界音 | I3 | 固定对照、实际渲染、人工听感 | music/user |
| MUS-07 | 2/3/4块或更长bridge发展与入口 | I3 | 固定对照、实际渲染、人工听感 | music/user |
| MUS-08 | 无合法连接空间、阶段无变化如实记录 | I3 | 固定对照、实际渲染、人工听感 | music/user |
| MUS-09 | 短尾、不足一拍/精确短空缺 | I3 | 固定对照、实际渲染、人工听感 | music/user |
| PERF-01 | 多素材滚动/选择/拖放：记录规模、实际耗时与资源 | I3 | 程序化Tk、真实窗口 | frontend |
| PERF-02 | 长轴、大量控制点，坐标及响应；不省校验 | I3 | 程序化Tk、真实窗口 | frontend/lead |
| PERF-03 | 多轮推荐/接受/undo/redo与已接受继续生成，来源/文件增长 | I3/I4 | 自动、实际渲染 | lead |
| PERF-04 | 大工程保存/重开：大小/耗时/内存；先基线再讨论预算 | I4 | 自动、程序化Tk | lead |
| PERF-05 | 取消/失败恢复、渲染串行队列/重复点击；缓存不认过期文件/结果 | I3 | 自动、Tk、实际渲染 | lead/frontend |

## 评审、缺陷与冻结

先算法和前端只读补充矩阵，由lead整合，再交verifier检查覆盖。此时不派功能实现。所有复现先记录输入/预期/实际/证据，再分配文件；纯样式修复须实际截图，不加镜像实现测试。渲染和设备串行，GUI只一个角色占用。

本轮独立检查累计最多5轮；覆盖评审、必要契约增量和实现验收分别注明TASK_ID但保留累计序号，不重置。冻结指纹包含tracked、未忽略untracked及删除状态；运行目录不进入指纹。验收期间不写集成目录；结论必须匹配HEAD及完整前后指纹。最终收据只写仓库外。

P8_READY要求必需实证齐全；P8_PARTIAL用于可做工作完成但实机/物理/人工缺证据；前置失败或实际阻塞为BLOCKED。不把测试、设备流或文档当人工PASS，不自动推送/发布。

## 双角色评审整合与执行叶

前端只读评审指出并修正矩阵的以下问题：Windows目标环境保持null，不再继承Mac执行环境；每个混合类别按独立证据叶记录，不用程序化Tk通过覆盖人手、视觉或设备结果；VIS-01细分2主题×3尺寸×2来源栏状态共12叶；Windows相同组合再乘100/125/150%共36叶。每叶记录真实执行者、时间、环境和required_for_P8_READY。

矩阵整合JSON以fixture_registry绑定每行实际入口、配方、预期不变量、资源时隙和指纹要求，不把三个通用样例贴到每一行。I3尚未执行的配方不伪造SHA；执行前建立真实文件/工程/请求Ref，缺失保持NOT_TESTED。I4保留原RUN/HEAD/类别的继承标签，不能写成P8新执行。正式run.py初始化、旧工程入口、原生菜单、逐模式逐格式、阶段互斥、暂存自动保存、回调故障及短保护标识另列16项UI补充。当前共70项父记录，参数和证据叶独立保存。

素材性能配方固定1/30/200素材、8/64/256格、2/128/1024控制点；先测实际p50/p95/max、heartbeat、RSS、文件/来源事实大小，再报告预算，不凭空赋予流畅阈值。资源时隙为READ_ONLY、GUI、RENDER_AUDIO；GUI与完整Tk套件不同时占用，真实渲染和设备流严格串行。

本轮已执行的基线校准：后端588项PASS；真实公开后端Facade对高强度crisis输入完成两套实际音乐不同的候选，4份对比/最终连续LMMS资产逐音符MIDI/MMP核对及完整PCM读取PASS，含12个鼓资源实例。此项是新实际渲染和文件检查，尚无公开窗口操作或人工听感结论。原音符/请求、乐谱/资源摘要、秒数、峰值/RMS/削波计数与末尾窗口能量保存于隔离actual-baseline及independent-output-audit.json。

已复现缺陷登记：
- D-OUTPUT-RESOURCE：含鼓轨MMP绝对本机资源路径不可移植。修改输出策略前需独立契约增量PASS；目标Windows仍需真正解析。
- D-OUTPUT-FORMAT：隔离同名错误采样测试中，required_formats仅MMP时认证错误接受，同时MIDI/MMP时拒绝；有效WAV仍接受。预期逐格式独立认证。修复前为FAIL。
- D-JOB-START：前端无窗口逻辑探针注入Thread.start异常后，留1个busy job及仍有效token；需要实际映射窗口复现和回归。
- 历史选择mode与按钮状态、短尾保护文字、WindowsDPI目前是源码风险候选，不冒充实际视觉或实机缺陷结论。

算法只读评审的MUS-01–09配方已接入矩阵：18个有限可试听子场景，各最多3个固定seed尝试；另设不足10tick的精确数据检查及六普通旋律/六情绪、五连接/五边界、记忆完整支撑和失败审计检查。不能为凑出差异强行启用bridge/连接；没有变化记录none及原因。真实同时有bridge与连接且端点不同的案例仍需有限搜索，找不到保持具体覆盖缺项，不伪造。

D-AUDITION-OWNERSHIP已由lead公开导入/组合/放置及真实P5/P6 none服务复现：3840tick长音分成两个独立1920tick组合子实例，中性试听合成1起音，真实Final布局保留2起音。需修复试听发声归属，并以版本化试听输出身份记录真正发声事件；不更改FinalScore音乐规则。文件有效、设备流成功与人工音乐反馈仍分别记录。

第1轮矩阵独立FAIL已核对身份、HEAD和211文件完整前后指纹相等：d06bd80de230c8e3112bc7e50c030fa27cdea1bbb00c207b27dbc0ba9a3d1ca5。具体修正为70父项的155独立证据叶、VIS12和Windows36独立参数叶；每叶拥有ID/category/required/status/executor/time/env/inputfp/head/evidence/actual/inheritance。父项只有全部required叶PASS才PASS，任一FAIL优先FAIL，否则BLOCKED或NOT_TESTED；不会以设备/程序化Tk替代人手/听感。第1轮JSON已封存，轮数不重置。

新增D-RESTORE-ORDER：原P7收据local-auto已接受大工程127707456字节在本轮纯恢复失败，真实诊断仅同priority的segment归属受集合顺序影响。P7独立认证的accepted-current工程55970981字节在本轮正常load/save/reopen/capture-cancel通过（约7.63/6.68/7.32/6.75秒，进程累计峰值RSS约1.44GB）；不能把它替代大工程反例。兼容修复先纳入15.4独立契约，不改原件/不删除来源保护、不用新hash重签旧请求。

第2轮TASK_ID=P8-MATRIX-AND-REPAIR-CONTRACT：MATRIX_VERDICT=PASS、CONTRACT_VERDICT=PASS，总PASS；HEAD=23c03815d7307c3f6393fb622f24295c0accc2d8、前后指纹ce0139373410498ef58554984eff341c41dc3fea7ce496da310bbe78c9adbd95，本轮现场重算一致。15节标FROZEN后安全同步原worktree，才派定向实现。服务runtime1与音乐native p7仍不变，输出profile和布局algorithm_version分别版本化。

## P8定向实施与本机实证（等待最终独立复核）

输出补充OUTPUT_CONTRACT_REV=curve-workflow-v2-r3-p8-output1、布局兼容补充LAYOUT_COMPAT_REV=curve-workflow-v2-r3-p8-layout1均沿用第2轮FROZEN。服务runtime1与各历史音乐native版本不改。本机实现阶段代码提交依次46a7c82、1d88e6c（集成算法0a02fa9）、ed7a039、a22bd4e、82eb99f、a29fe95、cb9c7db、14ac9ab；完整最终HEAD/指纹以仓库外freeze和最终收据为准，不在通过后改动此文档。

已实现的后端修复：逐格式实际认证，MMP单独检查也验证采样；新curve-final-lmms-v2输出使用严格data:/samples/drums/ URI及官方内容固定基准；LMMS子进程使用本次私有config和已认证data根，前后重新认证，不改用户配置。旧curve-final-lmms-v1保持原绑定与合法相同内容副本规则，不自动迁移。Controller.history_output_state按明确所选模式返回三格式独立状态，缺一个不关闭其他有效格式。实际导出的临时完整副本须匹配登记SHA256才原子替换，源变更/复制失败保留原目标。

中性素材试听升级curve-neutral-lmms-v2：组合的独立使用不合成长音，只有同一次真实演奏的连续原音符切片连接，保留首片力度；指纹对应实际发声。算法边界provider只新增布局版本识别，五类音乐规则未重写。

旧curve-boundary-v1存档通过真实来源、最高优先级及全局无环顺序证明纯恢复，完整重放比对每个layout字段；不是忽略metadata或重签旧请求。新curve-boundary-v2-deterministic-layout采用冻结的确定性顺序。新推荐任务在私有运行上下文绑定该算法版本，迟到旧算法结果不能作为新任务应用；旧事实纯读取仍接受。该门禁落实15.4，不新增音乐schema或接口。

本机专项9项通过，覆盖旧布局伪造/全局循环/跨进程hashseed、格式隔离、工厂内容与严格URI、缓存资产profile、源消失、同长度换源原目标保护、所选模式查询纯性、新任务旧布局结果拒绝。后端605项通过（542.607秒；多角色并发环境的实际耗时，不称流畅或性能预算）。前端集成后完整命令和独立验收另在最终记录中列出。早期失败日志保留，不能用它们或基线测试冒充最终通过。

真实公開Controller链：原MIDI导入→固定3格/强度/情绪/放置→完整建议产生2套实际不同音乐，4份comparison/final LMMS连续渲染；另一模式再准备2份。实际MIDI每个note/channel/program/同tick先后/全轨tempo、meter独立解析，MMP实际音符与masterpitch、路由及资源核对，完整WAV PCM读取通过。确认使用同一Score Ref，重复确认不变、一次undo/redo完整恢复；保存61,679,551字节快照重开有效，两模式六格式在中文空格路径导出字节与各自源一致。此项为后端公开Facade，不替代窗口操作。

真实Mac内置扬声器通过配对WavePlayer串行检查6份实际音频的播放、暂停、恢复、停止、重播；设备仅当前MacBook Air扬声器，未更改默认设备。设备流成功不是听感通过，耳机/蓝牙/外接未实测。

音乐对照：18组正常样例及1个精确tick数据场景，63条真实阶段链、51次如实无第二套基础候选、无阶段失败。已找到bridge与连接同时选定且真实端点变化的案例，连接读取桥后末音84而非旧末音62；包含全窗手动bridge与NO_LEGAL_WINDOW。每组保留真实基础、bridge、连接、最终音符/来源/保护/原因；中间中性音色与力度一致，不变阶段共享相同音乐的真实渲染，最终两模式分别输出。精确1tick实际音符保留，输出明确OUTPUT_TIME_UNREPRESENTABLE，无量化，不授予音频就绪或应用资格。全部音频与审计清单位于本轮music-listening，听感仍NOT_TESTED。

当前真实尾音策略未改：正文后固定1秒并沿用现有末尾fade。本轮已审计样例的原始dry PCM在该截点之后均静音，不能据此声称适合所有乐器/素材；最终fade后的零值不能单独证明没有截尾。人工尾音判断仍待反馈。

外部软件：本机LMMS 1.3.0-alpha.2实际打开MMP并查看主旋律；QuickTime10.5实际打开7秒、44.1kHz、16bit立体声WAV。LMMS导入MIDI缺默认General MIDI音色库，未下载安装；音符文件独立解析与第三方音色/人工听感分开。MMP并非自包含工程，依赖目标LMMS工厂资源；本机URI解析及固定内容认证通过，Windows实际解析未测。首次交接脚本指定错误data根的失败诊断已保留；使用实际renderer-context的Contents/share/lmms根后通过，不放宽验证。

127,707,456字节P7已接受存档的修复后纯load/save/reopen/capture-cancel自查通过，原摘要、音乐版本、保护及Ref不变；初测耗时约40–47秒、累计峰值RSS约2.66GB，列为性能限制，不称大工程编辑流畅。最终同机复测另存新的目录，保持128MiB及来源/深度预算，不删除审计以提速。

未完成的人工作业保持独立NOT_TESTED：实体鼠标/双指触控板/键盘、主观音乐与尾音听感、Windows100/125/150%实机、不可用耳机/蓝牙/外接设备。只准备本地交接清单和脚本，不自动发送、上传或推送。最终可执行本机工作全部完成后，缺这些证据时只能P8_PARTIAL。

算法交付的有界队列共80项，已串行完成全部实际输出；其中按实际音乐与模式复用已经认证的同谱文件，而不是重用旧候选或假音频。`music-listening/complete-queue/manifest.json`逐任务记录输入hash/用途与实际输出，19组包含18正常组及精确数据组；精确数据另列拒绝，不在80项无损渲染任务中。候选差异在实际pitch/onset/duration上比较，ID/seed/情绪标签或力度不算差异。18组首套最终双模式的36资产独立文件/PCM审计已通过；队列其余实际不同方案亦保存全谱及原始阶段关联，最终全部用途审计另存仓库外。

前端本地5823c257已集成为59c71a7（五个shared文件与四个UI测试；Mac/Windows适配器只读检查，接口不变）。修复最小窗口约束、长播放名称的点击/焦点全文、短保护标签引导线、手动Bridge可见标识、控制点/手绘优先级及Thread.start失败busy恢复。标签不放大精确音乐范围。卡片仅挂载实际视口及拖动对象，按完整内容、主题、选择失效；不删后端校验。200素材同规模5组对照：原36.27–92.239秒，修复后0.670–1.156秒，最大心跳间隔仍1.744秒，残余卡顿如实待人确认。

前端worker最终914项完整测试、25项专项、32项命中/拖动/卡片测试及check_frontends通过，既有失败日志保留；此时新后端实际服务未同步，不把stub测试写成新链路真实PASS。safe merge后另派只读真实集成smoke，GUI/音频明确串行转交，完成后才运行lead完整Tk套件和冻结。12张实际双主题/三尺寸/来源状态图及真实112个前景/背景样本：正文/按钮最低亮色5.98:1、暗色8.04:1，情绪文字9.45:1；实际PingFang SC 12pt。物理交互与独立人视觉评价仍待验。

后端最后同机复测两份原存档均纯load/save/reopen/capture-cancel通过且源hash/保存大小未变：55,970,981字节约25.84/19.11/20.44/11.16秒，127,707,456字节约28.35/35.91/29.11/27.01秒，进程累计峰值RSS约2.65GB。不同轮处于不同并发负载，不能以时差宣称同条件优化；没有给它们编造流畅阈值。来源事实分别19和30条，128MiB/深度及完整审计仍保持。

算法对全部80项输出另做只读事实复核：28份中性阶段诊断、52份最终乐谱资产，首套36份是后者的子集，不能加成116次独立渲染。中性复用按实际pitch/onset/duration、统一soft/80配方和文件认证，原来源/保护读取各次绑定输入，不把缓存首用的音符身份当作后用来源。发现28份诊断MMP projectnotes误称附加短回声，实际wet=0；仅修正仓库外说明及摘要，完整XML除说明外相同，PCM/MIDI不变，80项重新独立审计通过。原始发现、原摘要及修正收据均保留。

矩阵记录计划与实际输入差异：公开导入推断调性，G01实际强度0.25，不能以原计划C-major/0.35重标实测。数据worktree HEAD、渲染HEAD、UI交付HEAD及集成HEAD分别绑定，不统一改写为最后HEAD。18组有限样例不证明所有保护组合或五类方法都被自动选中：同次乐句连续切片、完整跨界记忆、单侧窗口、主题/手工保护等相关自动回归与实际音乐样例分别列证；没有自动选出的处理保留none，不为凑样例强制改计划。52份原始dry PCM在正文加1秒之后峰值均0、无削波，仍仅为这些样例的诊断，非人工听感或通用尾音保证。

集成烟雾通过真实公开run.py/Controller/provider：导入MIDI与MMP、普通新旋律、实际画布放置与情绪/undo、重复组合中性v2真实准备和设备播放、完整建议真实音频/明确对比试听/确认幂等/undo-redo/纯保存重开；双模式逐格式导出与缺任一文件不禁其他格式；240tick局部方案确认保留[4080,5760)空缺且禁止全部正式导出。只读与剩余gap的原探针FAIL分别因为检查隐藏按钮、比对时漏掉合法gap ID，原收据保留，独立真实重验通过，未改源码来放行。

另发现并修复D-CLOSE-DND：真实TkDND2.9.5 Aqua注销分支抛todo，保存后窗口不能关闭。前端6469e77已集成2ce37cb，Mac只处理该明确未实现分支、清理绑定并拒绝晚到drop，Windows已排队callback同样检查closed，共享close保持幂等；未知错误仍抛出，不宽泛吞错。45专项、7真实公开窗口/设备检查通过；autosave失败时窗口、拖入绑定、工程和真实在播流保持，随后成功关闭销毁窗口与设备。此为配对适配器回归加Mac实景，非Windows实机。dbc6ef2仅纠正来源未选时误称“未导入”的提示，无音乐/选择改动。

新MMP在独立LMMS1.3.0-alpha.2窗口打开，7轨、120BPM、4/4、masterpitch0；data URI的hihat实际显示122ms波形，无缺资源对话框。另将原MIDI导入新空白工程并原生Save As到隔离文件：独立解析发现27/133音符比原MID短10tick，音高数值/起点/数量保持，tempo在tick0为120自动化。D-EXTERNAL-LMMS-MIDI-IMPORT登记为目标第三方版本兼容FAIL；原MID通过逐音符FinalScore一致认证，直接MMP通过认证并可实际打开，不能修改原谱来补偿导入器时值损失。原因未独立定位，编辑此版本LMMS优先使用直接MMP；其他目标软件须另验。默认GM音色缺失使MIDI合成器声音BLOCKED，未安装或修改默认设置。不是把这个FAIL写成音符/第三方全面通过。


## 冻结前最终验证与证据边界

最终源码自查HEAD=9353395a87f7f734658d2f7d49e2186e699526f1：`scripts/test.py` 938项PASS（135.262秒），`scripts/check_frontends.py` PASS；日志在lead-backend/tests/final-full.log、final-frontends.log。后端605项PASS的执行HEAD为14ac9ab，37个后端Python文件至此字节未变；不把较早命令改写成最新HEAD执行。doctor实际检查Python/Tk、LMMS及三个工厂采样通过。文档提交后的完整HEAD、diff检查与代码指纹由仓库外冻结收据绑定。

首次集成完整938项有1项P6只读bookmark测试失败，原final-full-first-fail.log保留；隔离和worker完整重跑未复现默认失败。可控排队Delete在退出只读后才派发能复现同一断言，但未证明它就是原失败原因。frontend提交c005f9集成为4522f2f，仅完善测试的真实映射焦点/事件排空，保留原9项断言顺序并增加3项事件处理断言，不更改产品只读规则。映射P4–P8子组135项、重复6次及最新完整938项均通过；queued-after.json、assertion-preservation.json保留证据。

9353395只修复实际画布谱线在情绪填充上的语义对比度：彩色数据面使用深色线、灰阶阶段覆盖层使用主题线，不修改音乐、命中或坐标。1280×800双主题真实窗口前后图在source-note-before-*与source-note-after-*-actual.png，项目完整相等检查在source-hint-state.json。纯显示修改未添加复述实现的测试。真实背景模糊未实现；情绪数据色是已授权例外。

新v2 WAV已由QuickTime10.5实际打开并查看PCM16 little-endian/44100Hz信息，截图与软件报告在external-v2/wav-open-new.png、wav-info-new.png、wav-external-report.json；未将打开文件写成人工听感。该目录同时保留新MMP实际资源窗口及原生MIDI导入时值损失的FAIL证据。原导出谱仍正确，第三方导入缺陷不通过放宽认证或修改原音符绕过。

最终矩阵保留203个独立证据叶，代码/数据/渲染/界面交付HEAD分别标注；精确数量与结果以封存matrix JSON为准。80项真实输出、文件审计及设备流均不替代全部算法分支的实际自动选中、实体操作、Windows实机或人工听感。没有选中的完整跨界记忆、单侧窗口等真实音乐样例仍列具体缺项，相关自动保护回归另列通过，不混合类别。

已接受工程的新请求捕获与取消此前通过（17.09秒），这不是再次完整生成。独立的已接受工程继续生成实际检查写入accepted-continue-actual目录；完整执行状态及耗时由该目录summary和最终矩阵记录，不以捕获成功冒充完整链路。

本次本机实际截图、程序化Tk、LMMS渲染及Mac设备流已执行；人工视觉评价、实体鼠标/触控板/键盘、人工音乐听感、Windows100/125/150%、外接设备仍NOT_TESTED。LMMS目标版本MIDI导入存在实际时值损失FAIL。故最终即使代码独立审查PASS，也不能宣称全面验收或P8_READY；最终分项结论及收据在仓库外，不为填写“已通过”修改冻结后的仓库。

已接受工程继续生成实际完成：原61,679,551字节工程SHA256=51b015aaf461de1514fc8d064aefece173e9151c45dd66d589f5d9b5e37108e5，公开新请求走bridge/连接/边界/编配及LMMS渲染，59.530秒返回1套实际候选、无失败；当前工程和原文件摘要不变。该输入无空缺，不伪造补全或第二候选。summary/outcome保存在lead-backend/tests/accepted-continue-actual，执行HEAD=9353395。与较早capture-cancel记录分开，不能声称人工听感或大工程全部流畅。
