# 三栏 UI 技术验收记录

RUN_ID=curve-ui-20261007-af9a6bd3
BASE_SHA=36ae1476bd5c08df17ae3e33d50e25983dbc9014
状态：UI3第1轮FAIL已完成定向修复，等待第2轮独立检查。用户明确解锁后，最新源码的60张真实窗口图已补齐；下文锁屏缺项描述为历史过程，不再代表最终图数量。当前仍不预先宣称UI_TECHNICAL_READY。

## 范围和基线

本轮仅实现已确认的三栏布局、按阶段控件和合并试听。约定见docs/design/curve-ui-workspace-plan.md，r3公共数据及音乐规则不变。参考图用于三栏密度和播放器位置，不恢复双图、水平组装条、右栏BPM、情绪画笔及ABCD。

当前基线与用户预期完全一致，Git及两worker干净，实际Herdr角色空闲、源码导入各自worktree。新分支codex/ui-workflow-20261007-af9a6bd3；旧分支与P8运行目录保留。完整动态映射、每阶段任务及验收产物在仓库外本轮运行目录。

P8最终收据为P8_PARTIAL，ROUND4限定技术PASS；HEAD/214文件指纹及收据SHA现场读取。不能改写为全面通过。Windows实机、人手、主观听感仍待验；LMMS1.3alpha2 MIDI导入27/133音符少10tick、大工程127MB约58秒/2.52GB仍为原限制，不视为本轮解决。

## 验证方法

新增行为回归覆盖选择/明确试听意图、缓存及迟到回调、stop/切选/音乐编辑失效、mode-history-export绑定、返回不采用/一次undo、组合取消、高级往返和最小窗真实命中。使用既有Python与独立data/pycache，不安装依赖。check_frontends/full/diff均必须执行，GUI/Tkfull/LMMS/设备串行。

实际窗口矩阵为两主题×三尺寸×来源展开收起×空白/编辑/生成/审阅/历史共60项，截图、具体几何及状态记录在visual-matrix及frontend/tests。不以效果图/Canvas导出替代截图。程序派发事件属于程序化Tk，和真实触控板/鼠标/键盘分开。真实render、设备stream和听感分开，不改写P8素材为本轮新执行。

## 阶段与独立检查

UI0 lead建立基线与任务边界，music只读核对保护/阶段。UI1 frontend布局主题，UI2控件状态/临时播放意图；lead集成本地提交。UI3冻结完整tracked/unignored新文件/deleted指纹，verifier只读独立检查，最多五轮，身份和前后同指纹才有效。冻结后的最终收据保存仓库外，不能为了“通过”文案修改已验代码。

## 待人工项目

Mac实体鼠标/触控板/键盘与原生下拉焦点、主观音乐/尾音听感；Windows100/125/150%字体/滚轮/快捷键/设备/资源实际解析。新说明和操作表见docs/curve-ui-manual-acceptance.md。真实背景模糊未实现，情绪数据色为授权例外。

## 实施进度与实景复现

music-algorithm完成UI-MUSIC-READONLY-REVIEW ROUND1 PASS_DESIGN，实际worktree纯导入/Token和undo探针通过，无源码改动；现有Facade足够，不扩公共接口。后端token不会因停止/切选自动失效，因此前端播放意图为额外授权，并需编辑/undo、mode、newrequest/cancel失效。

UI1 frontend本地52e6e7d集成3c1b2e0。改造前实际截图：1280×800画布266px、1020×700画布166px，全窗底部日志/播放器挤占高度、暗色凸边、卡片双准备/播放按钮及编号截断。第一版实际图画布分别468px/380px、右底player、原稳定M编号前置/真notes缩图；此时不是最终UI2验收。lead实景审查要求继续处理暗色凸边、工程名、百分比轴线与明确模式，不能用第一版图代替最终状态矩阵。

原阶段UI测试所需允许文件已由lead扩至tests/core/test_curve_p3_ui.py、test_curve_p4_ui.py、test_curve_p6_ui.py、test_curve_p7_ui.py、test_curve_p8_ui.py，只适配菜单/前置/显示，保原保护、只读与事务覆盖。新播放意图与组合草稿的初次失败日志保留，不改写为通过。

