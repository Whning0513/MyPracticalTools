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


def test_symlinks_are_reported_without_scanning_their_targets(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    init_repo(root)
    outside = tmp_path / "private.txt"
    outside.write_text("ghp_" + "a" * 24, encoding="utf-8")
    link = root / "linked.txt"
    try:
        link.symlink_to(outside)
    except OSError as error:
        import pytest

        pytest.skip(f"symbolic links are unavailable: {error}")
    git(root, "add", "linked.txt")

    result = audit_module.audit(root)
    findings = result["findings"]

    assert any(item["code"] == "symlink" and item["path"] == "linked.txt" for item in findings)
    assert not any(item["code"] == "secret-pattern" and item["path"] == "linked.txt" for item in findings)


def test_dangling_tracked_symlink_is_not_reported_missing(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    init_repo(root)
    link = root / "dangling.txt"
    try:
        link.symlink_to(tmp_path / "missing-target.txt")
    except OSError as error:
        import pytest

        pytest.skip(f"symbolic links are unavailable: {error}")
    git(root, "add", "dangling.txt")

    result = audit_module.audit(root)
    findings = result["findings"]

    assert any(item["code"] == "symlink" and item["path"] == "dangling.txt" for item in findings)
    assert not any(item["code"] == "missing-tracked-file" and item["path"] == "dangling.txt" for item in findings)


def test_unreadable_text_is_reported_without_exposing_content(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "repo"
    init_repo(root)
    target = root / "settings.txt"
    original = Path.read_text

    def deny_target(path: Path, *args, **kwargs):
        if path == target:
            raise PermissionError("private details")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", deny_target)
    result = audit_module.audit(root)
    assert any(item["code"] == "unreadable-text" and item["path"] == "settings.txt" for item in result["findings"])
    assert "private details" not in audit_module.render_text(result)


def test_invalid_utf8_text_is_not_silently_skipped(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    init_repo(root)
    (root / "invalid.txt").write_bytes(b"\xff\xfe")
    git(root, "add", "invalid.txt")
    result = audit_module.audit(root)
    assert any(item["code"] == "unreadable-text" and item["path"] == "invalid.txt" for item in result["findings"])


def test_git_status_failure_is_not_reported_as_clean(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "repo"
    init_repo(root)
    original = audit_module.run_git

    def run_git_with_failed_status(root: Path, *args: str):
        if args == ("status", "--porcelain"):
            return subprocess.CompletedProcess(args, 1, stdout=b"", stderr=b"private git error")
        return original(root, *args)

    monkeypatch.setattr(audit_module, "run_git", run_git_with_failed_status)
    result = audit_module.audit(root)
    assert result["summary"]["dirty"] is True
    assert any(item["code"] == "git-status-failed" and item["level"] == "error" for item in result["findings"])
    assert "private git error" not in audit_module.render_text(result)


def test_oversized_text_is_reported_as_not_scanned(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    init_repo(root)
    (root / "large.txt").write_bytes(b"x" * (2 * 1024 * 1024 + 1))
    git(root, "add", "large.txt")
    result = audit_module.audit(root)
    assert any(item["code"] == "text-too-large-to-scan" and item["path"] == "large.txt" and item["level"] == "error" for item in result["findings"])


def test_worktree_symlink_is_not_scanned_when_index_has_regular_file(tmp_path: Path, monkeypatch) -> None:
    import stat
    from types import SimpleNamespace

    root = tmp_path / "repo"
    init_repo(root)
    target = root / "settings.txt"
    original_lstat = Path.lstat
    original_read = Path.read_text

    def link_lstat(path: Path):
        if path == target:
            return SimpleNamespace(st_mode=stat.S_IFLNK, st_size=1)
        return original_lstat(path)

    def no_link_reads(path: Path, *args, **kwargs):
        assert path != target
        return original_read(path, *args, **kwargs)

    monkeypatch.setattr(Path, "lstat", link_lstat)
    monkeypatch.setattr(Path, "read_text", no_link_reads)
    result = audit_module.audit(root)
    assert any(item["code"] == "symlink" and item["path"] == "settings.txt" for item in result["findings"])


def test_unstaged_symlink_does_not_read_outside_target(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    init_repo(root)
    outside = tmp_path / "outside.txt"
    outside.write_text("ghp_" + "b" * 24, encoding="utf-8")
    target = root / "settings.txt"
    target.unlink()
    try:
        target.symlink_to(outside)
    except OSError as error:
        import pytest
        pytest.skip(f"symlinks unavailable: {error}")
    result = audit_module.audit(root)
    assert any(item["code"] == "symlink" and item["path"] == "settings.txt" for item in result["findings"])
    assert not any(item["code"] == "secret-pattern" and item["path"] == "settings.txt" for item in result["findings"])


def test_symlinked_ancestor_is_not_scanned(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "repo"
    init_repo(root)
    directory = root / "nested"
    directory.mkdir()
    target = directory / "tracked.txt"
    target.write_text("ghp_" + "b" * 24, encoding="utf-8")
    git(root, "add", "nested/tracked.txt")
    original = Path.is_symlink
    monkeypatch.setattr(Path, "is_symlink", lambda path: path == directory or original(path))
    result = audit_module.audit(root)
    assert any(item["code"] == "symlink-ancestor" and item["path"] == "nested/tracked.txt" for item in result["findings"])
    assert not any(item["code"] == "secret-pattern" and item["path"] == "nested/tracked.txt" for item in result["findings"])


def test_real_ancestor_symlink_is_not_followed(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    init_repo(root)
    directory = root / "nested"
    directory.mkdir()
    target = directory / "tracked.txt"
    target.write_text("safe", encoding="utf-8")
    git(root, "add", "nested/tracked.txt")
    target.unlink()
    directory.rmdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "tracked.txt").write_text("ghp_" + "c" * 24, encoding="utf-8")
    try:
        directory.symlink_to(outside, target_is_directory=True)
    except OSError as error:
        import pytest
        pytest.skip(f"symlinks unavailable: {error}")
    result = audit_module.audit(root)
    assert any(item["code"] == "symlink-ancestor" and item["path"] == "nested/tracked.txt" for item in result["findings"])
    assert not any(item["code"] == "secret-pattern" and item["path"] == "nested/tracked.txt" for item in result["findings"])
