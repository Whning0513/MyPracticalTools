# 仓库发布审计器

`repo-release-audit` 在公开或归档 Git 仓库前检查常见问题，包括缺失的仓库元数据、强特征凭据、机器绝对路径、失效的本地 Markdown 链接、大文件、符号链接和丢失执行位的脚本。

命令只扫描 Git 已跟踪文件。报告包含文件名和行号，不打印命中的密钥或源码。

## 安装和运行

```bash
python -m pip install './repoReleaseAudit'
repo-release-audit /path/to/repository
```

自动化流程可以读取 JSON：

```bash
repo-release-audit . --format json
```

默认从 50 MiB 开始警告大文件；达到 GitHub 100 MiB 单文件限制时报错。`--strict` 还会把未提交的工作区改动视为错误。

## 检查项目

- 根目录 README、`.gitignore` 和许可证。
- GitHub、OpenAI、AWS 密钥和私钥头部特征。
- 用户目录与机器数据目录绝对路径。
- 本地 Markdown 链接、符号链接、文件大小和脚本执行位。

凭据检查使用较窄的特征，减少误报。安全敏感仓库发布前仍应运行专门的 secret scanner。

确认安全的示例可以添加行内 `release-audit: allow-secret-pattern` 或 `release-audit: allow-machine-path` 标记。添加前应人工检查该行。

## 开发

```bash
python -m pip install -e './repoReleaseAudit[test]'
python -m pytest repoReleaseAudit/tests -q
```

MIT License。
