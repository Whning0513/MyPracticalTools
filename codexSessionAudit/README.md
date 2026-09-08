# Codex Session Audit

`codex-session-audit` reads Codex session JSONL files and reports activity counts, repeated task categories, and tool-call frequency. It never writes conversation text, commands, tool output, working directories, hostnames, account names, or credentials to the report.

Use it to inventory a large `.codex/sessions` directory before deciding what to archive or turn into a script.

## Install and run

```bash
python -m pip install './codexSessionAudit'
codex-session-audit ~/.codex --label workstation
```

JSON output works well for comparing machines:

```bash
codex-session-audit ~/.codex --label gpu-node --format json > session-audit.json
```

The scanner accepts a `.codex` root, a `sessions` directory, a single JSONL file, or several inputs. Source labels appear in the report in place of filesystem paths.

## Privacy boundary

The scanner reads user-message text in memory to match a fixed topic vocabulary. It stores only counters. Reports contain no excerpts or keyword hits tied to a session ID.

The scanner ignores tool arguments and tool output. It counts function names because those names help identify repeated operations without exposing their inputs.

## Development

```bash
python -m pip install -e './codexSessionAudit[test]'
python -m pytest codexSessionAudit/tests -q
```

MIT licensed.
