# 三栏 UI 技术验收记录

RUN_ID=curve-ui-20261007-af9a6bd3
BASE_SHA=36ae1476bd5c08df17ae3e33d50e25983dbc9014
状态：实施中，未取得本轮独立验收。

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
