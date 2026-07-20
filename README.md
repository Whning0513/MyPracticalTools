# MyPracticalTools

[![CI](https://github.com/Whning0513/MyPracticalTools/actions/workflows/ci.yml/badge.svg)](https://github.com/Whning0513/MyPracticalTools/actions/workflows/ci.yml)

Small, reusable tools and reference assets for long-running ML, data, and
automation workflows.

这是一个个人实用工具集合。每个工具都有独立文档和明确的使用边界，可以单独安装或复制，
不需要采用整个仓库的其他部分。

## Included projects

| Project | Runtime | Purpose |
| --- | --- | --- |
| [Practical Run Dashboard](dashboard/README.md) | Python 3.10+ | Read-only terminal dashboard for checkpointed training and evaluation jobs, including progress, ETA, GPU use, and recoverable state. |
| [watchdogDownloader](watchdogDownloader/README.md) | Bash on Linux | Resumable manifest-based downloads with low-speed detection, process supervision, and size or SHA-256 verification. |
| [ACA small v0.2](datasets/ACA_small_v0.2/) | Zstandard JSONL | Versioned train/test dataset package with a manifest, blind-gate metadata, and audit reports. |
| [Dataset design notes](docs/dataset-and-datapackage-design.md) | Markdown | Reproducibility, split isolation, replay, validator, reference, and release requirements for the ACA data package. |
| [User workstyle skill](whn_skill/whn_skill.md) | Markdown | A Codex skill for evidence-driven coding, research, and technical communication. |

## Quick start

### Practical Run Dashboard

Install directly from this repository:

```bash
python -m pip install \
  "git+https://github.com/Whning0513/MyPracticalTools.git#subdirectory=dashboard"
```

Copy and edit the example configuration, then start the live terminal view:

```bash
practical-dashboard --config dashboard/examples/aca-rl-matrix.json
```

See the [dashboard documentation](dashboard/README.md) for JSON output,
checkpoint semantics, GPU ownership, and expected status files.

### watchdogDownloader

Install the script into a directory on `PATH`:

```bash
git clone https://github.com/Whning0513/MyPracticalTools.git
install -Dm755 MyPracticalTools/watchdogDownloader/wdd "$HOME/.local/bin/wdd"
wdd --help
```

Create a tab-separated manifest, initialize a download project, and start it:

```bash
wdd init /srv/download-state /srv/files ./manifest.tsv
wdd start /srv/download-state
wdd watchdog-start /srv/download-state
wdd status /srv/download-state
```

See the [watchdogDownloader documentation](watchdogDownloader/README.md) for
the manifest format, retry behavior, verification, and tuning controls.

## Dataset package

`datasets/ACA_small_v0.2/` contains compressed train/test problems and
submissions. Use `manifest.json` as the versioned source of truth and inspect
`audit/report.json` before consuming the package. The accompanying
[design document](docs/dataset-and-datapackage-design.md) distinguishes frozen
benchmark evidence from replay output, constructed references, validators, and
blind probes.

## Development

Run the Python tests:

```bash
python -m pip install -e './dashboard[test]'
python -m pytest dashboard/tests -q
```

Check the Bash script syntax:

```bash
bash -n watchdogDownloader/wdd
watchdogDownloader/wdd --version
```

CI runs both checks for pull requests and changes to `main`.

## License

The original software components, including Practical Run Dashboard,
watchdogDownloader, and the user-workstyle skill, are licensed under the
[MIT License](LICENSE). The dataset package, data-design materials, and any
third-party content are excluded unless a separate license is identified. See
[`LICENSE_SCOPE.md`](LICENSE_SCOPE.md) for the exact path-level scope.

## Contributing

Focused bug reports and pull requests are welcome. Include a minimal
reproduction, explain the behavioral change, and state the validation command.
Do not include credentials, private datasets, generated caches, or machine-
specific absolute paths.
