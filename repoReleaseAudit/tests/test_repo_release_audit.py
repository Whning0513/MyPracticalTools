from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "repo_release_audit.py"
SPEC = importlib.util.spec_from_file_location("repo_release_audit", MODULE_PATH)
assert SPEC and SPEC.loader
audit_module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = audit_module
SPEC.loader.exec_module(audit_module)


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def init_repo(root: Path) -> None:
    root.mkdir()
    git(root, "init")
    (root / "README.md").write_text("# Test\n\n[missing](missing.md)\n", encoding="utf-8")
    (root / ".gitignore").write_text("*.tmp\n", encoding="utf-8")
    (root / "LICENSE").write_text("test license\n", encoding="utf-8")
    (root / "run.sh").write_text("#!/usr/bin/env bash\necho ok\n", encoding="utf-8")
    token = "ghp_" + "a" * 24
    (root / "settings.txt").write_text(token + "\nC:\\Users\\name\\private\n", encoding="utf-8")
    git(root, "add", "--all")


def test_reports_release_failures_without_secret_text(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    init_repo(root)

    result = audit_module.audit(root)
    codes = {finding["code"] for finding in result["findings"]}

    assert "broken-local-link" in codes
    assert "secret-pattern" in codes
    assert "machine-path" in codes
    assert "missing-executable-bit" in codes
    rendered = audit_module.render_text(result)
    assert "ghp_" not in rendered
    assert "C:\\Users\\name" not in rendered


def test_clean_repo_has_no_errors(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    init_repo(root)
    (root / "README.md").write_text("# Test\n", encoding="utf-8")
    (root / "settings.txt").write_text("mode=safe\n", encoding="utf-8")
    git(root, "add", "--all")
    git(root, "update-index", "--chmod=+x", "run.sh")

    result = audit_module.audit(root)

    assert result["summary"]["errors"] == 0


def test_size_threshold_is_configurable(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    init_repo(root)
    (root / "README.md").write_text("# Test\n", encoding="utf-8")
    (root / "settings.txt").write_text("mode=safe\n", encoding="utf-8")
    (root / "large.bin").write_bytes(b"x" * 2048)
    git(root, "add", "--all")
    git(root, "update-index", "--chmod=+x", "run.sh")

    result = audit_module.audit(root, max_file_mb=0.001)

    assert any(item["code"] == "large-file" for item in result["findings"])


def test_inline_allow_marker_suppresses_reviewed_example(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    init_repo(root)
    (root / "README.md").write_text("# Test\n", encoding="utf-8")
    token = "ghp_" + "a" * 24
    (root / "settings.txt").write_text(
        token + " # release-audit: allow-secret-pattern\n",
        encoding="utf-8",
    )
    git(root, "add", "--all")
    git(root, "update-index", "--chmod=+x", "run.sh")

    result = audit_module.audit(root)

    assert not any(item["code"] == "secret-pattern" for item in result["findings"])


def test_reports_markdown_links_that_escape_the_worktree(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    init_repo(root)
    (tmp_path / "outside.md").write_text("# outside\n", encoding="utf-8")
    (root / "README.md").write_text("[outside](../outside.md)\n", encoding="utf-8")
    git(root, "add", "--all")

    result = audit_module.audit(root)

    assert any(item["code"] == "link-outside-root" for item in result["findings"])
    assert not any(item["code"] == "broken-local-link" for item in result["findings"])
