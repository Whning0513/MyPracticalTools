#!/usr/bin/env python3
"""Build a content-free activity summary from Codex session JSONL files."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence


SCHEMA_VERSION = 1

CATEGORY_PATTERNS: dict[str, tuple[str, ...]] = {
    "agent-and-tooling": (
        r"\bagent\b", r"tool[- ]?call", r"\bmcp\b", r"\bcodex\b", r"deepseek", r"skill",
        r"智能体", r"工具调用",
    ),
    "github-contributions": (
        r"github", r"pull request", r"\bpr\b", r"maintainer", r"review", r"\bci\b",
        r"issue", r"贡献", r"维护者",
    ),
    "testing-and-debugging": (
        r"pytest", r"unittest", r"test", r"traceback", r"debug", r"regression",
        r"测试", r"报错", r"调试", r"回归",
    ),
    "remote-compute": (
        r"\bssh\b", r"\ba100\b", r"\bgpu\b", r"cuda", r"vllm", r"model server",
        r"服务器", r"显卡", r"远程",
    ),
    "experiment-operations": (
        r"monitor", r"watchdog", r"checkpoint", r"resume", r"progress", r"experiment",
        r"监控", r"断点", r"恢复", r"实验",
    ),
    "data-and-artifacts": (
        r"dataset", r"jsonl", r"manifest", r"sha-?256", r"artifact", r"archive", r"backup",
        r"数据集", r"清单", r"哈希", r"归档", r"备份",
    ),
    "environment-and-config": (
        r"\bpip\b", r"conda", r"dependenc", r"environment", r"config", r"proxy", r"toml",
        r"依赖", r"环境", r"配置", r"代理",
    ),
    "documentation-and-release": (
        r"readme", r"documentation", r"\bdocs?\b", r"release", r"publish", r"deploy",
        r"website", r"github pages", r"文档", r"发布", r"上传", r"网页",
    ),
    "downloads-and-transfer": (
        r"download", r"\bwget\b", r"\bcurl\b", r"aria2", r"transfer", r"下载", r"传输",
    ),
    "numerical-computing": (
        r"numerical", r"scipy", r"numpy", r"optimization", r"trajectory", r"solver",
        r"数值", r"优化", r"轨道", r"求解器",
    ),
    "reports-and-figures": (
        r"paper", r"report", r"latex", r"\bpdf\b", r"figure", r"plot", r"论文", r"报告", r"图表",
    ),
}

COMPILED_CATEGORIES = {
    name: tuple(re.compile(pattern, re.IGNORECASE) for pattern in patterns)
    for name, patterns in CATEGORY_PATTERNS.items()
}

INJECTED_BLOCKS = (
    re.compile(r"<environment_context>.*?</environment_context>", re.IGNORECASE | re.DOTALL),
    re.compile(r"<codex_internal_context(?:\s+[^>]*)?>.*?</codex_internal_context>", re.IGNORECASE | re.DOTALL),
    re.compile(
        r"# AGENTS\.md instructions for[^\n]*\n\s*<INSTRUCTIONS>.*?</INSTRUCTIONS>",
        re.IGNORECASE | re.DOTALL,
    ),
)


@dataclass
class SourceStats:
    label: str
    files: int = 0
    bytes: int = 0
    records: int = 0
    malformed_records: int = 0
    sessions: int = 0


@dataclass
class AuditResult:
    schema_version: int = SCHEMA_VERSION
    privacy: str = (
        "The report omits message text, command arguments, tool output, working directories, "
        "hostnames, account names, and credentials."
    )
    sources: list[SourceStats] = field(default_factory=list)
    first_timestamp: str | None = None
    last_timestamp: str | None = None
    user_messages: int = 0
    assistant_messages: int = 0
    tool_calls: int = 0
    category_sessions: Counter[str] = field(default_factory=Counter)
    category_messages: Counter[str] = field(default_factory=Counter)
    tools: Counter[str] = field(default_factory=Counter)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "privacy": self.privacy,
            "sources": [asdict(source) for source in self.sources],
            "summary": {
                "files": sum(source.files for source in self.sources),
                "bytes": sum(source.bytes for source in self.sources),
                "records": sum(source.records for source in self.sources),
                "malformed_records": sum(source.malformed_records for source in self.sources),
                "sessions": sum(source.sessions for source in self.sources),
                "first_timestamp": self.first_timestamp,
                "last_timestamp": self.last_timestamp,
                "user_messages": self.user_messages,
                "assistant_messages": self.assistant_messages,
                "tool_calls": self.tool_calls,
            },
            "categories": [
                {
                    "name": name,
                    "sessions": sessions,
                    "user_messages": self.category_messages[name],
                }
                for name, sessions in self.category_sessions.most_common()
            ],
            "tools": [
                {"name": name, "calls": calls}
                for name, calls in self.tools.most_common()
            ],
        }


def discover_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path] if path.suffix == ".jsonl" else []
    sessions = path / "sessions" if (path / "sessions").is_dir() else path
    if not sessions.is_dir():
        return []
    return sorted(item for item in sessions.rglob("*.jsonl") if item.is_file())


def message_text(payload: dict[str, object]) -> str:
    content = payload.get("content")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        legacy_text = payload.get("text")
        return legacy_text if isinstance(legacy_text, str) else ""
    parts: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        text = item.get("text")
        if isinstance(text, str):
            parts.append(text)
    return "\n".join(parts)


def matched_categories(text: str) -> set[str]:
    return {
        name
        for name, patterns in COMPILED_CATEGORIES.items()
        if any(pattern.search(text) for pattern in patterns)
    }


def user_request_text(payload: dict[str, object]) -> str:
    text = message_text(payload)
    for pattern in INJECTED_BLOCKS:
        text = pattern.sub("", text)
    return text


def _parse_timestamp(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _timestamp_before(left: str, right: str) -> bool:
    left_parsed = _parse_timestamp(left)
    right_parsed = _parse_timestamp(right)
    if left_parsed is not None and right_parsed is not None:
        return left_parsed < right_parsed
    return left < right


def update_timestamp(result: AuditResult, value: object) -> None:
    if not isinstance(value, str) or not value:
        return
    if result.first_timestamp is None or _timestamp_before(value, result.first_timestamp):
        result.first_timestamp = value
    if result.last_timestamp is None or _timestamp_before(result.last_timestamp, value):
        result.last_timestamp = value


def audit_source(path: Path, label: str, result: AuditResult) -> SourceStats:
    files = discover_files(path)
    stats = SourceStats(label=label, files=len(files), bytes=sum(item.stat().st_size for item in files))
    for session_file in files:
        stats.sessions += 1
        session_categories: set[str] = set()
        try:
            handle = session_file.open("r", encoding="utf-8", errors="replace")
        except OSError:
            stats.malformed_records += 1
            continue
        with handle:
            for line in handle:
                stats.records += 1
                if '"response_item"' not in line and '"session_meta"' not in line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    stats.malformed_records += 1
                    continue
                update_timestamp(result, record.get("timestamp"))
                payload = record.get("payload")
                if not isinstance(payload, dict):
                    continue
                if record.get("type") == "session_meta":
                    update_timestamp(result, payload.get("timestamp"))
                    continue
                payload_type = payload.get("type")
                if payload_type == "message":
                    role = payload.get("role")
                    if role == "user":
                        result.user_messages += 1
                        categories = matched_categories(user_request_text(payload))
                        session_categories.update(categories)
                        result.category_messages.update(categories)
                    elif role == "assistant":
                        result.assistant_messages += 1
                elif payload_type in {"function_call", "custom_tool_call", "web_search_call", "tool_search_call"}:
                    result.tool_calls += 1
                    name = payload.get("name") or payload_type
                    if isinstance(name, str):
                        result.tools[name] += 1
        result.category_sessions.update(session_categories)
    return stats


def audit(paths: Sequence[Path], labels: Sequence[str] | None = None) -> AuditResult:
    result = AuditResult()
    used_labels = list(labels or ())
    for index, path in enumerate(paths, start=1):
        label = used_labels[index - 1] if index <= len(used_labels) else f"source-{index}"
        result.sources.append(audit_source(path, label, result))
    return result


def render_markdown(data: dict[str, object]) -> str:
    summary = data["summary"]
    assert isinstance(summary, dict)
    lines = [
        "# Codex session audit",
        "",
        str(data["privacy"]),
        "",
        "## Activity",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
    ]
    for key in ("sessions", "files", "bytes", "records", "malformed_records", "user_messages", "assistant_messages", "tool_calls"):
        lines.append(f"| {key.replace('_', ' ')} | {summary[key]} |")
    lines.extend([
        f"| first timestamp | {summary['first_timestamp'] or ''} |",
        f"| last timestamp | {summary['last_timestamp'] or ''} |",
        "",
        "## Repeated work",
        "",
        "| Category | Sessions | User messages |",
        "| --- | ---: | ---: |",
    ])
    for item in data["categories"]:
        lines.append(f"| {item['name']} | {item['sessions']} | {item['user_messages']} |")
    lines.extend(["", "## Tool calls", "", "| Tool | Calls |", "| --- | ---: |"])
    for item in data["tools"][:30]:
        lines.append(f"| `{item['name']}` | {item['calls']} |")
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Summarize Codex session activity without emitting conversation content."
    )
    parser.add_argument("paths", nargs="+", type=Path, help=".codex root, sessions directory, or JSONL file")
    parser.add_argument("--label", action="append", default=[], help="safe source label; repeat in path order")
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    parser.add_argument("--fail-on-malformed", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    data = audit(args.paths, args.label).to_dict()
    if args.format == "json":
        json.dump(data, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(render_markdown(data))
    malformed = data["summary"]["malformed_records"]
    return 2 if args.fail_on_malformed and malformed else 0


if __name__ == "__main__":
    raise SystemExit(main())
