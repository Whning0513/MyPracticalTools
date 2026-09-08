# Repository Release Audit

`repo-release-audit` checks a Git worktree before you publish or archive it. It catches missing repository metadata, strong credential patterns, machine-specific paths, broken local Markdown links, oversized files, symlinks, and scripts that lost their executable bit.

The command scans tracked files only. It reports file names and line numbers without printing matched secrets or source text.

## Install and run

```bash
python -m pip install './repoReleaseAudit'
repo-release-audit /path/to/repository
```

Use JSON in automation:

```bash
repo-release-audit . --format json
```

The default size warning starts at 50 MiB. GitHub's 100 MiB per-file limit is an error. `--strict` also treats a dirty worktree as an error.

## Checks

- Root README, `.gitignore`, and license presence.
- GitHub, OpenAI, AWS, and private-key signatures in tracked text files.
- Absolute user or machine-data paths in tracked text files.
- Local Markdown links, tracked symlinks, file sizes, and executable shebang scripts.

The credential scan uses narrow signatures to limit false positives. Run a dedicated secret scanner before publishing security-sensitive code.

Known examples can carry an inline `release-audit: allow-secret-pattern` or `release-audit: allow-machine-path` marker. Review the line before adding a marker.

## Development

```bash
python -m pip install -e './repoReleaseAudit[test]'
python -m pytest repoReleaseAudit/tests -q
```

MIT licensed.
