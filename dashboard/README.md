# Practical Run Dashboard

A reusable Rich terminal UI for long-running, checkpointed training pipelines.
It combines scheduler JSON, Hugging Face `checkpoint-N/trainer_state.json`,
tqdm logs, evaluation progress, and `nvidia-smi` into one live view.

## Features

- pipeline stages: setup, training, evaluation, final report;
- per-job progress bars, live step, recoverable checkpoint step, speed, and ETA;
- correct paused-job semantics: unsaved log steps are shown but not counted as recoverable;
- GPU allowlist, memory, utilization, task ownership, and external-process detection;
- stale heartbeat, paused job, failed job, and audited-error warnings;
- resumable evaluation progress from `progress.json`;
- live TUI, one-shot terminal output, JSON stdout, and atomic JSON snapshots.

The dashboard is read-only unless `--json-output` is supplied. It never starts,
stops, pauses, or moves a training process.

## Install

From this repository:

```bash
python -m pip install -e ./dashboard
```

Directly from GitHub:

```bash
python -m pip install \
  "git+https://github.com/Whning0513/MyPracticalTools.git#subdirectory=dashboard"
```

For development:

```bash
python -m pip install -e './dashboard[test]'
python -m pytest dashboard/tests -q
```

## Run

Copy and edit `examples/aca-rl-matrix.json`, especially `project_root`,
`run_dir`, job names, and total steps.

```bash
practical-dashboard --config dashboard/examples/aca-rl-matrix.json
```

Other output modes:

```bash
practical-dashboard --config dashboard/examples/aca-rl-matrix.json --once --no-color
practical-dashboard --config dashboard/examples/aca-rl-matrix.json --json
practical-dashboard --config dashboard/examples/aca-rl-matrix.json \
  --json-output /tmp/dashboard-snapshot.json
```

Detach a persistent dashboard with tmux:

```bash
tmux new-session -d -s training-dashboard \
  'practical-dashboard --config /absolute/path/to/dashboard.json'
tmux attach -t training-dashboard
```

## Configuration

```json
{
  "title": "My training matrix",
  "project_root": "/absolute/path/to/project",
  "run_dir": "artifacts/runs/experiment-001",
  "jobs": [
    {"name": "sft", "label": "SFT", "total_steps": 500},
    {"name": "dpo", "label": "DPO", "total_steps": 1000}
  ],
  "setup_checks": ["artifacts/data/manifest.json"],
  "evaluation": {
    "label": "Frozen evaluation",
    "expected_policies": 2,
    "tasks_per_policy": 100
  },
  "final_report_files": ["final_report.json", "final_report.md"],
  "gpu_ids": [0, 1, 2, 3],
  "allowed_gpus": [0, 2],
  "external_gpu_threshold_mb": 2048
}
```

Relative `run_dir`, setup-check, log, and output paths resolve from
`project_root`. Relative `project_root` resolves from the config file location.

## Expected state files

The training status defaults to `<run_dir>/status.json`:

```json
{
  "last_poll_at": "2026-07-20T03:00:00+00:00",
  "allowed_gpus": [0, 2],
  "gpu_memory_used_mb": {"0": 32000, "1": 20, "2": 45000, "3": 20},
  "jobs": {
    "sft": {
      "status": "running",
      "gpu": 0,
      "attempts": 1,
      "output_dir": "artifacts/runs/experiment-001/adapters/sft",
      "log": "artifacts/runs/experiment-001/logs/sft.log"
    }
  }
}
```

Supported job states are `pending`, `running`, `paused`, `failed`, and
`complete`. Output directories may contain Hugging Face-style
`checkpoint-N/trainer_state.json`. Logs may contain tqdm `N/TOTAL` and
`seconds/it` records.

The optional evaluation status defaults to
`<run_dir>/evaluation_status.json`. Each policy may point to an output directory
whose `progress.json` contains `{"total_progress": "37/100"}`.

## Design notes

- Live progress comes from logs, while recoverable progress comes from the
  newest checkpoint.
- A paused job is counted only through its recoverable checkpoint.
- ETA uses the median of the latest checkpoint `step_time` values, falling back
  to recent tqdm `seconds/it` values.
- GPUs above `external_gpu_threshold_mb` without an owned job are displayed as
  `external`, never as free.

## License

Practical Run Dashboard is licensed under the [MIT License](LICENSE).
