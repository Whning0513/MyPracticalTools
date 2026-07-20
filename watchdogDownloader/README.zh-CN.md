# watchdogdownloader

[English](README.md) | [简体中文](README.zh-CN.md)

`watchdogdownloader` 是一个小型 Bash 工具，适用于容易遇到长期连接异常的大文件下载。它是 Code-Contests-Plus 下载逻辑的通用版本。

它有意采用保守设计：

- 使用 `curl --continue-at -` 断点续传；
- 低速保护会中止异常的“慢滴式”连接；
- 由外层脚本循环负责重试，不使用 `curl --retry`；
- 下载器通过 `setsid` 启动，不依赖发起它的 shell；
- 当总下载字节数停止增长时，watchdog 可以重启整个下载器进程组；
- 每个文件都有原子写入、持久化的尝试和续传状态；
- 按预期字节数和可选 SHA-256 摘要校验文件；
- 全屏 TUI 展示进度、速度、ETA、worker、重试次数和续传偏移。

## 依赖

`watchdogdownloader` 面向 Linux，需要 Bash、`curl`、`setsid`、`flock`，以及 `readlink`、`stat`、`sha256sum` 等标准 GNU 工具。

## 安装

克隆仓库，并将 `wdd` 安装到 `PATH` 中的目录：

```bash
git clone https://github.com/Whning0513/MyPracticalTools.git
install -Dm755 MyPracticalTools/watchdogDownloader/wdd "$HOME/.local/bin/wdd"
wdd --version
```

也可以直接运行检出目录中的 `watchdogDownloader/wdd`。

## 清单格式

创建制表符分隔的清单：

```text
# URL<TAB>relative-output-path<TAB>expected-bytes<TAB>optional-sha256
https://example.com/a.bin	a.bin	123456	
https://example.com/shards/part-00000.parquet	shards/part-00000.parquet	987654321	
```

规则：

- 第二列是相对于已配置输出目录的路径；
- 应尽量提供精确的 `expected-bytes`；
- 仅当文件大小未知时使用 `0`。此类文件只有在 curl 成功退出后才视为完成；如果没有 SHA-256，仍无法证明其精确大小；
- 第四列是可选的 `sha256`；
- 避免在文件名中使用空格和制表符；
- 拒绝绝对路径和包含 `..` 的路径。

## 基本用法

创建项目：

```bash
wdd init \
  /srv/mydownload-state \
  /srv/mydownload-files \
  /srv/mydownload-state/manifest.tsv
```

启动或恢复下载器和 watchdog：

```bash
wdd resume /srv/mydownload-state
```

打开实时终端界面：

```bash
wdd tui /srv/mydownload-state
```

查看状态：

```bash
wdd status /srv/mydownload-state
```

下载完成后校验：

```bash
wdd verify /srv/mydownload-state
```

暂停并保留已下载的字节：

```bash
wdd pause /srv/mydownload-state
wdd resume /srv/mydownload-state
```

停止 watchdog 和下载器，但不修改部分下载文件：

```bash
wdd stop /srv/mydownload-state
```

需要分别管理两个进程时，仍可使用底层的 `start` 和 `watchdog-start` 命令。

## 终端界面

`wdd tui <project-dir>` 会打开一个响应式、无额外依赖的全屏界面。它读取与下载器相同的持久化状态，不要求自己拥有下载进程。

快捷键：

- `P`：保存续传状态后暂停 watchdog 和下载器；
- `R`：恢复两个进程；
- `V`：按清单运行文件大小和 SHA-256 校验；
- `Q`：仅关闭窗口，下载继续在后台运行。

日志、脚本和 CI 可以渲染一份不带 ANSI 控制码的快照：

```bash
wdd tui /srv/mydownload-state --once
```

## 续传状态

部分下载内容保留在最终输出路径。每次新请求都使用 `curl --continue-at -`，由 curl 根据该文件计算下一个字节偏移。每个文件的状态以原子方式写入：

```text
<project-dir>/.wdd/files/<path-sha256>.state
```

状态记录包括状态值、尝试次数、最近续传偏移、curl 退出码、时间戳和最近一次失败原因。只有满足以下条件，文件才会被标记为 `complete`：

