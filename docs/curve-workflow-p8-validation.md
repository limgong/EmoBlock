# P8 综合验收矩阵与运行记录

SPEC_REV=curve-workflow-v2-r3
CONTRACT_REV=curve-workflow-v2-r3-p7-runtime1
RUN_ID=curve-v2-p8-20261007-492036f5
BASE_SHA=c47c5dca9c14e84216cbc9fce904cf0f0d611e85
状态：MATRIX_DRAFT。P8只验证并定向修复已有工作流，不扩展产品。

## 基线与证据门禁

P7实施TASK_ID=P7-IMPLEMENTATION、ROUND=4、VERDICT=PASS；RUN_ID=curve-v2-p7-20261007-345861bc。受检HEAD等于本轮BASE_SHA，209文件检查前后及本轮现场指纹均为906de19d0761326c30315c1c679abbead880c4e471dfbe6d73f21f063ee8990b，完整manifest逐项一致。真实P7-final-receipt、P7-R4-review和pane结果在对应仓库外运行目录。契约PASS和agent空闲不作为实施PASS。

集成目录和两个worker均干净，交付已集成，实际源码字节一致；四角色Python导入各自目录，复用原解释器。不删除历史或覆盖修改。本轮产物位置为本机EmoBlocks/dev-runs/<RUN_ID>，动态映射、矩阵JSON、音频、截图、工程副本和日志均在仓库外。

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
