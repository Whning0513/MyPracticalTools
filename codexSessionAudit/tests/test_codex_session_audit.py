from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "codex_session_audit.py"
SPEC = importlib.util.spec_from_file_location("codex_session_audit", MODULE_PATH)
assert SPEC and SPEC.loader
audit_module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = audit_module
SPEC.loader.exec_module(audit_module)


def write_session(path: Path) -> None:
    records = [
        {
            "timestamp": "2026-08-01T00:00:00Z",
            "type": "session_meta",
            "payload": {"id": "private-id", "cwd": "/secret/project"},
        },
        {
            "timestamp": "2026-08-01T00:01:00Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "Fix a GitHub PR test failure on A100"}],
            },
        },
        {
            "timestamp": "2026-08-01T00:02:00Z",
            "type": "response_item",
            "payload": {"type": "function_call", "name": "exec_command", "arguments": "secret"},
        },
        {
            "timestamp": "2026-08-01T00:03:00Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "private response"}],
            },
        },
    ]
    path.parent.mkdir(parents=True)
    path.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")


def test_audit_counts_without_exposing_content(tmp_path: Path) -> None:
    session = tmp_path / ".codex" / "sessions" / "2026" / "08" / "one.jsonl"
    write_session(session)

    result = audit_module.audit([tmp_path / ".codex"], ["workstation"]).to_dict()

    assert result["summary"]["sessions"] == 1
    assert result["summary"]["user_messages"] == 1
    assert result["summary"]["assistant_messages"] == 1
    assert result["summary"]["tool_calls"] == 1
    assert result["tools"] == [{"name": "exec_command", "calls": 1}]
    categories = {item["name"] for item in result["categories"]}
    assert {"github-contributions", "testing-and-debugging", "remote-compute"} <= categories

    rendered = json.dumps(result)
    assert "private-id" not in rendered
    assert "/secret/project" not in rendered
    assert "secret" not in rendered
    assert "Fix a GitHub" not in rendered


def test_markdown_omits_paths_and_message_text(tmp_path: Path) -> None:
    session = tmp_path / "sessions" / "one.jsonl"
    write_session(session)
    data = audit_module.audit([tmp_path], ["gpu-node"]).to_dict()

    report = audit_module.render_markdown(data)

    assert "Codex session audit" in report
    assert str(tmp_path) not in report
    assert "Fix a GitHub" not in report


def test_audit_reads_legacy_message_text(tmp_path: Path) -> None:
    session = tmp_path / ".codex" / "sessions" / "2026" / "06" / "legacy.jsonl"
    session.parent.mkdir(parents=True)
    records = [
        {
            "timestamp": "2026-06-01T00:00:00Z",
            "type": "session_meta",
            "payload": {"id": "private-id"},
        },
        {
            "timestamp": "2026-06-01T00:01:00Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "text": "resume an experiment checkpoint",
            },
        },
    ]
    session.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )

    result = audit_module.audit([tmp_path / ".codex"], ["legacy"]).to_dict()

    assert result["summary"]["user_messages"] == 1
    categories = {item["name"] for item in result["categories"]}
    assert "experiment-operations" in categories


def test_malformed_candidate_can_fail_cli(tmp_path: Path, capsys) -> None:
    session = tmp_path / "sessions" / "broken.jsonl"
    session.parent.mkdir(parents=True)
    session.write_text('{"type":"response_item"\n', encoding="utf-8")

    code = audit_module.main([str(tmp_path), "--format", "json", "--fail-on-malformed"])

    assert code == 2
    output = json.loads(capsys.readouterr().out)
    assert output["summary"]["malformed_records"] == 1


def test_injected_context_does_not_change_categories() -> None:
    payload = {
        "content": [
            {
                "type": "input_text",
                "text": (
                    "Write a short note.\n"
                    "<environment_context><cwd>/secret</cwd><config>private</config></environment_context>"
                ),
            }
        ]
    }

    text = audit_module.user_request_text(payload)

    assert "secret" not in text
    assert "config" not in text
    assert "environment-and-config" not in audit_module.matched_categories(text)


def test_timestamps_are_ordered_by_instant_across_timezones() -> None:
    result = audit_module.AuditResult()

    audit_module.update_timestamp(result, "2026-08-01T00:30:00+02:00")
    audit_module.update_timestamp(result, "2026-07-31T23:00:00Z")

    assert result.first_timestamp == "2026-08-01T00:30:00+02:00"
    assert result.last_timestamp == "2026-07-31T23:00:00Z"
