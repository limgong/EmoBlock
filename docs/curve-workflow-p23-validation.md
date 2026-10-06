# r3 P2–P3 验收记录

SPEC_REV=curve-workflow-v2-r3
CONTRACT_REV=curve-workflow-v2-r3-p23
RUN_ID=curve-v2-p23-20261006-4022708a

## 基线及门禁

P1 受检 HEAD 为 b048565da9306dd473f4faac1fe66c9682cb6478；实际 verifier 最终输出为 ROUND=3、PASS，代码指纹为 73e7518792a6d4003fc4872f24bdcaa6eae267b062caab4f53dfc28ef7e000f1。本轮启动再次读取实际 pane 输出，并独立重算一致。未重置 P1 轮数。

两个 worker 起始目录均清洁、包含同一验收提交。使用已有 Python 3.11 环境，各目录的源码导入位置已独立确认；数据、测试输出、运行日志置于仓库外本轮 RUN_DIR。沿用现有四个 Herdr 角色，不新建 pane。

P2–P3 补充契约经过算法/前端只读评审及独立 verifier 检查。契约 R1 FAIL 指出情绪轻改不能只传保护音符而忽略保护区内休止；修订为 protected_notes + protected_ranges。R2 PASS 指纹为 99674eb102c1f073c1cab0f22af631128e51c312dbe5d97f23db39ef57e697ea。随后标记 FROZEN，提交 4754c87、0940d5f；两 worker 安全同步后开始 P2。冻结产品规范未改动。

## P2 已实现的边界

- 公共 Facade 对接 v2 ProjectSession/Store；独立导入批次、普通新旋律批次和组合批次完整校验后一次入库、一次撤销。
- 原始音符保留稳定内部身份、开头休止及实际短尾；跨四拍长音记录切片连续关系。重叠单旋律输入明确拒绝，不隐式截音。
- 最多三种默认有效候选；六种按需纯规则，真实音乐去重。变体保留来源、参数、种子及算法版本，组合原件保持不变。
- 新建工程为空、固定格数与独立 tick 放置。p0 v2 打开/保存不改变原指纹，首次音乐编辑在同一撤销事务升级当前契约版本；旧工程只读、逐格式导出。
- 中性素材试听独立 LMMS 渲染，不通过旧 planner 或 v2 整曲管线；输出器不能无损表达精确 tick 时明确拒绝，不静默量化。
- 整曲补全、bridge、连接和最终管线保持未接通，不伪造成功或放入占位音符。

## 实际音乐与设备证据

以下路径均相对仓库外本轮 RUN_DIR，不提交用户音频或运行日志：

- `lead-backend/tests/P2-real-import.txt`：真实 assets/theme-c.mid 导入，1 个原始来源、22 个素材通过完整模型校验。
- `lead-backend/tests/P2-real-render.json`、相邻 `.txt`：原始四拍片段与固定 seed=31 回答句各一次实际 LMMS 渲染；每个正文 1920 tick / 2 秒，实际 WAV 含自然尾音为 3 秒。记录音符快照、音频及 MIDI/MMP 路径和 SHA-256。
- `lead-backend/tests/P2-device-stream.json`：当前 MacBook Air 扬声器、双声道 44100Hz，两样例播放/暂停/恢复/关闭均实际执行，播放位置持续推进。不是人工听感质量评定。
- `lead-backend/tests/P2-real-export.json`：两套真实渲染样例的 WAV/MIDI/MMP 六次安全导出，中文与空格目录中逐字节与源文件一致。第三方软件打开与人工听感尚未验收。
- `music-algorithm/tests/P2-original-new-comparison.json`：原始与六种普通新旋律的固定输入、参数及音符对照；不是实际声音试听结论。

## 自动检查及独立复核

P2 算法交付 03a730d（28 项专项）、前端交付 d9b1a88（21 项新 UI 测试，单独工作目录全套 442 项）。集成目录后端套件 328 项通过；另有 3 项使用实际 Facade 和实际素材准备规则的映射 Tk 集成测试通过，覆盖导入/按需生成/重复候选拒绝/组合/精确13tick放置/保存重开/取消迟到结果/主题尺寸不污染保存状态。UI 单元测试使用的假播放器不是设备或声音证据。

