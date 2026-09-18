"""Create and verify deterministic manifests for files and research artifacts."""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable, Sequence


SCHEMA_VERSION = 1
TOOL_VERSION = "0.1.0"
CHUNK_SIZE = 1024 * 1024
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

MEDIA_TYPES = {
    ".csv": "text/csv",
    ".json": "application/json",
    ".jsonl": "application/x-ndjson",
    ".md": "text/markdown",
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".py": "text/x-python",
    ".sh": "application/x-sh",
    ".txt": "text/plain",
    ".tsv": "text/tab-separated-values",
    ".yaml": "application/yaml",
    ".yml": "application/yaml",
    ".zip": "application/zip",
    ".zst": "application/zstd",
}


class ManifestError(ValueError):
    """Raised when a root, path, or manifest is not safe to process."""


@dataclass(frozen=True)
class ManifestFile:
    path: str
    bytes: int
    sha256: str
    media_type: str

    def as_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "bytes": self.bytes,
            "sha256": self.sha256,
            "media_type": self.media_type,
        }


def _root_path(root: os.PathLike[str] | str) -> Path:
    path = Path(root).expanduser()
    if path.is_symlink():
        raise ManifestError(f"root must not be a symbolic link: {path}")
    if not path.exists():
        raise ManifestError(f"root does not exist: {path}")
    if not path.is_dir():
        raise ManifestError(f"root is not a directory: {path}")
    return path.resolve()


def _matches_exclude(relative_path: str, patterns: Sequence[str]) -> bool:
    path = PurePosixPath(relative_path)
    return any(
        fnmatch.fnmatchcase(relative_path, pattern)
        or path.match(pattern)
        for pattern in patterns
    )


def _iter_files(
    root: Path,
    *,
    excludes: Sequence[str] = (),
    manifest_path: Path | None = None,
) -> Iterable[tuple[str, Path]]:
    manifest_resolved = (
        manifest_path.resolve(strict=False) if manifest_path is not None else None
    )
    for current, directories, filenames in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        directories.sort()
        filenames.sort()
        for directory in directories:
            candidate = current_path / directory
            if candidate.is_symlink():
                relative = candidate.relative_to(root).as_posix()
                raise ManifestError(f"symbolic links are not supported: {relative}")
        for filename in filenames:
            candidate = current_path / filename
            if candidate.is_symlink():
                relative = candidate.relative_to(root).as_posix()
                raise ManifestError(f"symbolic links are not supported: {relative}")
            relative = candidate.relative_to(root).as_posix()
            if manifest_resolved is not None and candidate.resolve() == manifest_resolved:
                continue
            if _matches_exclude(relative, excludes):
                continue
            yield relative, candidate


def _hash_file(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK_SIZE):
            size += len(chunk)
            digest.update(chunk)
    return size, digest.hexdigest()


def _media_type(path: str) -> str:
    return MEDIA_TYPES.get(Path(path).suffix.lower(), "application/octet-stream")


def collect_files(
    root: os.PathLike[str] | str,
    *,
    excludes: Sequence[str] = (),
    manifest_path: os.PathLike[str] | str | None = None,
) -> list[ManifestFile]:
    """Collect sorted file metadata below *root*.

    Paths in the result always use POSIX separators, regardless of the host OS.
    Symlinks are rejected so a manifest cannot silently include files outside root.
    """

    root_path = _root_path(root)
    output_path = Path(manifest_path).expanduser() if manifest_path is not None else None
    files: list[ManifestFile] = []
    for relative, path in _iter_files(
        root_path, excludes=excludes, manifest_path=output_path
    ):
        size, digest = _hash_file(path)
        files.append(
            ManifestFile(
                path=relative,
                bytes=size,
                sha256=digest,
                media_type=_media_type(relative),
            )
        )
    files.sort(key=lambda item: item.path)
    return files


def create_manifest(
    root: os.PathLike[str] | str,
    output: os.PathLike[str] | str,
    *,
    excludes: Sequence[str] = (),
) -> dict[str, object]:
    """Create a deterministic JSON manifest and return its payload."""

    root_path = _root_path(root)
    output_path = Path(output).expanduser()
    files = collect_files(root_path, excludes=excludes, manifest_path=output_path)
    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "root": ".",
        "files": [item.as_dict() for item in files],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return payload


