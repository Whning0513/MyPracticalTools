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