- curl 成功退出；
- 清单提供精确大小时，文件字节数与其一致；
- 清单提供 SHA-256 时，摘要与其一致。

因 `pause`、watchdog 重启、shell 断开或连接失败而停止的文件会保留字节，并在下一次尝试时续传。SHA 不匹配、文件过大，或传输成功但大小不符，都属于终止性错误，会显示为 `failed`，不会无限重试。

如需恢复失败条目，可将当前数据移入带时间戳的隔离目录，并仅清除该条目的状态：

```bash
wdd reset-file /srv/mydownload-state shards/part-00000.parquet
wdd resume /srv/mydownload-state
```

`reset-file` 不会删除旧数据，而会将其移到 `<project-dir>/.wdd/quarantine/` 下供检查。

对于同一 URL 内容可能变化的 HTTP 资源，请在清单中提供 SHA-256。curl 的 ETag 比较模式无法直接与 `--continue-at` 组合，因此摘要是最终的身份校验。远端对象发生变化时，校验会失败，不会被静默接受。

## 配置

`wdd init` 会写入：

```text
<project-dir>/.wdd/config
```

常用配置项：

```bash
JOBS=1
LOW_SPEED_LIMIT=524288
LOW_SPEED_TIME=60
MAX_DOWNLOAD_TIME=1800
CONNECT_TIMEOUT=30
CHECK_INTERVAL=120
STALL_LIMIT=600
BACKOFF_SECONDS=10
```

建议值：

- 对主动限速或严格限制请求频率的主机，保持 `JOBS=1`；
- 从稳定主机下载许多独立文件时，可使用 `JOBS=2` 或 `JOBS=4`；
- 如果希望连接连续一分钟低于 512 KiB/s 时中止，保持 `LOW_SPEED_LIMIT=524288` 和 `LOW_SPEED_TIME=60`；
- 单个文件很大且连接稳定时，可以增大 `MAX_DOWNLOAD_TIME`。

## 为什么不使用 `curl --retry`

`curl --retry` 适用于许多场景，但对可续传的大文件而言，它会让控制流更难观察。本工具让一个 `curl` 进程只负责持续下载、触发低速保护、失败或完成。随后，外层循环检查本地文件大小，并发起一次新的续传请求。

这种循环更容易检查，也更适合下载进程可能被 watchdog 终止的场景。

## Watchdog 行为

watchdog 每隔 `CHECK_INTERVAL` 秒检查一次总下载字节数。

满足以下条件时会重启下载器：

- 下载器 PID 不存在；
- 总字节数在 `STALL_LIMIT` 秒内没有增加；
- 文件集合尚未全部完成。

它会终止下载器的整个进程组，而不只是直接父进程。这样可以避免旧 `curl` 子进程在新下载器启动后继续写文件。

显式执行 `wdd pause` 会创建暂停标记并停止两个进程组，因此 watchdog 不会把主动暂停误判为下载卡死。

## 并行下载

在 `.wdd/config` 中设置 `JOBS`：

```bash
JOBS=4
```

每个 worker 会占用不同的清单条目，不会主动同时写入同一文件。如果 worker 退出，其他 worker 发现其所有者 PID 已不存在时，会清理过期的占用状态。

并行只适用于相互独立的文件，不要用它拆分单个文件。

## Code-Contests-Plus 示例

仓库中包含一份示例清单：

```text
watchdogDownloader/examples/ccplus_1x.manifest.tsv
```

为该数据集创建一个新的通用项目：

```bash
wdd init \
  /srv/codecontestplus-state \
  /srv/codecontestplus-files \
  ./watchdogDownloader/examples/ccplus_1x.manifest.tsv
```

## 开发

运行语法检查和端到端中断测试：

```bash
bash -n watchdogDownloader/wdd
python -m unittest discover -s watchdogDownloader/tests -v
```

集成测试使用一个本地 HTTP 服务器，在写入部分文件后主动断开第一次响应。测试会断言下一次请求使用非零字节范围，并校验最终 SHA-256 正确。

## 许可证

watchdogDownloader 使用 [MIT License](LICENSE)。
