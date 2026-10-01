# GitHub 源码仓库

用户指定远程：`https://github.com/limgong/EmoBlock.git`，默认分支 `main`。

首次检查时远程未返回任何分支，按空仓库建立本地 Git 树。正常提交/上传命令：

```bash
git status
git add <本次修改的文件>
git commit -m "Describe the change"
git push origin main
```

不要使用强推替代处理远程冲突。若 GitHub 身份验证失败，需要当前账户对仓库有写权限，并使用 Git Credential Manager、SSH 或其他本机登录机制；不要把访问令牌写进源码、文档或聊天。

上传范围：正式前后端源码、启动入口、依赖列表、示例 MIDI/MMP、设计文档、测试与 CI。未上传范围：旧发布包/压缩包、LMMS 可执行文件、虚拟环境、用户工程、生成音频和备份。根 `.gitignore` 固定这一边界。

项目尚未由所有者选择开源许可证；上传 GitHub 不自动授予第三方开源许可。默认演示旋律和第三方工具的来源及权利说明见素材说明与相应官方项目，不得据此声称项目拥有原曲版权。