def _validate_relative_path(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ManifestError("manifest file path must be a non-empty string")
    if "\\" in value:
        raise ManifestError(f"manifest path must use '/' separators: {value!r}")
    pure = PurePosixPath(value)
    if pure.is_absolute() or ".." in pure.parts or pure.as_posix() != value:
        raise ManifestError(f"manifest path escapes root: {value!r}")
    return value


def _load_expected(manifest_path: Path) -> dict[str, ManifestFile]:
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestError(f"cannot read manifest {manifest_path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ManifestError("manifest must contain a JSON object")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ManifestError(
            f"unsupported schema_version: {payload.get('schema_version')!r}"
        )
    if payload.get("root") != ".":
        raise ManifestError("manifest root must be '.'")
    entries = payload.get("files")
    if not isinstance(entries, list):
        raise ManifestError("manifest files must be a JSON array")

    expected: dict[str, ManifestFile] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise ManifestError("each manifest file entry must be an object")
        relative = _validate_relative_path(entry.get("path"))
        if relative in expected:
            raise ManifestError(f"duplicate manifest path: {relative}")
        size = entry.get("bytes")
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise ManifestError(f"invalid byte count for {relative}")
        digest = entry.get("sha256")
        if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
            raise ManifestError(f"invalid sha256 for {relative}")
        media_type = entry.get("media_type")
        if not isinstance(media_type, str) or not media_type:
            raise ManifestError(f"invalid media_type for {relative}")
        expected[relative] = ManifestFile(relative, size, digest, media_type)
    return expected


def verify_manifest(
    root: os.PathLike[str] | str,
    manifest: os.PathLike[str] | str,
    *,
    excludes: Sequence[str] = (),
) -> list[str]:
    """Return human-readable differences between *root* and a manifest."""

    root_path = _root_path(root)
    manifest_path = Path(manifest).expanduser()
    expected = _load_expected(manifest_path)
    actual = {
        item.path: item
        for item in collect_files(
            root_path, excludes=excludes, manifest_path=manifest_path
        )
    }
    differences: list[str] = []
    for relative in sorted(expected.keys() | actual.keys()):
        if relative not in actual:
            differences.append(f"missing: {relative}")
            continue
        if relative not in expected:
            differences.append(f"unexpected: {relative}")
            continue
        want = expected[relative]
        got = actual[relative]
        changes: list[str] = []
        if want.bytes != got.bytes:
            changes.append(f"bytes {want.bytes} -> {got.bytes}")
        if want.sha256 != got.sha256:
            changes.append("sha256 differs")
        if want.media_type != got.media_type:
            changes.append(f"media_type {want.media_type!r} -> {got.media_type!r}")
        if changes:
            differences.append(f"changed: {relative} ({'; '.join(changes)})")
    return differences


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="artifact-manifest",
        description="Create and verify deterministic SHA-256 manifests.",
    )
    parser.add_argument("--version", action="version", version=f"artifact-manifest {TOOL_VERSION}")
    commands = parser.add_subparsers(dest="command", required=True)

    create = commands.add_parser("create", help="write a manifest for a directory")
    create.add_argument("root", type=Path)
    create.add_argument("output", type=Path)
    create.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="PATTERN",
        help="exclude matching relative paths (repeatable)",
    )

    verify = commands.add_parser("verify", help="check a directory against a manifest")
    verify.add_argument("root", type=Path)
    verify.add_argument("manifest", type=Path)
    verify.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="PATTERN",
        help="exclude matching relative paths (repeatable)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "create":
            payload = create_manifest(args.root, args.output, excludes=args.exclude)
            print(f"created {args.output} ({len(payload['files'])} files)")
            return 0
        differences = verify_manifest(args.root, args.manifest, excludes=args.exclude)
        if differences:
            for difference in differences:
                print(f"ERROR {difference}")
            return 1
        print(f"OK {args.manifest}")
        return 0
    except (ManifestError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