截图过程曾出现真实锁屏：只读IOConsoleLocked/CGSSessionScreenIsLocked均Yes，窗口/区域捕获失败，已请用户手动解锁。继续可执行自动检查和音频路径，禁止自行解锁、改权限或电源。最终截图矩阵必须记录实际完成情况，锁屏下Tk坐标或Canvas导出不是截图。必需视觉检查未完成时不能UI_TECHNICAL_READY。

## UI2集成与实际检查

frontend UI2本地98ab63b6590c1398b9eb099105c76c2999fff6da集成51093cd；UI1原52e6e7d集成3c1b2e0。lead独立f71f500将tests/ui纳入标准完整脚本，backend-only明确排除此UI目录，并将主题可达性旧准备/取消控件前置改为常驻播放/暂停/停止，保原项目、播放、选择及滚动断言。frontend原prepare_button句柄已兼容指向唯一试听按钮，无第二个可见播放动作。音乐后端、工程格式、播放器适配器及既有冻结契约均未修改。

实现三栏、48px单行顶栏/文件菜单、项目名与保存状态；来源180/素材252/8px间距、<1180默认折叠与用户覆盖；来源筛选、96px虚拟卡/稳定M编号前置/真实notes预览/单试听；单二维画布百分比和拍格、三个模式、仅选积木的情绪/选gap的操作；高级分阶段和明确自动补全并应用；右下候选选择/两侧对比/采用/返回，右底共用播放器及格式菜单、短结果与打开位置。hover/focus实际Tooltip，暗色clam的lightcolor/darkcolor/relief一并处理，无原生模糊或装饰动画，情绪数据色为授权例外。

临时PlayIntent绑定对象/模式/输入快照/完整token及资产键；stop/cancel/换选/模式/编辑-undo/新请求失效。仅合法结果准备并重新认证后可播放；阶段准备与正常生成不会自动播放或采用。源/块/情绪/组合原缓存依据不变，推荐缺模式明确准备该侧资产且保持候选/模式/快照门禁，历史逐格式版本判断保留。视图书签保高级往返的草稿和只读预览，不写音乐数据。

frontend：198专项及原938完整通过（135.395秒）、新UI专项23通过；check_frontends/diff通过。旧失败日志保留。原阶段UI测试仅将tick文案断言转移到详情、旧常驻控制访问改菜单或明确模式/选择前置；具体AST测试方法保留与assert计数在frontend/tests/delivery.json和test-adaptation-audit.json。新增行为不只验证颜色常量。

集成目录51093cd：标准scripts/test.py包含新增UI目录，958项PASS（143.277秒），scripts/check_frontends.py PASS；日志lead-backend/tests/full.log、check-frontends.log。相对BASE全部backend文件无变化；本轮不把后端规则重写来配合UI。

真实公开run.py/Facade控件34项检查：组合左右拖放/草稿不dirty/确认一次undo、源码MIDI/MMP与六方法命令、控制点/迟到回调/stop/selection/edit-undo，以及一次无缓存真实LMMS中性组合准备→有效意图→实际WavePlayer流。实际PCM44100/双声道/5秒；渲染约0.506秒，不是音乐听感结论。迟到故障使用原真实资产加受控延迟，明确不是三次新渲染。

保留P8真实候选资产的推荐与成品18项窗口检查：选择不播放，明确准备好的编配模式后两侧同共享设备播放，返回不采用、同谱采用/重复幂等/一次undo-redo/保存重开/三格式导出及dirty不变。初次探针把未准备另一模式误作可立即播放的错误收据单独保留，修正另存actual-recommendation-v2，不冒充新管线渲染。新主入口真实完整管线另在lead-backend/tests/new-pipeline报告逐阶段记录。

提交后60组真实Facade/Tk映射矩阵（2主题×3尺寸×2来源状态×5状态）几何通过、最小Canvas控件331px，实际样式/Canvas颜色对比度最低5.33:1；位于frontend/tests/matrix-geometry-final。GEOMETRY_ONLY明确path=None，不是截图、不代表物理输入。改造前与UI1共8张实际截图来源与摘要保留，但不能代表最终UI2。

## 历史截图阻塞与持续待验

