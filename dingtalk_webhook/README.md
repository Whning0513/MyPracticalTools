# DingTalk Webhook

向钉钉机器人发送通知消息。

## 快速使用

其他项目只需两行代码即可发消息到钉钉：

```python
from dingtalk_webhook.client import notify, send_text, send_markdown

# 发送格式化通知（推荐）
notify(sender="a/b/c", content="任务执行完毕")
```

钉钉收到:

```
发送者: a/b/c
时间: 14:30:25
内容: 任务执行完毕
```

`sender` 格式约定为 `项目/模块/进程名`，其中 `c`（最后一段）为调用方进程名。

## 其他消息类型

```python
# 纯文本
send_text("Hello")

# Markdown
send_markdown(title="通知", text="# 构建通过\n**分支**: main")

# 链接卡片
send_link(title="Google", text="搜索引擎", message_url="https://google.com")
```

## HTTP 调用

启动服务：

```bash
cd /data/whn/programfiles
python -m dingtalk_webhook.main
```

服务默认监听 `0.0.0.0:8000`。

```bash
curl -X POST http://localhost:8000/notify \
  -H "Content-Type: application/json" \
  -d '{"sender": "a/b/c", "content": "Hello"}'

curl -X POST http://localhost:8000/send/text \
  -H "Content-Type: application/json" \
  -d '{"content": "Hello"}'

curl -X POST http://localhost:8000/send/markdown \
  -H "Content-Type: application/json" \
  -d '{"title": "通知", "text": "# 构建通过"}'
```

## 环境变量

可在调用方覆盖 Token 和 Secret，用于不同场景使用不同机器人：

```python
import os
os.environ["DINGTALK_ACCESS_TOKEN"] = "your_token"
os.environ["DINGTALK_SECRET"] = "your_secret"

from dingtalk_webhook.client import notify
notify(sender="a/b/c", content="Hello")
```

必须通过 `DINGTALK_ACCESS_TOKEN` 和 `DINGTALK_SECRET` 提供凭证。仓库不包含默认凭证。

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/notify` | 格式化通知（含发送者、时间、内容） |
| POST | `/send/text` | 发送文本 |
| POST | `/send/markdown` | 发送 Markdown |
| POST | `/send/link` | 发送链接卡片 |
| GET | `/health` | 健康检查 |

## Claude Code Bridge

从钉钉群与终端里的 Claude Code 交互。@bot 发消息 → CC 执行 → 结果回帖到群里。

### 启动桥接

```bash
cd /data/whn/programfiles
python -m dingtalk_webhook.bridge
```

服务监听 `0.0.0.0:8001`。

### 暴露公网

```bash
ngrok http 8001
# 或使用 frp 等其他隧道工具
```

### 配置钉钉出向 Webhook

1. 在钉钉群设置 → 机器人 → 出向 Webhook
2. 回调 URL 填 `https://<你的公网地址>/callback`
3. 在群里 @机器人 发送消息即可

### 工作原理

```
@bot 消息 → 钉钉 POST /callback → bridge 后台执行 claude -p → 结果发回群
```

### 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DINGTALK_ACCESS_TOKEN` | (必填) | 机器人 token |
| `DINGTALK_SECRET` | (必填) | 机器人 secret |
| `CC_TIMEOUT` | 180 | CC 查询超时秒数 |
| `CC_MAX_RESPONSE_LENGTH` | 18000 | 回复最大字符数 |

### API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/callback` | 钉钉出向 Webhook 回调 |
| GET | `/health` | 健康检查 |

## Telegram Bot Bridge

无需公网地址、无需 ngrok，通过 Telegram Bot 与 CC 交互。

### 创建 Bot

Telegram 搜 @BotFather，发 `/newbot`，按要求取名，拿到 token。

### 启动

```bash
export TELEGRAM_BOT_TOKEN="你的token"
export TELEGRAM_PROXY="http://127.0.0.1:7890"   # 如果需要代理
CC_MODE=print python -m dingtalk_webhook.telegram_bridge

# 有状态模式（上下文持续保留）
CC_MODE=tmux python -m dingtalk_webhook.telegram_bridge
```

### 工作原理

```
手机 Telegram → @bot 发消息 → polling 拉到 → claude -p/tmux → 回复到 Telegram
```

### 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `TELEGRAM_BOT_TOKEN` | (必填) | BotFather 给的 token |
| `TELEGRAM_PROXY` | (空) | HTTP 代理地址 |
| `CC_MODE` | print | print 或 tmux |
| `CC_TIMEOUT` | 180 | CC 查询超时秒数 |
| `TELEGRAM_OFFSET_FILE` | `~/.cache/dingtalk-webhook/telegram-offset` | 保存已处理的 update offset，避免重启后重复处理 |
