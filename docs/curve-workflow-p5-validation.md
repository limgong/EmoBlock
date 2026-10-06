# r3 P5 bridge 验收记录

SPEC_REV=curve-workflow-v2-r3
CONTRACT_REV=curve-workflow-v2-r3-p5
RUN_ID=curve-v2-p5-20261007-3dec2380
BASE_SHA=c767fe650219df5eb23f92abc3ff075846b05069

## 起始基线与现有修改

P4最终ROUND3明确PASS：HEAD=c1b148bb4bb2eb2a02461270aee26f27e841ad1d，前后185文件指纹b55e9d170a3425a42c837db74445aeb3d0b7677f382d0ad4b7abafed1254b4eb；实际pane存档、review和receipt已现场核对。来源闭包、纯恢复、候选隔离及P3旧保护/跨界长音修复保留。

六个已有未提交文件全部属于删除键修复，单独提交c767fe6作为本轮基线：docs/macos-portability.md、frontend/shared/curve_canvas.py、frontend/macos/ui_platform.py、frontend/windows/ui_platform.py、tests/core/test_curve_canvas_ui.py、tests/platform/test_platform_contracts.py。修复独立RUN=mac-canvas-delete-20261007-022505-04e87cd4、TASK=MAC_CANVAS_DELETE、ROUND1 PASS，前后指纹26737299c95b39dc6a83bf56743d574786cada6806c8188bc11fe4d349a66ab6，649完整测试、成对适配、真实后端映射Tk/撤销/保护拒绝通过；实体Mac删除键和Windows实机仍待验。不是P5功能提交。

四角色实际名称/pane从Herdr JSON核对（HERDR_ENV=1），现有verifier、music-algorithm、frontend均空闲；两个worker无未交付改动，安全ff到上述基线。四角色包装器复用已有Python，各自实际加载自身worktree，数据/临时/测试/pycache在仓库外隔离。运行记录位置通过本地/tmp/emoblocks-p5-run查询，不写入源码指纹。

## 契约状态

第11节p5已FROZEN。算法和前端只读初审及补充评审已整合范围／集合／部分失败、phrase子块闭包、真实发声来源、每桥预算、指纹域、overlay与继承计划归属；契约ROUND2独立PASS后才开始实现。契约和实现独立记录轮次，各最多5轮；检查冻结期间不写集成目录。

## 预定验收与边界

覆盖用户十五场景：基础输入无效/STALE/篡改拒绝；当前完整输入；单有效/局部基础；2/3/4及更长窗口和none；原子锁定；部分失败保锁；手动bridge+none；相邻/单侧/key/rest；记忆/主题/手工/留白/长音；来源/音乐/hash反例；取消迟到重复编辑undo；纯保存恢复；确定性；无P6/最终边界/旧planner调用；精确tick及输出拒绝。

自动测试、程序化Tk、实际LMMS渲染、设备播放、人工视觉/听感和Windows实机分别记录。P4已有真实材料和未验清单保留，不能充当P5实测。P5不开放最终应用/完整方案试听/整曲导出；验收音频仅是基础与bridge后对照。完成P5后停止不进P6。

基线doctor确认Mac Python3.11/Tk9、现有LMMS和样本可用；436后端测试通过（2.239秒），这仅是P5实现前的基线检查，不是P5功能验收。


## 契约独立ROUND1 FAIL与修订

受检HEAD=f787a3ba1282b0d4f4d4922f4b4d139bc3a5ba44，186文件前后指纹6e4fdbc3b34c8a15dba6b90a0067f81fda76c679e899bae2a6784ca27a7f5ab8，现场与实际verifier输出/review核对。缺少公开bridge→protection映射，及计划创建前FAILED/CANCELLED的plan_fingerprint空值约定。第11.11补齐Plan.protection_refs、明确inherited owner身份域、初始集合重建和终态完整形状，新增往返/篡改/纯恢复验收。仍DRAFT，功能实现尚未开始；下一次独立轮次为2/5。


## 契约独立ROUND2 PASS与冻结

受检HEAD=990176694109c1507426973fa478ffa765725842，186文件前后指纹186d265ad323c9b7152fcfc220dbd06ac6a892f68eb6a85461c8947774455273，实际输出、review与lead重算一致。R1两问题闭合，无新增阻断；只修改状态标FROZEN，规范正文未改。此PASS仅契约，不代替P5实现验收；实施轮次从1开始最多5轮。

## P5 实现与本地集成

lead：curve_bridges独立请求/计划/来源/实际音符/情绪账本认证；curve_workflow原子锁定、流式结果认证及终态事务；curve_store纯恢复与RUNNING→INTERRUPTED；curve_session处理版本Token；story_engine专用P5入口。保留旧工程音乐头和P4处理版本，不因打开、保存或候选计算升级原工程；旧planner/连接块/最终边界未接入。