最终60张真实窗口截图仍因实际IOConsoleLocked/CGSSessionScreenIsLocked=Yes无法取得，窗口与区域捕获原失败证据保留。用户需手动解锁后才能补拍；不自行解锁、改变权限或电源。必需视觉缺项意味着本轮当前只能BLOCKED，不能把自动958PASS、程序化矩阵或设备流替代技术完成门禁。

Mac实体触控板/鼠标/键盘、Windows100/125/150%与目标资源解析、人工视觉/音乐听感均PENDING/NOT_TESTED。P8第三方LMMS MIDI导入时值FAIL与大工程性能限制不改写。全部音频/截图/副本/日志/代码指纹/角色映射外置，本轮收据在仓库外，不为填入PASS修改冻结代码，不发布/推送/进入新功能阶段。

新增主入口实际完整链在集成HEAD51093cd执行，总耗时115.402秒，保存结果含2套真实不同音乐候选、19条真实阶段事件；主按钮与选择均不播/不应用，明确最终试听及完整PCM、同谱采用、一次undo-redo、保存重开、选定历史WAV均通过（15项）。每候选Bridge_LOCKED均在Bridge_GENERATION之前，连接在其之后。音频是本轮新实际LMMS，不是P8音频复用；设备播放非听感PASS。

## UI3第1轮发现、修复与第2轮材料

verifier UI3-R1在62444e1/1ef5b2f4指纹上独立958测试PASS，但明确FAIL：返回编辑后recommendation.visible未退出，编排/控制点/手绘仍隐藏；原音乐和输入文件未改变。收据及前后指纹保留verifier/tests/UI3-R1-review.json。frontend 3511697集成a770aec，将显式返回及采用成功接到已有编辑视图，失败采用保只读；一般restore_view语义不变。补映射返回后工具/动作、候选重开、失败采用不切换、幂等/一次undo和原文件不变检查。

负责人真实图审查另外发现空工程控件过多、加载后导入提示过期、FULL/CURRENT内部码外露，以及生成中仍显示disabled候选审阅行。frontend 4d05cfd集成31281eb：空工程保导入、隐藏不适用工具；空notes/纯休止无生成请求，保无source音符快照可编辑；加载提示按事实显示，简短候选/历史标签中文化、原码留详情。frontend 3680ad5集成132f080：活动RECOMMENDATION隐藏审阅行、结束恢复，真实phase中文/耗时直显，原state.message放详情；不改RECOMMENDATION_MODE播放意图或音乐门禁。

修复最新版完整964项PASS151.103秒、11专项PASS5.873秒、check_frontends与diff PASS。真实Controller的隔离READY工程61检查覆盖两主题/窗口尺寸返回与适用动作、候选/缓存保留、失败/成功采用、幂等、一次undo-redo、保存结果重开；原始探针前置错误另存，不删失败日志。最后仅生成显示修正不改上述事务。

用户回复“已解锁”后，经实际CG session未锁定核对，最终UI3-R1-final-v4-matrix报告60张真实Mac窗口捕获成功：两主题×1020×700/1280×800/1440×900×来源展开收起×空白/编辑/生成/审阅/成品。PNG逐张hash和源码digests绑定3680ad5；集成源码逐文件一致。生成图通过实际主入口捕获RECOMMENDATION、provider受控等待，只验证运行布局，不伪称额外音乐生成。旧v2锁屏失败、v3对应4d05图和更早before/UI1图仍分别保留。负责人已实际看最新版空白、编辑、运行、候选和成品图，最终独立复核另行出具。

本轮新真实完整LMMS和设备流证据仍为lead-backend/tests/new-pipeline；修复改的是UI状态，未重新作曲来伪造更多音频。人工视觉审美、物理Mac操作、Windows三个缩放、人工音乐听感与外设音频依旧PENDING；P8历史PARTIAL与两项既知限制未改写。最终收据写仓库外，不为标记PASS改冻结目录。

最新版生成取消入口另由frontend真实窗口复测10项PASS：v4原图及新增图均可见“取消”，实际坐标点击先登记CANCEL_REQUESTED再收拢到CANCELLED，busy退出，工程/saved/undo/播放器不变。该疑点未复现，不改代码；收据frontend/tests/UI3-R1-cancel-check/report.json。最终交付UI3-R1-fix-delivery.json为READY_FOR_REVIEW，源码3680ad5，旧BLOCKED交付另存不覆盖。
