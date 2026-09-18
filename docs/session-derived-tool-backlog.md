# Reusable tool backlog from session archives

[English](session-derived-tool-backlog.md) | [简体中文](session-derived-tool-backlog.zh-CN.md)

This backlog comes from aggregate analysis of four readable Codex archives: a
current workstation archive, a converted historical archive, a portable
backup, and a compute-node archive. Together they contain 6,294 session files
and 464,350 JSONL records dated from June through September 2026.

The analysis retained counts, dates, task categories, and tool names. It did
not retain or publish prompts, responses, command arguments, tool output,
working directories, hostnames, account names, or credentials. The converted
historical archive uses a reduced message schema; the audit handles that schema
without publishing the stored text.

The converted archive is dominated by environment and configuration work,
followed by numerical computing, testing, and contribution maintenance. The
two active archives add a strong cluster around experiment operations, remote
compute, and artifact handling. Those patterns favor small state-capture and
verification tools over project-specific code generators.

## What is already covered

| Repeated need | Existing tool | Why it belongs here |
| --- | --- | --- |
| Monitor long-running experiments and recover from interrupted runs | [Practical Run Dashboard](../dashboard/README.md) | Experiment operations appeared in 124 compute-node sessions and 61 workstation sessions. |
| Resume and verify large downloads | [watchdogDownloader](../watchdogDownloader/README.md) | Transfer work appeared repeatedly on the workstation, while manifests and checksums also support artifact handling. |
| Inventory session archives without leaking their contents | [Codex Session Audit](../codexSessionAudit/README.md) | Session review itself needs a repeatable, privacy-preserving summary. |
| Check a worktree before making it public | [Repository Release Audit](../repoReleaseAudit/README.md) | Release, documentation, environment, and artifact cleanup recur across both active archives. |
| Verify files after moving or publishing an artifact | [artifactManifest](../artifactManifest/README.md) | Data and artifact work needs a small, deterministic inventory that can be checked at the destination. |

## Next candidates

1. **Sanitized Codex configuration backup and diff.** Export allowlisted config,
   skills, and instruction files while rejecting tokens, histories, caches,
   machine paths, and identity files. Environment and configuration work
   appeared in 4,878 converted-archive sessions and 67 current workstation
   sessions.
2. **Remote run handoff snapshot.** Produce one sanitized JSON file describing
   a job's command name, state, checkpoint, logs, GPU allocation, and restart
   instructions. Remote-compute and experiment-operation work dominate the
   compute-node archive.
3. **Read-only contribution queue snapshot.** Summarize review state, CI state,
   maintainer requests, and staleness for an explicit repository allowlist.
   GitHub contribution work appeared in 59 workstation sessions. The tool
   should never post, close, merge, or edit anything.

The first three candidates have value beyond a single project. The
configuration backup needs a deliberately small allowlist. The contribution
snapshot should remain read-only so that triage cannot turn into bulk account
activity.

## Selection rule

A candidate should enter this repository only when it has a concrete input
format, content-safe output, one documented command, tests for failure cases,
and a maintenance use beyond a single archived task.
