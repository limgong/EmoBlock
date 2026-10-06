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

第11节p5 DRAFT，已收到算法和前端只读初审，整合范围／集合／部分失败、phrase子块闭包、真实发声来源和两阶段主线程锁定接口。两角色ROUND2要求补齐每桥音符预算、精确指纹域、overlay形状及继承结果计划归属，均已整合；独立契约检查尚未开始，未实现产品功能。契约和实现独立记录轮次，各最多5轮；检查冻结期间不写集成目录。

## 预定验收与边界

覆盖用户十五场景：基础输入无效/STALE/篡改拒绝；当前完整输入；单有效/局部基础；2/3/4及更长窗口和none；原子锁定；部分失败保锁；手动bridge+none；相邻/单侧/key/rest；记忆/主题/手工/留白/长音；来源/音乐/hash反例；取消迟到重复编辑undo；纯保存恢复；确定性；无P6/最终边界/旧planner调用；精确tick及输出拒绝。

自动测试、程序化Tk、实际LMMS渲染、设备播放、人工视觉/听感和Windows实机分别记录。P4已有真实材料和未验清单保留，不能充当P5实测。P5不开放最终应用/完整方案试听/整曲导出；验收音频仅是基础与bridge后对照。完成P5后停止不进P6。

基线doctor确认Mac Python3.11/Tk9、现有LMMS和样本可用；436后端测试通过（2.239秒），这仅是P5实现前的基线检查，不是P5功能验收。
