from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).resolve().parents[1] / "artifact_manifest.py"
SPEC = importlib.util.spec_from_file_location("artifact_manifest", MODULE_PATH)
assert SPEC and SPEC.loader
artifact_manifest = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = artifact_manifest
SPEC.loader.exec_module(artifact_manifest)


def test_create_is_sorted_and_does_not_include_itself(tmp_path: Path) -> None:
    root = tmp_path / "artifact"
    (root / "nested").mkdir(parents=True)
    (root / "z.txt").write_text("last\n", encoding="utf-8")
    (root / "nested" / "a.json").write_text('{"ok": true}\n', encoding="utf-8")
    manifest_path = root / "manifest.json"

    payload = artifact_manifest.create_manifest(root, manifest_path)

    assert [item["path"] for item in payload["files"]] == [
        "nested/a.json",
        "z.txt",
    ]
    assert payload["files"][0]["media_type"] == "application/json"
    assert payload["files"][1]["media_type"] == "text/plain"
    assert artifact_manifest.verify_manifest(root, manifest_path) == []


def test_verify_reports_missing_changed_and_unexpected_files(tmp_path: Path) -> None:
    root = tmp_path / "artifact"
    root.mkdir()
    (root / "data.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    (root / "keep.txt").write_text("keep\n", encoding="utf-8")
    manifest_path = tmp_path / "manifest.json"
    artifact_manifest.create_manifest(root, manifest_path)

    (root / "data.csv").write_text("a,b\n9,9\n", encoding="utf-8")
    (root / "keep.txt").unlink()
    (root / "new.txt").write_text("new\n", encoding="utf-8")

    assert artifact_manifest.verify_manifest(root, manifest_path) == [
        "changed: data.csv (sha256 differs)",
        "missing: keep.txt",
        "unexpected: new.txt",
    ]


def test_exclude_patterns_are_applied_during_create_and_verify(tmp_path: Path) -> None:
    root = tmp_path / "artifact"
    root.mkdir()
    (root / "data.txt").write_text("data\n", encoding="utf-8")
    (root / "scratch.tmp").write_text("temporary\n", encoding="utf-8")
    manifest_path = tmp_path / "manifest.json"

    artifact_manifest.create_manifest(root, manifest_path, excludes=["*.tmp"])
    (root / "scratch.tmp").write_text("changed temporary\n", encoding="utf-8")

    assert artifact_manifest.verify_manifest(root, manifest_path, excludes=["*.tmp"]) == []
    assert artifact_manifest.verify_manifest(root, manifest_path) == [
        "unexpected: scratch.tmp",
    ]


def test_invalid_paths_and_duplicate_entries_are_rejected(tmp_path: Path) -> None:
    root = tmp_path / "artifact"
    root.mkdir()
    (root / "data.txt").write_text("data\n", encoding="utf-8")
    manifest_path = tmp_path / "bad.json"

    base = {
        "schema_version": 1,
        "root": ".",
        "files": [
            {
                "path": "../outside.txt",
                "bytes": 1,
                "sha256": "0" * 64,
                "media_type": "text/plain",
            }
        ],
    }
    manifest_path.write_text(json.dumps(base), encoding="utf-8")
    with pytest.raises(artifact_manifest.ManifestError, match="escapes root"):
        artifact_manifest.verify_manifest(root, manifest_path)

    base["files"] = [
        {
            "path": "data.txt",
            "bytes": 5,
            "sha256": "0" * 64,
            "media_type": "text/plain",
        },
        {
            "path": "data.txt",
            "bytes": 5,
            "sha256": "0" * 64,
            "media_type": "text/plain",
        },
    ]
    manifest_path.write_text(json.dumps(base), encoding="utf-8")
    with pytest.raises(artifact_manifest.ManifestError, match="duplicate"):
        artifact_manifest.verify_manifest(root, manifest_path)


def test_cli_exit_codes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = tmp_path / "artifact"
    root.mkdir()
    (root / "data.txt").write_text("data\n", encoding="utf-8")
    manifest_path = tmp_path / "manifest.json"

    assert artifact_manifest.main(["create", str(root), str(manifest_path)]) == 0
    assert "created" in capsys.readouterr().out
    assert artifact_manifest.main(["verify", str(root), str(manifest_path)]) == 0
    assert "OK" in capsys.readouterr().out

    (root / "data.txt").write_text("changed\n", encoding="utf-8")
    assert artifact_manifest.main(["verify", str(root), str(manifest_path)]) == 1
    assert "ERROR changed: data.txt" in capsys.readouterr().out


def test_manifest_symlink_is_rejected_before_it_can_overwrite_target(tmp_path: Path) -> None:
    root = tmp_path / "artifact"
    root.mkdir()
    (root / "data.txt").write_text("data\n", encoding="utf-8")
    target = tmp_path / "outside.json"
    target.write_text("keep me\n", encoding="utf-8")
    manifest_path = root / "manifest.json"
    try:
        manifest_path.symlink_to(target)
    except OSError as error:
        pytest.skip(f"symbolic links are unavailable: {error}")

    with pytest.raises(artifact_manifest.ManifestError, match="must not be a symbolic link"):
        artifact_manifest.create_manifest(root, manifest_path)
    assert target.read_text(encoding="utf-8") == "keep me\n"

    with pytest.raises(artifact_manifest.ManifestError, match="must not be a symbolic link"):
        artifact_manifest.verify_manifest(root, manifest_path)


def test_create_manifest_fails_when_os_walk_skips_unreadable_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "artifact"
    root.mkdir()
    (root / "readable.txt").write_text("readable\n", encoding="utf-8")
    manifest_path = root / "manifest.json"
    unreadable = root / "private"

    def walk_with_error(path, *, topdown, followlinks, onerror=None):
        if onerror is not None:
            onerror(PermissionError(13, "Permission denied", str(unreadable)))
        return iter(())

    monkeypatch.setattr(artifact_manifest.os, "walk", walk_with_error)

    with pytest.raises(artifact_manifest.ManifestError, match="cannot read directory"):
        artifact_manifest.create_manifest(root, manifest_path)
    assert not manifest_path.exists()


def test_special_file_is_rejected_before_hashing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import stat
    from types import SimpleNamespace

    root = tmp_path / "artifact"
    root.mkdir()
    target = root / "pipe"
    target.write_text("placeholder", encoding="utf-8")
    original_lstat = Path.lstat

    def fake_lstat(path: Path):
        if path == target:
            return SimpleNamespace(st_mode=stat.S_IFIFO)
        return original_lstat(path)

    monkeypatch.setattr(Path, "lstat", fake_lstat)
    with pytest.raises(artifact_manifest.ManifestError, match="not a regular file: pipe"):
        artifact_manifest.collect_files(root)
    assert artifact_manifest.collect_files(root, excludes=["pipe"]) == []


@pytest.mark.skipif(not hasattr(__import__("os"), "mkfifo"), reason="named pipes unavailable")
def test_named_pipe_does_not_block_manifest_creation(tmp_path: Path) -> None:
    import os

    root = tmp_path / "artifact"
    root.mkdir()
    os.mkfifo(root / "pipe")
    with pytest.raises(artifact_manifest.ManifestError, match="not a regular file: pipe"):
        artifact_manifest.collect_files(root)


def test_invalid_utf8_manifest_reports_error_without_traceback(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = tmp_path / "artifact"
    root.mkdir()
    manifest = tmp_path / "invalid.json"
    manifest.write_bytes(b"\xff\xfe")

    with pytest.raises(artifact_manifest.ManifestError, match="cannot read manifest"):
        artifact_manifest.verify_manifest(root, manifest)
    assert artifact_manifest.main(["verify", str(root), str(manifest)]) == 2
    captured = capsys.readouterr()
    assert "cannot read manifest" in captured.err
    assert "Traceback" not in captured.err


@pytest.mark.parametrize("version", [True, 1.0, "1", None])
def test_schema_version_requires_integer(tmp_path: Path, version: object) -> None:
    root = tmp_path / "artifact"
    root.mkdir()
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"schema_version": version, "root": ".", "files": []}), encoding="utf-8")
    with pytest.raises(artifact_manifest.ManifestError, match="unsupported schema_version"):
        artifact_manifest.verify_manifest(root, manifest)
