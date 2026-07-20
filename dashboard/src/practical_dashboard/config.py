"""Configuration schema for the practical training dashboard."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class JobConfig:
    name: str
    total_steps: int
    label: str


@dataclass(frozen=True)
class EvaluationConfig:
    expected_policies: int = 5
    tasks_per_policy: int = 100
    label: str = "Frozen evaluation"


@dataclass(frozen=True)
class DashboardConfig:
    title: str
    project_root: Path
    run_dir: Path
    jobs: tuple[JobConfig, ...]
    setup_checks: tuple[Path, ...]
    evaluation: EvaluationConfig
    gpu_ids: tuple[int, ...]
    allowed_gpus: tuple[int, ...]
    external_gpu_threshold_mb: int
    training_status_file: str = "status.json"
    evaluation_status_file: str = "evaluation_status.json"
    final_report_files: tuple[str, ...] = ("final_report.json", "final_report.md")


def _positive_integer(value: Any, field: str) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field} must be an integer") from error
    if result < 1:
        raise ValueError(f"{field} must be positive")
    return result


def _gpu_list(value: Any, field: str) -> tuple[int, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{field} must be a non-empty list")
    try:
        result = tuple(dict.fromkeys(int(item) for item in value))
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field} must contain integer GPU IDs") from error
    return result


def load_config(path: str | Path) -> DashboardConfig:
    source = Path(path).resolve()
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read dashboard config {source}: {error}") from error
    if not isinstance(payload, dict):
        raise ValueError("dashboard config must be a JSON object")

    root_value = Path(str(payload.get("project_root") or ".")).expanduser()
    project_root = root_value.resolve() if root_value.is_absolute() else (source.parent / root_value).resolve()
    raw_run_dir = payload.get("run_dir")
    if not isinstance(raw_run_dir, str) or not raw_run_dir.strip():
        raise ValueError("run_dir is required")
    run_value = Path(raw_run_dir).expanduser()
    run_dir = run_value if run_value.is_absolute() else project_root / run_value

    raw_jobs = payload.get("jobs")
    if not isinstance(raw_jobs, list) or not raw_jobs:
        raise ValueError("jobs must be a non-empty list")
    jobs: list[JobConfig] = []
    seen: set[str] = set()
    for index, row in enumerate(raw_jobs):
        if not isinstance(row, dict) or not str(row.get("name") or "").strip():
            raise ValueError(f"jobs[{index}].name is required")
        name = str(row["name"]).strip()
        if name in seen:
            raise ValueError(f"duplicate job name: {name}")
        seen.add(name)
        jobs.append(JobConfig(name, _positive_integer(row.get("total_steps"), f"jobs[{index}].total_steps"),
                              str(row.get("label") or name)))

    gpu_ids = _gpu_list(payload.get("gpu_ids") or [0], "gpu_ids")
    allowed_gpus = _gpu_list(payload.get("allowed_gpus") or list(gpu_ids), "allowed_gpus")
    if any(gpu not in gpu_ids for gpu in allowed_gpus):
        raise ValueError("allowed_gpus must be a subset of gpu_ids")
    evaluation_row = payload.get("evaluation") or {}
    evaluation = EvaluationConfig(
        expected_policies=_positive_integer(evaluation_row.get("expected_policies", 5),
                                            "evaluation.expected_policies"),
        tasks_per_policy=_positive_integer(evaluation_row.get("tasks_per_policy", 100),
                                           "evaluation.tasks_per_policy"),
        label=str(evaluation_row.get("label") or "Frozen evaluation"),
    )
    setup_checks = tuple(
        item if item.is_absolute() else project_root / item
        for item in (Path(str(value)) for value in payload.get("setup_checks") or [])
    )
    report_files = tuple(str(value) for value in payload.get("final_report_files") or
                         ("final_report.json", "final_report.md"))
    return DashboardConfig(
        title=str(payload.get("title") or "Experiment dashboard"), project_root=project_root,
        run_dir=run_dir.resolve(), jobs=tuple(jobs), setup_checks=setup_checks,
        evaluation=evaluation, gpu_ids=gpu_ids, allowed_gpus=allowed_gpus,
        external_gpu_threshold_mb=_positive_integer(payload.get("external_gpu_threshold_mb", 2048),
                                                    "external_gpu_threshold_mb"),
        training_status_file=str(payload.get("training_status_file") or "status.json"),
        evaluation_status_file=str(payload.get("evaluation_status_file") or "evaluation_status.json"),
        final_report_files=report_files,
    )
