# P7 最终处理、完整推荐试听与一次应用验收

SPEC_REV=curve-workflow-v2-r3
CONTRACT_REV=curve-workflow-v2-r3-p7-runtime1
RUN_ID=curve-v2-p7-20261007-345861bc
BASE_SHA=66adc83ece0673e9fa2e879a2a10e37a41381da9

P6实际ROUND2 PASS、HEAD与199文件前后指纹逐项现场核对。集成目录/两worker干净、最新源码一致，旧P4/P5/P6门禁与待人工清单保留。本轮第13节DRAFT；先评审冻结再实现，完成P7停止不进入P8。

完整路径、保护、事务、输出和失败矩阵见契约第13节。自动测试、真实Tk坐标、LMMS、设备流、人工视觉/听感与Windows实机分别记录；不预写独立PASS，最终结论/完整代码指纹在仓库外RUN_DIR receipt，不为写验收记录而修改受检代码。


## 契约只读评审与整合

算法/前端R1和R2均提出明确设计缺口；没有写项目源码、实现或提交。lead已整合13.10–13.16的局部操作与演奏账本、精确同谱编配、双mode、双资产、确认权限、一次事务/注册表、接受后实际读取和取消审计。旧第8–12冻结正文保持不变，本轮契约仍DRAFT，接下来独立verifier检查；不是以worker评审代替PASS。


## 契约独立ROUND1 FAIL与修复

受检HEAD=91d4e6803807bca23780d68c0eaa779a9326b206，前后200文件指纹60b27ff0dac801e955c20f5967bf60b802041c5d9756f0e48a692c5cdf3b5a42，实际pane/review/lead逐项核对匹配，检查期间未写目录。F1 BoundaryRequest无注册ID；F2 source_fingerprint无唯一投影/域/来源闭包。新增13.17并同步Request字段，定义多候选唯一ID/Ref/纯恢复和精确源父闭包/旧接受Score锚点、不自指及两个固定hash向量；篡改后重新hash仍必须拒绝。下一独立契约ROUND2/5，本轮仍无产品实现。


## 契约独立ROUND2 PASS与冻结

受检HEAD=ecb36c53a74663db078032cb82ce72c92f17c769，前后200文件指纹f57174074312a29ece7637e9c68e322342dfdddafbe0313371882fdedc938231，实际pane/review/lead逐项核对一致；R1两项问题关闭，两个source向量和请求多候选身份独立检查一致。只修改状态为FROZEN，不改通过的规范规则。本结论仅契约，现在开始P7实现，实际功能/渲染/人工仍需各自验证。


运行时补充13.18状态DRAFT：p7音乐数据对象保持原冻结版本，服务捕获增加source_facts以及纯历史Snapshot闭包。算法与前端只读评审对文档825b9ac3125770504aa7f1fff290e72ffb8f974d417f4e8f82f64921f3b5969c均PASS；仍需独立P7-CONTRACT ROUND3/5，新增捕获字段尚未实施。

运行时补充独立P7-CONTRACT ROUND3 PASS：HEAD=7cc0a0f5c698c740e8b7f657227ce05a59666428，209文件前后与lead现场指纹a820e1656d442e17517e269ea762c52fc025e1d28667f4e70e78eda2e08311c5完全相同。第13.18只将状态改FROZEN；服务runtime1、音乐数据p7分离，新增运行时字段现在允许实施。本结论不代替产品实现验收。

## 实现集成（等待独立实现验收）

算法原提交f707d81e043c59136174ba092dd8c20abab4d6b5（集成6f496f8）；前端原提交ff8973a28a7a7b48450ae46d9aa0ea24571cd2a5（集成b8b0d4c），运行时source_facts补充71905f6dc2b210e3fe6a7e4b7d4d7b440686ec06（集成f4c14e0）。lead新增curve_final/curve_final_render/curve_recommendations/curve_application，公共会话、存储、快照及story_engine接线。旧路径不迁移，P7数据头仍p7，运行时服务runtime1。

旧来源适配仅读取真实已接受谱/父音符与精确演奏路径；curve_connection_music._captured_key加入accepted_score调性来源读取，与curve_melody/bridge父快照适配一致，不修改P5/P6音乐规则、算法版本和公开schema。载入与保存的保护/来源验证不调用作曲、情绪、编配或渲染。

专项17项在102.659秒通过；随后新增主动留白真实交接与输出力度篡改行为，纯门禁8项在1.231秒通过。故障测试的WAV是明确合成夹具，只测试事务/文件失败，不作正常音乐证据。当前全套及真实导入/LMMS/双模式/试听与导出证据仍在运行，未据此预写产品PASS。

## 实际音乐、事务与设备证据

隔离目录的 `lead-backend/tests/actual-p7/fixed-input.mid` 重新走真实MIDI导入解析，SHA256=eb7a88ef1285c6e33ca379447efa67243114b4c4e0fd14a88ce13abf96eb8801。不是用户工程，来源、父音符和子块由prepare_import建立。3格/120BPM主体6秒，实际LMMS WAV为7秒（含1秒尾音）；完整编配与中性单旋律实际渲染，切换模式不重新作曲。

`initial-outcome.json` 两套最终推荐SUCCEEDED。最终音乐指纹为6244ed58bc0ea28e6f7e01e183cd04bda54a533966ad374f668a9648310749c7和f2ed9def61761f87dca086ce02e78a9a89233ea3e421c41e01d37898beb8632a；差异是实际音高/节奏，不是ID、力度或标签。bridge真实selected且READY，连接明确none，最终边界实际selected。6格无空缺样例 `rough-outcome.json` 有实际bridge；明确Bridge policy none的 `connection-outcome.json` 有实际连接selected。none为合法有原因的计划，不掩盖失败。

`actual-resume-current.log` 与 `summary-current.json` 记录真实资产重新认证、同谱确认、一次undo/redo、保存重开及中文/空格路径三格式导出。接受乐谱指纹1855e3c81ef133b066c9699fa09c9dda34375b8ed52c869e419644ab22d5b3cd；试听、Receipt、有效编辑音乐与导出绑定同一FinalScore和mode，三导出分别与真实生成源字节相同。早期actual_p7.py在保存验证时被lead主动停止以验证性能修复，不将中断日志当最终PASS；旧音频和审计保留，最终证据采用accepted-current.json和summary-current.json。

`stage-audio/manifest.json` 包含两组各四阶段真实LMMS连续渲染：基础补全、bridge布局、连接布局、最终谱。诊断使用一致的中性音色和力度，记录实际tick、notes、保护摘要和范围；不是公共推荐资产或人工听感验收。连接none时两阶段实际音乐相同，如实记录，不制造伪FinalScore。

`device-stream.json` 在MacBook Air扬声器以44100Hz/双声道串行检查基础、处理后完整编配、单旋律和第二方案四个真实WAV；播放位置前进、pause/resume/close通过，源WAV hash不变。human_listening=false；不证明听感质量、Bluetooth单声道或Windows设备。

大型真实来源暴露重复纯验证耗时：加入有界、单操作内容hash缓存，实际数据改变仍重新认证，退出操作即释放，无文件可用性缓存。v2只缩减JSON空白（schema/字段不变），v1原序列化不动。已接受桥素材重用立即登记手动保护，显式移动更新其计划版本；丢失MIDI不禁用有效WAV试听和MMP导出。

root后端575项在62.224秒PASS；随后逐格式恢复与worker短段范围修复必须最终集成复跑。运行日志、缓存、样例与全部音频在仓库外RUN_DIR，不进入提交。
