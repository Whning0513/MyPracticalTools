# watchdogdownloader

`watchdogdownloader` is a small Bash tool for large downloads that are likely to hit bad long-lived connections. It is the generic version of the Code-Contests-Plus downloader logic.

It is intentionally conservative:

- Downloads are resumable with `curl --continue-at -`.
- A low-speed guard aborts bad "slow drip" connections.
- Retry is handled by the outer script loop, not `curl --retry`.
- The downloader is started with `setsid`, so it is not tied to the launching shell.
- A watchdog can restart the whole downloader process group if aggregate downloaded bytes stop increasing.
- Files are checked against expected byte sizes from a manifest.

## Requirements

`watchdogdownloader` targets Linux and requires Bash, `curl`, `setsid`,
`flock`, and standard GNU utilities such as `readlink`, `stat`, and `sha256sum`.

## Install

Clone the repository and install `wdd` into a directory on `PATH`:

```bash
git clone https://github.com/Whning0513/MyPracticalTools.git
install -Dm755 MyPracticalTools/watchdogDownloader/wdd "$HOME/.local/bin/wdd"
wdd --version
```

Alternatively, run `watchdogDownloader/wdd` directly from the checkout.

## Manifest

Create a tab-separated manifest:

```text
# URL<TAB>relative-output-path<TAB>expected-bytes<TAB>optional-sha256
https://example.com/a.bin	a.bin	123456	
https://example.com/shards/part-00000.parquet	shards/part-00000.parquet	987654321	
```

Rules:

- The second column is relative to the configured output directory.
- `expected-bytes` should be exact when possible.
- Use `0` only when the size is unknown; status can still show growth, but verify cannot prove completeness.
- The fourth column is optional `sha256`.
- Avoid spaces and tabs inside file names.

## Basic Usage

Create a project:

```bash
wdd init \
  /srv/mydownload-state \
  /srv/mydownload-files \
  /srv/mydownload-state/manifest.tsv
```

Start the downloader:

```bash
wdd start /srv/mydownload-state
```

Start the watchdog:

```bash
wdd watchdog-start /srv/mydownload-state
```

Check status:

```bash
wdd status /srv/mydownload-state
```

Verify after completion:

```bash
wdd verify /srv/mydownload-state
```

Stop both watchdog and downloader:

```bash
wdd stop /srv/mydownload-state
```

## Config

`wdd init` writes:

```text
<project-dir>/.wdd/config
```

Useful keys:

```bash
JOBS=1
LOW_SPEED_LIMIT=524288
LOW_SPEED_TIME=60
MAX_DOWNLOAD_TIME=1800
CONNECT_TIMEOUT=30
CHECK_INTERVAL=120
STALL_LIMIT=600
BACKOFF_SECONDS=10
```

Recommended defaults:

- Keep `JOBS=1` for hosts that throttle or rate-limit aggressively.
- Use `JOBS=2` or `JOBS=4` when downloading many independent files from a stable host.
- Keep `LOW_SPEED_LIMIT=524288` and `LOW_SPEED_TIME=60` when you want to reject links below 512 KiB/s for a full minute.
- Increase `MAX_DOWNLOAD_TIME` for very large individual files if the link is stable.

## Why No `curl --retry`

`curl --retry` is useful for many cases, but for large resumed files it makes the control flow less visible. This tool lets one `curl` process either make progress, hit the low-speed guard, fail, or finish. Then the outer loop checks the local file size and starts a fresh resumed request.

That simpler loop is easier to inspect and safer when a process is killed by a watchdog.

## Watchdog Behavior

The watchdog checks aggregate downloaded bytes every `CHECK_INTERVAL` seconds.

It restarts the downloader when:

- the downloader PID is missing;
- aggregate bytes do not increase for `STALL_LIMIT` seconds;
- the file set is not complete.

It kills the downloader process group, not only the direct parent. That prevents old `curl` children from continuing to write while a new downloader starts.

## Parallel Downloads

Set `JOBS` in `.wdd/config`:

```bash
JOBS=4
```

Each worker claims a different manifest entry. Workers do not intentionally write the same file at the same time. If a worker dies, its stale claim is removed when another worker sees that the owner PID is gone.

Use parallelism only for independent files. Do not use it to split a single file.

## Code-Contests-Plus Example

An example manifest is included:

```text
watchdogDownloader/examples/ccplus_1x.manifest.tsv
```

To create a fresh generic project for that dataset:

```bash
wdd init \
  /srv/codecontestplus-state \
  /srv/codecontestplus-files \
  ./watchdogDownloader/examples/ccplus_1x.manifest.tsv
```

## License

watchdogDownloader is licensed under the [MIT License](LICENSE).
