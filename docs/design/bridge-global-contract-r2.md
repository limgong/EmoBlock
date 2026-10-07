# Bridge 全曲分析：乐句边界归属补充

STATUS=FROZEN
SPEC_REV=curve-workflow-v2-r3
CONTRACT_REV=curve-workflow-v2-r3-bridge-global2
SUPERSEDES_SERVICE_REV=curve-workflow-v2-r3-bridge-global1

本增量保留已冻结的 `bridge-global-contract.md`，只解决首次实现发现的
contour_turn 归属歧义。公开音乐对象仍属于 P5；请求定位版本仍为
`curve-bridge-global-v2`，分析版本更新为 `curve-phrase-analysis-v1.1`。
global-v2 尚无已验收实现或已接受的历史音乐结果，不迁移旧 v1 工程、
attempt 或音乐。旧定位 v1 的校验、选位及生成语义不变。

## 复现与最小规则

原冻结样例的 P1、P3 中，前一放置末音与当前放置前两音产生反向音程。
若跨两个 terminal/performance 计算 contour_turn，5040、12720 tick 的
证据为 rest .30 + attack .10 + contour_turn .20，达到 .60，误把两个
三音乐句切开，冻结的远主题回归关系因此消失。

仅将 contour_turn 定义收紧为：三个实际连续音符属于同一 terminal
occurrence 与同一 performance 时，两个非零音程反向处的起音登记 .20。
跨 terminal/performance 不登记这一项；重复使用同一素材不是同一演奏。
terminal 内的音符仍使用当前有效音乐，不能退回库原件。

其他边界证据、阈值、端点、乐句划分、远距离动机关系、评分、有限搜索和
统一 DP 完全沿用 global1。乐句仍可跨多次放置：休止、起音、节奏、实际
放置边缘等其他证据继续参与。此规则不是来源乐句硬边界，也不禁止长句
内部合法窗口。全曲动机比较不受 terminal 限制。

分析指纹纳入 v1.1；请求与计划仍绑定其实际持久化分析、输入及保护摘要。
不接受 v1 分析冒充 v1.1，不通过加载、保存或纯校验升级旧数据或作曲。
本轮尚未发布的实验 v1 分析只保留为运行证据，不用于应用或后续连接。

## 验收

1. 使用冻结的完整 A/X 样例，列出边界、关系、实际候选全集及最终 DP。
   A 应选择 [7680,11520)，X 应完整搜索后 none；不能仅验证手算分数。
2. 同一 terminal 内真实转折仍登记；跨 terminal 的相邻转折不登记。
   原起点、时值、来源、演奏身份及所有硬保护不变。
3. 重排和重复使用后按实际 terminal/performance 计算，而非素材 ID。
4. 纯验证独立核对归属及该证据，伪造 contour_turn 或分析版本必须拒绝。
5. 搜索覆盖、密集开头公平性、长句内部窗口及旧 v1 回归继续验收。

算法角色已报告该复现和上述最小修订建议。独立契约 ROUND=3 审查通过后
才实施此增量；不重置既有五轮上限，不改变 UI 或 Bridge 音乐生成规则。