主入口已经使用新 CurveApplication，不实例化旧 StoryPage/精细创作。双主题、六种窗口组合实测为映射 Tk 窗口（实际1020×700、1280×800、1440×900），工程内容保持一致。lead 独立截图尝试同样失败，命令返回 could not create image from rect；记录见 lead-backend/tests/P2-real-gui.json。不以坐标或窗口测试冒充截图视觉验收。

check_frontends.py 及 git diff --check 通过。集成全套结果及独立 verifier 结论在运行目录冻结/结果记录中绑定 HEAD 和全部源码指纹；本页在冻结前不预写 PASS。P3 尚未启动，必须先取得匹配 P2 HEAD/指纹的独立 PASS。

## 待验事项

人工音乐听感、真实鼠标/触控板操作、Windows 实机字体/滚轮/快捷键/播放器，均未因自动测试或 Mac 设备流检查而视为通过。实际截图与程序化 Tk 操作单独记录。未实现原生背景模糊；情绪数据色为已授权例外。没有实施 P4 补全、bridge 或连接算法。

## P2 第一轮复核与修复

ROUND=1、HEAD=dc234fd1bfd44c91cca2d3d92dfc90e99012c77c、指纹 dd513be0f86ecf1475ca4c00df7029ebbd65ddd59c9196bde8f308b65921f260 收到明确 FAIL，审查前后匹配。本轮未进入 P3。

- 新 Facade 导出只保护三种文件，遗漏历史元数据及路径别名：恢复全部历史输出文件保护，并测试 report.json、嵌套 snapshot、符号链接/硬链接目标。
- 保存 B 后撤销回打开时 A 仍是 dirty，但此前用初始指纹豁免了自动保存：仅真正未编辑的新空工程可以豁免，已编辑/保存/打开的 dirty 内容遵守自动保存失败即停止切换。
- 试听 WAV 缓存丢失后无法准备：交前端 worker 修复缓存有效性和明确重试，不自动播放。
- 额外音乐自查：副旋律规则的 .8 缩时产生 768/96 tick 等本来可表达输入的新不可表达输出，交算法 worker 在生成规则中明确处理缩短单位；绝不在输出阶段静默量化原始精确 tick。

verifier 独立运行完整488、后端328、前端契约检查，并额外实际串行 LMMS 渲染与六次导出字节比对通过。该证据不抵消以上失败；实际人工/设备边界见其 P2-R1-review.json。修复后必须重新集成、自测、冻结指纹并进入第2轮，不重置计数。

### P2 第二轮集成自查

修复提交：lead 61cf26a（历史文件全保护与 dirty 自动保存）；算法 c6f6c63（仅副旋律缩短规则，明确10tick单位，原始精确时值保留）；前端 14a594f（普通/组合/播放入口失效缓存与准备完成时文件校验）。

集成完整499项、后端335项、check_frontends.py、dirty与基线至HEAD的git diff --check均通过。新增回归覆盖 metadata/嵌套快照/路径别名、保存后撤销与关闭/打开/新建的自动保存失败、失效试听缓存恢复且不自动播放、普通副旋律可表达时值与精确输入拒绝。Windows无符号链接创建权限时仅跳过该别名子情形，普通文件/硬链接保护仍执行；这不等于 Windows 实机验收。

lead-backend/tests/P2-R2-counter-render.json 保存真实副旋律样例、三格式导出字节一致、设备播放/暂停/恢复证据；正文2秒、尾音后3秒。曲谱时值770/100/100为生成规则明确记录的缩短结果，输出器未静默改写任何精确时间。仍不评价人工听感。

computer-use只读捕获尝试未能取得 standalone Python/Tk app状态（timeoutReached，应用列表未识别到可寻址窗口）；未修改系统权限或安装应用。结合此前screencapture错误，双主题截图/人工视觉仍待验，不用源码/坐标检查替代。第二轮只申请P2复验，P3尚未开始；最终结论与审查前后指纹见仓库外P2-R2-result及review记录。
