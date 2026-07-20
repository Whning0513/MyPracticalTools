"""Build stable progress snapshots from scheduler state, checkpoints, and logs."""

from __future__ import annotations

import json
import re
import statistics
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from practical_dashboard.config import DashboardConfig, JobConfig


@dataclass(frozen=True)
class JobProgress:
    name: str
    label: str
    status: str
    current_step: int
    observed_step: int
    saved_step: int
    total_steps: int
    percent: float
    seconds_per_step: float | None
    eta_seconds: float | None
    gpu: int | None
    checkpoint: str | None
    attempts: int
    detail: str


@dataclass(frozen=True)
class StageProgress:
    key: str
    label: str
    status: str
    current: int
    total: int
    percent: float


@dataclass(frozen=True)
class DashboardSnapshot:
    title: str
    generated_at: str
    run_dir: str
    phase: str
    phase_label: str
    current_stage: int
    stage_count: int
    training_current: int
    training_total: int
    evaluation_current: int
    evaluation_total: int
    allowed_gpus: tuple[int, ...]
    gpu_ids: tuple[int, ...]
    external_gpu_threshold_mb: int
    jobs: tuple[JobProgress, ...]
    stages: tuple[StageProgress, ...]
    gpu_memory_used_mb: dict[str, int]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _resolve(value: str | Path | None, root: Path) -> Path | None:
    if not value:
        return None
    path = Path(value)
    return path if path.is_absolute() else root / path


def _tail_text(path: Path | None, limit: int = 4 * 1024 * 1024) -> str:
    if path is None or not path.is_file():
        return ""
    try:
        with path.open("rb") as handle:
            handle.seek(0, 2)
            size = handle.tell()
            handle.seek(max(0, size - limit))
            return handle.read().decode("utf-8", errors="replace")
    except OSError:
        return ""


def _latest_checkpoint(output_dir: Path | None) -> tuple[int, Path | None, dict[str, Any]]:
    if output_dir is None:
        return 0, None, {}
    candidates: list[tuple[int, Path]] = []
    for path in output_dir.glob("checkpoint-*"):
        try:
            candidates.append((int(path.name.rsplit("-", 1)[1]), path))
        except ValueError:
            continue
    if not candidates:
        return 0, None, {}
    step, checkpoint = max(candidates)
    state = _read_json(checkpoint / "trainer_state.json")
    return int(state.get("global_step", step)), checkpoint, state


def _log_progress(text: str, total: int) -> tuple[int, float | None]:
    normalized = text.replace("\r", "\n")
    steps = [int(value) for value in re.findall(rf"(?<!\d)(\d+)\s*/\s*{total}(?!\d)", normalized)]
    rates = [float(value) for value in re.findall(r"([0-9]+(?:\.[0-9]+)?)s/it", normalized)]
    rates = [value for value in rates[-10:] if value > 0]
    return (min(total, max(steps)) if steps else 0, statistics.median(rates) if rates else None)


def _checkpoint_rate(state: dict[str, Any]) -> float | None:
    history = state.get("log_history") or []
    values: list[float] = []
    for row in history[-50:]:
        if not isinstance(row, dict):
            continue
        try:
            value = float(row.get("step_time") or 0)
        except (TypeError, ValueError):
            continue
        if value > 0:
            values.append(value)
    return statistics.median(values[-20:]) if values else None


def _job_progress(config: DashboardConfig, spec: JobConfig, state: dict[str, Any]) -> JobProgress:
    output_dir = _resolve(state.get("output_dir"), config.project_root)
    saved, checkpoint, trainer_state = _latest_checkpoint(output_dir)
    observed, log_rate = _log_progress(_tail_text(_resolve(state.get("log"), config.project_root)),
                                       spec.total_steps)
    status = str(state.get("status") or "pending")
    if status == "complete":
        saved = observed = current = spec.total_steps
    elif status == "paused":
        current = saved
    else:
        current = max(saved, observed)
    rate = _checkpoint_rate(trainer_state) or log_rate
    eta = 0.0 if status == "complete" else None
    if status == "running" and rate is not None:
        eta = max(0.0, (spec.total_steps - current) * rate)
    detail = ""
    if status == "paused":
        detail = str(state.get("pause_reason") or "paused")
        if observed > saved:
            detail += f"; observed {observed}, recoverable {saved}"
    elif status == "failed":
        detail = str(state.get("error") or f"return code {state.get('return_code')}")
    elif status == "pending" and state.get("resume_from_checkpoint"):
        detail = "waiting to resume"
    return JobProgress(
        name=spec.name, label=spec.label, status=status, current_step=current,
        observed_step=max(observed, saved), saved_step=saved, total_steps=spec.total_steps,
        percent=100.0 * current / spec.total_steps, seconds_per_step=rate, eta_seconds=eta,
        gpu=state.get("gpu"), checkpoint=str(checkpoint) if checkpoint else None,
        attempts=int(state.get("attempts") or 0), detail=detail,
    )