music-algorithm：02d96a1＋6d0cc42（集成f3bee9e＋d635f43），独立有限选位、保留自然排布的none决策、动机发展完整乐句、相邻共同端点、一次情绪处理及四拍子块。补齐受保护长句的合法内部窗口及真实公共门禁测试，算法专项26项；实际来源/留白/短尾/邻接/单侧样例见music-algorithm/tests/evidence-manifest.json。组合独立扁平ID反例由lead修复并纳入专项回归。

frontend：a2637c6（集成7cfa6fc），现有三栏中的Bridge入口、真实阶段/已用时间/取消、范围锁与就绪分轴、唯一画布只读覆盖预览、互斥P4/P5视图、流式回调及快照门禁。素材、播放器、旧成品逐格式导出保持原语义；不提供最终方案应用/试听/整曲导出。

服务自测15项覆盖真实算法往返、单合法INSUFFICIENT候选、局部剩余空缺、全部锁原子登记、部分成功保留、失败/取消/迟到/重复/编辑后undo、新attempt隔离、手动桥+none、独立扁平ID嵌套组合来源、重新hash仍无法掩盖结构/来源/子块篡改、禁用算法后的纯恢复、保存写入失败及R1指出的历史自动桥合法力度继承。手工构造的事务决策不是选位音乐质量证据；实际算法场景另列。

lead用最终集成源码重跑算法13个对照样例，全部通过独立门禁（含worker旧门禁拒绝的独立扁平ID反例）；相对目录lead-backend/music-algorithm-replay/evidence-manifest.json及测试日志p5-music-replay.txt。精确1tick、实际4080tick短尾、2/3/4/8块、相邻、不同调性单侧、主动留白、嵌套组合和部分失败都有实际数据。算法worker自身未渲染/未调用硬件，其684完整/471后端/26专项结论只对应自身交付分支；集成验收以lead及verifier受检代码为准。

## 自动检查和 GUI 证据边界

已有环境的隔离run-python包装器实际使用仓库.venv解释器和自身源码。

- scripts/check_frontends.py：PASS，共享UI、成对适配器及后端隔离检查。
- scripts/test.py实施R1集成：717 PASS，117.774秒；首轮710 PASS为新增测试/最终算法修正前的历史记录。R2修复后的检查另列。
- scripts/test.py --backend-only实施R1集成：476 PASS，4.865秒。
- 前端首版专项28 PASS、自身完整677 PASS；Mapped Tk双主题×1020×700／1280×800／1440×900，唯一画布可绘制高度166／266／366px，播放按钮44px。使用测试Facade/播放器替身，不等于真实后端或设备结论。真实后端UI集成另行记录。
- 前端首份仓库外真实集成5/5记录对应最终选位修正前的输入，verifier在R1复跑4/5：原第五项预设双桥，但默认预算只选出一桥，不能作为最终双桥证据。verifier换用合法960tick音符输入后补验流式取消通过。lead在R2同样更新真实输入及完整来源，使用实际Facade/P4/P5/P3重新跑5/5 PASS（7.351秒），涵盖六主题/尺寸预览、保存重开、取消/迟到/中断、P4→P5、undo失效、自然none及双桥流式取消。仅WavePlayer替身。最终对应lead-backend/p5-real-integration-r2.py、lead-backend/tests/p5-real-integration-evidence.json及p5-real-r2.log；旧frontend证据保留作为历史，不冒充最终结论。
- git diff --check：实现中持续PASS，冻结前和独立验收仍须检查。

## 真实音乐、锁与来源对照材料

所有测试及音频只在仓库外本轮运行目录，不提交音频或用户数据。通过本地/tmp/emoblocks-p5-run定位；相对材料目录lead-backend/music。

- selected-request.json／selected-proposal.json：完整原排布和实际基础音符、选位评价与理由。固定8秒、7680tick场景，自动记忆保护首四拍，自动bridge覆盖[1920,7680)。
- selected-range-locked.json：生成前已登记全部RANGE_LOCKED；selected-ready.json为实际CONTENT_READY及独立认证内容。
- natural-none.json：自然旋律的明确none计划、理由和版本，非算法失败的替代。
- partial-failed-locks.json：第一桥实际READY，第二桥故障模拟FAILED，保留CONTENT_READY与RANGE_LOCKED，下一阶段能力false。
- music-difference.json：原始/bridge后实际pitch/start/duration对照、逐音符父放置/快照/动机与发展账本；基础排布和保护范围不变。
- archive-location.json：保存快照路径，重开实际内容一致，不恢复线程。
- render-assets.json、base 对照.wav／bridge 对照.wav及对应MID/MMP：已有LMMS真实连续渲染。两份正文8.0秒、实际音频9.0秒（保留尾音）；三种格式的开发验收复制与源字节一致。此为私有P5中性旋律对照，尚未处理连接块、最终边界和整曲编配，不授予产品最终导出资格。字节校验不等于第三方软件打开或音乐质量合格。
- device-check.json：渲染结束后串行使用macOS真实WavePlayer/PortAudio，当前MacBook Air扬声器双声道44100Hz，两份WAV播放位置推进、暂停/恢复、关闭通过，源文件不变。这是程序化设备API证据，非用户点击GUI或人工听感结论。
- final-source-replay.json：最后算法修正集成后以保存的真实Request/Plan重新生成并独立认证，全部实际Result与音频样例原结果一致，选位窗口亦一致；已有渲染材料仍对应最终音乐实现。

