#!/usr/bin/env python3
"""Check a Git worktree for common public-release mistakes."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence
from urllib.parse import unquote


TEXT_SUFFIXES = {
    "", ".c", ".cc", ".cfg", ".conf", ".cpp", ".css", ".csv", ".go", ".h", ".hpp",
    ".html", ".ini", ".java", ".js", ".json", ".jsonl", ".jsx", ".md", ".py", ".rb",
    ".rs", ".sh", ".toml", ".ts", ".tsx", ".txt", ".xml", ".yaml", ".yml",
}

SECRET_PATTERNS = {
    "private-key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    "github-token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    "openai-key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "aws-access-key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
}

MACHINE_PATH_PATTERNS = {
    "windows-user-path": re.compile(r"\b[A-Za-z]:\\Users\\[^\\\s]+\\"),
    "mac-user-path": re.compile(r"/Users/[^/\s]+/"),  # release-audit: allow-machine-path
    "linux-user-path": re.compile(r"/home/[^/\s]+/"),  # release-audit: allow-machine-path
    "local-data-path": re.compile(r"/data/(?:whn|hengningwang)/"),
}

MARKDOWN_LINK = re.compile(r"!?(?:\[[^\]]*\])\(([^)\s]+)(?:\s+[^)]*)?\)")


@dataclass(frozen=True)
class Finding:
    level: str
    code: str
    path: str
    line: int | None = None
    detail: str | None = None


def run_git(root: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def tracked_files(root: Path) -> tuple[list[tuple[str, Path]], dict[str, str]]:
    proc = run_git(root, "ls-files", "-z", "--stage")
    if proc.returncode:
        raise ValueError("path is not a readable Git worktree")
    files: list[tuple[str, Path]] = []
    modes: dict[str, str] = {}
    for entry in proc.stdout.split(b"\0"):
        if not entry:
            continue
        metadata, raw_path = entry.split(b"\t", 1)
        mode = metadata.split(b" ", 1)[0].decode("ascii")
        relative = raw_path.decode("utf-8", errors="surrogateescape")
        files.append((relative, root / relative))
        modes[relative] = mode
    return files, modes


def is_text_candidate(path: Path) -> bool:
    return path.suffix.lower() in TEXT_SUFFIXES


def scan_text(path: Path, relative: str, findings: list[Finding]) -> None:
    if not is_text_candidate(path) or path.stat().st_size > 2 * 1024 * 1024:
        return
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return
    for line_number, line in enumerate(text.splitlines(), start=1):
        for name, pattern in SECRET_PATTERNS.items():
            if pattern.search(line) and "release-audit: allow-secret-pattern" not in line:
                findings.append(Finding("error", "secret-pattern", relative, line_number, name))
        for name, pattern in MACHINE_PATH_PATTERNS.items():
            if pattern.search(line) and "release-audit: allow-machine-path" not in line:
                findings.append(Finding("warning", "machine-path", relative, line_number, name))


def scan_markdown_links(root: Path, path: Path, relative: str, findings: list[Finding]) -> None:
    if path.suffix.lower() != ".md" or path.stat().st_size > 2 * 1024 * 1024:
        return
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return
    for line_number, line in enumerate(text.splitlines(), start=1):
        for match in MARKDOWN_LINK.finditer(line):
            target = unquote(match.group(1)).split("#", 1)[0].split("?", 1)[0]
            if not target or re.match(r"^(?:https?:|mailto:|data:)", target, re.IGNORECASE):
                continue
            destination = root / target.lstrip("/") if target.startswith("/") else path.parent / target
            resolved = destination.resolve(strict=False)
            try:
                resolved.relative_to(root)
            except ValueError:
                findings.append(Finding("error", "link-outside-root", relative, line_number, target))
                continue
            if not resolved.exists():
                findings.append(Finding("error", "broken-local-link", relative, line_number, target))


def audit(root: Path, max_file_mb: float = 50.0, strict: bool = False) -> dict[str, object]:
    root = root.resolve()
    files, modes = tracked_files(root)
    findings: list[Finding] = []
    relative_names = {relative for relative, _ in files}

    if not any(name.lower().startswith("readme") for name in relative_names if "/" not in name):
        findings.append(Finding("error", "missing-readme", "."))
    if ".gitignore" not in relative_names:
        findings.append(Finding("warning", "missing-gitignore", "."))
    if not any(name.upper().startswith(("LICENSE", "COPYING")) for name in relative_names if "/" not in name):
        findings.append(Finding("warning", "missing-license", "."))

    warn_bytes = int(max_file_mb * 1024 * 1024)
    github_limit = 100 * 1024 * 1024
    total_bytes = 0
    for relative, path in files:
        try:
            size = path.stat().st_size
        except OSError:
            findings.append(Finding("error", "missing-tracked-file", relative))
            continue
        total_bytes += size
        if size >= github_limit:
            findings.append(Finding("error", "github-file-limit", relative, detail=str(size)))
        elif size >= warn_bytes:
            findings.append(Finding("warning", "large-file", relative, detail=str(size)))
        if modes.get(relative) == "120000":
            findings.append(Finding("warning", "symlink", relative))
        if path.suffix.lower() in {"", ".sh"} and size <= 2 * 1024 * 1024:
            try:
                first_line = path.open("rb").readline(256)
            except OSError:
                first_line = b""
            if first_line.startswith(b"#!") and modes.get(relative) != "100755":
                findings.append(Finding("error", "missing-executable-bit", relative))
        scan_text(path, relative, findings)
        scan_markdown_links(root, path, relative, findings)

    status = run_git(root, "status", "--porcelain")
    dirty = bool(status.stdout.strip())
    if dirty:
        findings.append(Finding("error" if strict else "warning", "dirty-worktree", "."))

    findings.sort(key=lambda item: (item.level != "error", item.code, item.path, item.line or 0))
    errors = sum(item.level == "error" for item in findings)
    warnings = sum(item.level == "warning" for item in findings)
    return {
        "schema_version": 1,
        "summary": {
            "tracked_files": len(files),
            "tracked_bytes": total_bytes,
            "errors": errors,
            "warnings": warnings,
            "dirty": dirty,
        },
        "findings": [asdict(item) for item in findings],
    }


def render_text(data: dict[str, object]) -> str:
    summary = data["summary"]
    assert isinstance(summary, dict)
    lines = [
        f"tracked files: {summary['tracked_files']}",
        f"tracked bytes: {summary['tracked_bytes']}",
        f"errors: {summary['errors']}",
        f"warnings: {summary['warnings']}",
    ]
    for finding in data["findings"]:
        location = finding["path"]
        if finding["line"] is not None:
            location += f":{finding['line']}"
        detail = f" ({finding['detail']})" if finding["detail"] else ""
        lines.append(f"{finding['level'].upper()} {finding['code']} {location}{detail}")
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check a Git worktree before publishing it.")
    parser.add_argument("path", nargs="?", default=Path.cwd(), type=Path)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--max-file-mb", type=float, default=50.0)
    parser.add_argument("--strict", action="store_true", help="treat a dirty worktree as an error")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        data = audit(args.path, args.max_file_mb, args.strict)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 2
    if args.format == "json":
        json.dump(data, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(render_text(data))
    return 1 if data["summary"]["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
