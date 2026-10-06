# r3 P6 连接块验收记录

SPEC_REV=curve-workflow-v2-r3
CONTRACT_REV=curve-workflow-v2-r3-p6 (FROZEN)
RUN_ID=curve-v2-p6-20261007-715c3cb7
BASE_SHA=8706f96fa9c8aecdbb613f115547f64255da9b3c

## 启动核对

实际P5 verifier ROUND2 PASS：RUN=curve-v2-p5-20261007-3dec2380，TASK=P5，HEAD=8706f96fa9c8aecdbb613f115547f64255da9b3c，192文件前后指纹c733742fd431bfd27e751ca51bda3ad1bb2fa3414d1ce36d7b928490af8ccbd3。现场读取真实pane存档与review JSON，独立重算集成和两个worker全manifest一致且工作目录干净，三个worker都已done，无在写入任务。P4纯恢复/来源闭包、P3保护/跨界音符及Mac删除键修复全部保留。

HERDR_ENV=1，从实际JSON读取原四角色名称/pane，不新建或更换模型。角色映射、Python各自源码路径、轮次、任务和日志放仓库外RUN_DIR；本地/tmp/emoblocks-p6-run仅指向运行目录。复用已有.venv解释器，各角色数据/tmp/pycache隔离；不提交用户工程、音频或运行记录。

## 契约与实施边界

第12节p6补充先算法/前端只读评审，整合后独立verifier PASS方可FROZEN和实现。契约与实施独立各最多5轮；冻结期间不写集成目录，PASS必须匹配RUN/TASK/ROUND/HEAD及前后相同代码指纹。历史契约正文保留，不自动迁移音乐工程头。

P6只消费真实就绪bridge布局，规划/生成保护外有时长的连接覆盖层，并独立认证实际音符与保护。当前编辑、基础候选、bridge事实和连接层分别存储；没有最终应用、完整方案试听或正式整曲导出，不进入P7。

## 验证计划与证据边界

必测场景见契约12.6：READY全集合/版本门禁、实际桥端点、三类侵入及合法窗越界音符、保护完整长音/休止、多个窗口和共同端点、none与失败、取消迟到重复/保存纯恢复/快照隔离。执行专项、后端、完整套件、check_frontends和git diff --check。固定输入基础→桥→连接actual notes和来源/保护摘要保存仓库外，真实LMMS连续渲染与设备检查串行；声音标注“尚未经过最终块间处理”。

自动约束、真实Facade程序化映射Tk、真实LMMS、设备API、人工视觉/物理键鼠/触控板/听感和Windows实机分别记录。已有P4/P5截图失败及人工/Windows/DAW待验清单保留，不能充当本轮实测。静态Vibrancy风格不实现真实背景模糊；情绪数据色为已授权例外。

本页在冻结前记录实施与证据，不预写独立PASS。最终受检结论保存在仓库外P6-Rn-freeze.json、verifier-P6-Rn-output.txt、verifier/tests/P6-Rn-review.json和P6-final-receipt.json，避免验收后修改文档破坏指纹。


## 契约双角色只读评审

算法和前端ROUND1均指出可实现性缺口，未写仓库或运行产品算法：精确状态/覆盖层与队列、逐窗元数据/来源、去身份音乐种子、真实发展门禁、历史保护力度比较、父预览隔离和预算耗尽。lead整合第12.7–12.9，历史冻结正文未改；独立契约轮次尚未开始，当前仍DRAFT。基线477后端测试和check_frontends通过，仅基线证据。


## 独立契约ROUND1 PASS

HEAD=5c70a8c6d0e0b724831a0f82a4139fe66b5f1138，193文件前后指纹1dd4d9914e45d51853de7b89dd24936502c273f0deba2b29b173e90098df90e2，actual pane/review/lead重算完整manifest一致。无阻断契约缺口；历史8–11正文未改。只更新本节状态FROZEN后才开始P6实现，此PASS不代替产品测试和实施验收。
