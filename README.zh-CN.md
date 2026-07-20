# MyPracticalTools

[English](README.md) | [简体中文](README.zh-CN.md)

[![CI](https://github.com/Whning0513/MyPracticalTools/actions/workflows/ci.yml/badge.svg)](https://github.com/Whning0513/MyPracticalTools/actions/workflows/ci.yml)

这是一个面向长期运行的机器学习、数据处理和自动化工作流的小型实用工具与参考资源集合。

每个工具都有独立文档和明确的使用边界，可以单独安装或复制，不需要采用仓库中的其他部分。

## 包含的项目

| 项目 | 运行环境 | 用途 |
| --- | --- | --- |
| [Practical Run Dashboard](dashboard/README.zh-CN.md) | Python 3.10+ | 面向带检查点训练与评测任务的只读终端仪表盘，显示进度、ETA、GPU 使用情况和可恢复状态。 |
| [watchdogDownloader](watchdogDownloader/README.zh-CN.md) | Linux Bash | 支持续传的清单式下载工具，具有低速检测、进程监管以及文件大小或 SHA-256 校验。 |
| [ACA small v0.2](datasets/ACA_small_v0.2/) | Zstandard JSONL | 带 manifest、盲测门控元数据和审计报告的版本化训练/测试数据包。 |
| [数据集设计说明](docs/dataset-and-datapackage-design.zh-CN.md) | Markdown | 说明 ACA 数据包的可复现性、切分隔离、重放、validator、reference 和发布要求。 |
| [用户工作方式 skill](whn_skill/whn_skill.zh-CN.md) | Markdown | 用于证据驱动的编码、研究和技术沟通的 Codex skill。 |

## 快速开始

### Practical Run Dashboard

直接从本仓库安装：

```bash
python -m pip install \
  "git+https://github.com/Whning0513/MyPracticalTools.git#subdirectory=dashboard"
```

复制并修改示例配置，然后启动实时终端界面：

```bash
practical-dashboard --config dashboard/examples/aca-rl-matrix.json
```

JSON 输出、检查点语义、GPU 归属和状态文件格式见[仪表盘文档](dashboard/README.zh-CN.md)。

### watchdogDownloader

将脚本安装到 `PATH` 中的目录：

```bash
git clone https://github.com/Whning0513/MyPracticalTools.git
install -Dm755 MyPracticalTools/watchdogDownloader/wdd "$HOME/.local/bin/wdd"
wdd --help
```

创建制表符分隔的清单，初始化下载项目并启动：

```bash
wdd init /srv/download-state /srv/files ./manifest.tsv
wdd resume /srv/download-state
wdd tui /srv/download-state
```

清单格式、重试行为、校验和调优参数见 [watchdogDownloader 文档](watchdogDownloader/README.zh-CN.md)。

## 数据包

`datasets/ACA_small_v0.2/` 包含压缩后的训练/测试题目和提交。请将 `manifest.json` 作为版本化事实来源，并在使用数据包前检查 `audit_report.json`。配套的[设计文档](docs/dataset-and-datapackage-design.zh-CN.md)明确区分冻结的基准证据、重放输出、构造 reference、validator 和 blind probe。

## 开发

运行 Python 测试：

```bash
python -m pip install -e './dashboard[test]'
python -m pytest dashboard/tests -q
```

检查 Bash 脚本及其中断/续传集成测试：

```bash
bash -n watchdogDownloader/wdd
watchdogDownloader/wdd --version
python -m unittest discover -s watchdogDownloader/tests -v
```

CI 会在 pull request 和 `main` 分支变更时运行这两组检查。

## 许可证

Practical Run Dashboard、watchdogDownloader 和用户工作方式 skill 等原创软件组件使用 [MIT License](LICENSE)。数据包、数据设计材料和任何第三方内容不在此许可范围内，除非另行标明许可证。准确的路径范围见 [`LICENSE_SCOPE.md`](LICENSE_SCOPE.md)，中文便览见 [`LICENSE_SCOPE.zh-CN.md`](LICENSE_SCOPE.zh-CN.md)。

## 贡献

欢迎提交目标明确的错误报告和 pull request。请提供最小复现，说明行为变化，并列出验证命令。不要提交凭据、私有数据集、生成的缓存或机器相关的绝对路径。
