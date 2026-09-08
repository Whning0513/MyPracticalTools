# Codex 会话审计器

`codex-session-audit` 流式读取 Codex 会话 JSONL，统计活动量、重复任务类别和工具调用频率。报告不会包含聊天正文、命令参数、工具输出、工作目录、主机名、账号或凭据。

它适合在整理 `.codex/sessions` 存档前回答两个问题：记录有多少，以及哪些重复操作值得写成脚本。

## 安装和运行

```bash
python -m pip install './codexSessionAudit'
codex-session-audit ~/.codex --label workstation
```

多台机器可以输出 JSON 后再比较：

```bash
codex-session-audit ~/.codex --label gpu-node --format json > session-audit.json
```

输入可以是 `.codex` 根目录、`sessions` 目录、单个 JSONL 文件或多个路径。报告只显示你提供的安全标签，不显示源路径。

## 隐私边界

程序只在内存中读取用户消息，用固定词表匹配任务类别，最后保存计数。它不会保存摘录，也不会把关键词命中关联到会话 ID。

程序忽略工具参数和工具输出，只统计函数名。

## 开发

```bash
python -m pip install -e './codexSessionAudit[test]'
python -m pytest codexSessionAudit/tests -q
```

MIT License。