## 待验事项与 Mac 手动流程

实际窗口截图六次均失败，系统screencapture返回“could not create image from window”；未修改权限或设置，截图和人工视觉列为待验，不能用坐标证据冒充截图。实体鼠标/触控板/键盘操作、人工音乐听感、Windows实机（含125%／150%缩放）以及外部DAW打开MIDI/MMP尚未验收。主题是静态跨平台Vibrancy风格，不实现真实背景模糊；情绪数据色为已授权例外。P4与既有删除键修复的实体双端待验项目继续保留。

约5分钟Mac验收：

1. 在隔离工程打开本轮archive-location记录的快照（不要覆盖真实工程），确认原放置、强度、保存状态和历史不变。打开Bridge查看锁/就绪与范围，核对记忆标识独立。
2. 切换明暗主题及三窗口尺寸，展开/退出Bridge只读预览、横向滚动首尾，核对按钮可达、完整理由可读、无第四栏或另开试听窗口。只读预览按⌫和Fn+Delete不能删当前编辑。
3. 返回当前编辑，在完整排布或有效单条基础候选上明确点击判断Bridge，观察判断→已保护→生成→就绪；取消后锁保留，重新尝试计划版本不同，不改变素材选择和播放器。
4. 打开partial-failed-locks对照说明，确认失败范围仍有锁而非普通空缺；工程修改再undo后旧候选仍显示失效，不可继续消费。
5. 串行人工试听base/bridge对照WAV，检查动机、入口、休止和尾音；另用LMMS打开对应MMP、DAW打开MIDI。记录听感问题，不将就绪认证当作听感合格。P5页面没有最终确认/完整方案试听/整曲导出，属于本阶段边界。

P6建议：lead负责消费匹配版本的READY Plan、CONTENT_READY全集合和保护摘要；算法负责连接块规划/生成，最终边界保持下一阶段；前端显示独立连接状态及候选保护，verifier审查不可改变bridge音高、起点、时值。此处仅派工建议，本轮不开始P6。

## 独立实现检查

实施提交冻结后由现有verifier检查集成目录。验收RUN_ID同文首、TASK_ID=P5，实施ROUND从1起，每轮最多5轮。冻结HEAD、全部已跟踪/未跟踪源码测试指纹、实际pane输出、独立review和前后指纹保存在仓库外RUN_DIR的P5-Rn-freeze.json、verifier-P5-Rn-output.txt、verifier/tests/P5-Rn-review.json及最终P5-final-receipt.json。本文件冻结时不预先声明实现PASS；后续结果仅在这些运行记录和交付汇报登记，避免记录变化破坏受检指纹。契约PASS不代替实施PASS；未验平台与听感项目不因PASS自动关闭。

### 实施 ROUND1 FAIL 和修复

受检HEAD=fa5ffb7c5de60756716726d1d4032ca279ce9ad7，192文件前后指纹e94532f85d0a81d21914f7ae905977146618364336909c3ba969387c9bb33b7e，实际pane/review/lead重算匹配，检查期间无修改。独立专项40、后端476、完整717和前端检查均PASS，另完成禁用全部算法的纯恢复及13组音乐认证。明确缺陷P5-R1-F1：合法历史自动桥当前实际velocity=100、历史记录velocity=80，但pitch/start/duration/身份完全不变，继承认证却从旧记录重建预期音符，误拒绝整个none计划。

修复：历史记录和锁完全保留，独立认证原记录与结构保护后，再认证当前实际发声结构；当前合法力度用于实际Result.notes和新包装指纹，不把旧力度误当成不许变化的旋律结构。原计划类型/版本、唯一记录及保护映射同时严格匹配。新增none/selected×80/100四子场景，实际生成READY，非法音高/起点/时值重新hash仍拒绝，禁用算法后保存恢复通过；不放宽保护或旧格式校验。复制verifier最小反例到lead隔离目录重跑，两种力度均ACCEPTED/READY，旧记录和锁未改；原verifier证据不覆盖。补正双桥Tk材料并实测通过，未把测试输入差异当成产品算法缺陷。后续复验轮次为2/5，未重置计数。