def _evaluation_progress(config: DashboardConfig, state: dict[str, Any]) -> tuple[int, int]:
    policies = state.get("policies") or {}
    total = config.evaluation.expected_policies * config.evaluation.tasks_per_policy
    if state.get("phase") == "complete":
        return total, total
    done = 0
    for policy in policies.values():
        if policy.get("status") == "complete":
            done += config.evaluation.tasks_per_policy
            continue
        output_dir = _resolve(policy.get("output_dir"), config.project_root)
        progress = _read_json((output_dir or config.run_dir) / "progress.json")
        match = re.fullmatch(r"(\d+)\s*/\s*(\d+)", str(progress.get("total_progress") or ""))
        if match:
            done += min(config.evaluation.tasks_per_policy, int(match.group(1)))
    return min(total, done), total


def _stage(key: str, label: str, status: str, current: int, total: int) -> StageProgress:
    percent = 100.0 * current / total if total else 100.0
    return StageProgress(key, label, status, current, total, min(100.0, percent))


def _heartbeat_warning(status: dict[str, Any]) -> str | None:
    raw = status.get("last_poll_at")
    if not raw:
        return "Training scheduler has no heartbeat"
    try:
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(str(raw))).total_seconds()
    except (TypeError, ValueError):
        return "Training scheduler heartbeat is invalid"
    return f"Training scheduler heartbeat is stale ({int(age)}s)" if age > 180 else None


def build_snapshot(config: DashboardConfig) -> DashboardSnapshot:
    training = _read_json(config.run_dir / config.training_status_file)
    evaluation = _read_json(config.run_dir / config.evaluation_status_file)
    job_states = training.get("jobs") or {}
    jobs = tuple(_job_progress(config, spec, job_states.get(spec.name) or {}) for spec in config.jobs)
    training_current = sum(job.current_step for job in jobs)
    training_total = sum(job.total_steps for job in jobs)
    evaluation_current, evaluation_total = _evaluation_progress(config, evaluation)
    setup_total = len(config.setup_checks)
    setup_current = sum(path.is_file() for path in config.setup_checks)
    setup_ready = setup_current == setup_total
    training_complete = all(job.status == "complete" for job in jobs)
    training_failed = any(job.status == "failed" for job in jobs)
    evaluation_phase = str(evaluation.get("phase") or "waiting")
    evaluation_complete = evaluation_phase == "complete"
    report_ready = all((config.run_dir / path).is_file() for path in config.final_report_files)

    if not setup_ready:
        phase, phase_label, current_stage = "setup", "Data and calibration", 1
    elif not training_complete:
        phase, phase_label, current_stage = "training", "Adapter training", 2
    elif not evaluation_complete:
        phase, phase_label, current_stage = "evaluation", config.evaluation.label, 3
    else:
        phase, phase_label, current_stage = "complete", "Final report", 4
    if training_failed:
        training_status = "failed"
    elif training_complete:
        training_status = "complete"
    elif any(job.status == "running" for job in jobs):
        training_status = "running"
    elif any(job.status == "paused" for job in jobs):
        training_status = "paused"
    else:
        training_status = "pending"
    stages = (
        _stage("setup", "Data and calibration", "complete" if setup_ready else "running",
               setup_current, setup_total),
        _stage("training", "Adapter training", training_status, training_current, training_total),
        _stage("evaluation", config.evaluation.label,
               "complete" if evaluation_complete else ("running" if evaluation_phase == "evaluating" else "waiting"),
               evaluation_current, evaluation_total),
        _stage("report", "Final report", "complete" if report_ready else "waiting", int(report_ready), 1),
    )
    warnings: list[str] = []
    heartbeat = _heartbeat_warning(training)
    if heartbeat:
        warnings.append(heartbeat)
    for job in jobs:
        if job.status == "paused":
            warnings.append(f"{job.label} is paused at recoverable step {job.saved_step}")
        elif job.status == "failed":
            warnings.append(f"{job.label} failed: {job.detail}")
    if evaluation.get("previous_errors"):
        warnings.append("Evaluation state contains audited previous errors")
    allowed = tuple(int(gpu) for gpu in (training.get("allowed_gpus") or config.allowed_gpus))
    return DashboardSnapshot(
        title=config.title, generated_at=datetime.now(timezone.utc).isoformat(),
        run_dir=str(config.run_dir), phase=phase, phase_label=phase_label,
        current_stage=current_stage, stage_count=len(stages), training_current=training_current,
        training_total=training_total, evaluation_current=evaluation_current,
        evaluation_total=evaluation_total, allowed_gpus=allowed, gpu_ids=config.gpu_ids,
        external_gpu_threshold_mb=config.external_gpu_threshold_mb, jobs=jobs, stages=stages,
        gpu_memory_used_mb={str(key): int(value) for key, value in
                            (training.get("gpu_memory_used_mb") or {}).items()},
        warnings=tuple(warnings),
    )
