from __future__ import annotations

import json
from pathlib import Path

import pytest

from practical_dashboard.cli import format_duration
from practical_dashboard.config import load_config
from practical_dashboard.progress import build_snapshot


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def config_file(tmp_path: Path) -> Path:
    path = tmp_path / "dashboard.json"
    write_json(path, {
        "title": "Test matrix", "project_root": ".", "run_dir": "run",
        "jobs": [
            {"name": "done", "total_steps": 10},
            {"name": "live", "total_steps": 100},
            {"name": "held", "total_steps": 100}
        ],
        "setup_checks": ["manifest.json"],
        "evaluation": {"expected_policies": 3, "tasks_per_policy": 20},
        "gpu_ids": [4, 5, 6, 7], "allowed_gpus": [4, 7]
    })
    return path


def test_config_rejects_allowed_gpu_outside_display_set(tmp_path: Path):
    path = config_file(tmp_path)
    payload = json.loads(path.read_text())
    payload["allowed_gpus"] = [3]
    write_json(path, payload)
    with pytest.raises(ValueError, match="subset"):
        load_config(path)


def test_config_requires_run_dir(tmp_path: Path):
    path = config_file(tmp_path)
    payload = json.loads(path.read_text())
    del payload["run_dir"]
    write_json(path, payload)
    with pytest.raises(ValueError, match="run_dir is required"):
        load_config(path)


def test_snapshot_combines_live_and_recoverable_progress(tmp_path: Path):
    config = load_config(config_file(tmp_path))
    (tmp_path / "manifest.json").write_text("{}", encoding="utf-8")
    jobs = {}
    for name, status, gpu in (("done", "complete", None), ("live", "running", 4),
                              ("held", "paused", None)):
        jobs[name] = {
            "status": status, "gpu": gpu, "attempts": 1,
            "output_dir": str(tmp_path / "outputs" / name),
            "log": str(tmp_path / "logs" / f"{name}.log")
        }
    jobs["held"]["pause_reason"] = "reserved GPU"
    write_json(config.run_dir / "status.json", {
        "last_poll_at": "2999-01-01T00:00:00+00:00", "allowed_gpus": [4, 7], "jobs": jobs
    })
    write_json(tmp_path / "outputs/live/checkpoint-40/trainer_state.json", {
        "global_step": 40,
        "log_history": [{"step_time": "invalid"}, {"step_time": 12.0}, {"step_time": 10.0}]
    })
    write_json(tmp_path / "outputs/held/checkpoint-20/trainer_state.json", {"global_step": 20})
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs/live.log").write_text("45/100 [1:00<2:00, 9.0s/it]", encoding="utf-8")
    (tmp_path / "logs/held.log").write_text("24/100 [1:00<2:00, 20.0s/it]", encoding="utf-8")
    snapshot = build_snapshot(config)
    jobs_by_name = {job.name: job for job in snapshot.jobs}
    assert jobs_by_name["done"].current_step == 10
    assert jobs_by_name["live"].current_step == 45
    assert jobs_by_name["live"].eta_seconds == 55 * 11.0
    assert jobs_by_name["held"].current_step == 20
    assert jobs_by_name["held"].observed_step == 24
    assert snapshot.training_current == 75
    assert snapshot.phase == "training"
    assert snapshot.allowed_gpus == (4, 7)


def test_evaluation_progress_and_duration_formatting(tmp_path: Path):
    config = load_config(config_file(tmp_path))
    (tmp_path / "manifest.json").write_text("{}", encoding="utf-8")
    jobs = {
        name: {"status": "complete", "output_dir": str(tmp_path / "outputs" / name)}
        for name in ("done", "live", "held")
    }
    write_json(config.run_dir / "status.json", {
        "last_poll_at": "2999-01-01T00:00:00+00:00", "jobs": jobs
    })
    policies = {
        "a": {"status": "complete", "output_dir": str(config.run_dir / "eval/a")},
        "b": {"status": "running", "output_dir": str(config.run_dir / "eval/b")},
        "c": {"status": "pending", "output_dir": str(config.run_dir / "eval/c")},
    }
    write_json(config.run_dir / "eval/b/progress.json", {"total_progress": "7/20"})
    write_json(config.run_dir / "evaluation_status.json", {"phase": "evaluating", "policies": policies})
    snapshot = build_snapshot(config)
    assert snapshot.phase == "evaluation"
    assert snapshot.evaluation_current == 27
    assert snapshot.evaluation_total == 60
    assert format_duration(3661) == "1h 01m"
