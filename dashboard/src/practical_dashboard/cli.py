"""Rich terminal interface for practical_dashboard."""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from practical_dashboard.config import load_config
from practical_dashboard.progress import DashboardSnapshot, build_snapshot


STATUS_STYLE = {
    "complete": "bold green", "running": "bold cyan", "paused": "bold yellow",
    "failed": "bold red", "pending": "dim", "waiting": "dim",
}


def format_duration(seconds: float | None) -> str:
    if seconds is None:
        return "--"
    value = max(0, int(seconds))
    days, value = divmod(value, 86400)
    hours, value = divmod(value, 3600)
    minutes, secs = divmod(value, 60)
    if days:
        return f"{days}d {hours:02d}h"
    if hours:
        return f"{hours}h {minutes:02d}m"
    if minutes:
        return f"{minutes}m {secs:02d}s"
    return f"{secs}s"


def _bar(percent: float, width: int = 24) -> Text:
    filled = min(width, max(0, round(width * percent / 100)))
    result = Text("█" * filled, style="green" if percent >= 100 else "cyan")
    result.append("░" * (width - filled), style="grey35")
    return result


def gpu_stats() -> dict[int, dict[str, int]]:
    command = ["nvidia-smi", "--query-gpu=index,memory.used,memory.total,utilization.gpu",
               "--format=csv,noheader,nounits"]
    try:
        completed = subprocess.run(command, text=True, capture_output=True, check=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return {}
    result: dict[int, dict[str, int]] = {}
    for line in completed.stdout.splitlines():
        try:
            index, used, total, utilization = [int(value.strip()) for value in line.split(",")]
        except ValueError:
            continue
        result[index] = {"used": used, "total": total, "utilization": utilization}
    return result


def render(snapshot: DashboardSnapshot) -> Group:
    headline = Text(snapshot.title, style="bold")
    headline.append(f"   Stage {snapshot.current_stage}/{snapshot.stage_count}: ", style="dim")
    headline.append(snapshot.phase_label, style="bold cyan")
    headline.append(f"   GPUs {','.join(map(str, snapshot.allowed_gpus))}", style="dim")
    headline.append(f"   {snapshot.generated_at[11:19]} UTC", style="dim")
    stages = Table(box=None, expand=True, padding=(0, 1))
    stages.add_column("Stage", ratio=2)
    stages.add_column("State", width=10)
    stages.add_column("Progress", width=18, justify="right", no_wrap=True)
    stages.add_column("", ratio=3)
    for stage in snapshot.stages:
        stages.add_row(stage.label, Text(stage.status, style=STATUS_STYLE.get(stage.status, "white")),
                       f"{stage.current}/{stage.total}  {stage.percent:5.1f}%", _bar(stage.percent))
    jobs = Table(expand=True, header_style="bold", padding=(0, 1))
    jobs.add_column("Method", width=12)
    jobs.add_column("State", width=9)
    jobs.add_column("Step", width=14, justify="right")
    jobs.add_column("Progress", ratio=3)
    jobs.add_column("GPU", width=5, justify="center")
    jobs.add_column("Speed", width=10, justify="right")
    jobs.add_column("ETA", width=10, justify="right")
    jobs.add_column("Saved", width=9, justify="right")
    for job in snapshot.jobs:
        eta = "paused" if job.status == "paused" else format_duration(job.eta_seconds)
        speed = f"{job.seconds_per_step:.1f}s/it" if job.seconds_per_step else "--"
        jobs.add_row(job.label, Text(job.status, style=STATUS_STYLE.get(job.status, "white")),
                     f"{job.current_step}/{job.total_steps}", _bar(job.percent),
                     str(job.gpu) if job.gpu is not None else "--", speed, eta, str(job.saved_step))
    stats = gpu_stats()
    gpus = Table(box=None, expand=True, padding=(0, 1))
    gpus.add_column("GPU", width=5)
    gpus.add_column("Role", width=12)
    gpus.add_column("Memory", ratio=2)
    gpus.add_column("Util", width=8, justify="right")
    roles = {job.gpu: job.label for job in snapshot.jobs if job.gpu is not None}
    for index in snapshot.gpu_ids:
        row = stats.get(index)
        if row:
            memory, utilization = f"{row['used'] / 1024:.1f} / {row['total'] / 1024:.0f} GiB", f"{row['utilization']}%"
        else:
            memory, utilization = f"{snapshot.gpu_memory_used_mb.get(str(index), 0) / 1024:.1f} GiB", "--"
        if index in roles:
            role = Text(roles[index], style="bold cyan")
        elif row and row["used"] > snapshot.external_gpu_threshold_mb:
            role = Text("external", style="bold yellow")
        elif index not in snapshot.allowed_gpus:
            role = Text("reserved", style="dim")
        else:
            role = Text("free", style="green")
        gpus.add_row(str(index), role, memory, utilization)
    warnings = "\n".join(f"• {item}" for item in snapshot.warnings) or "No active warnings"
    return Group(
        Panel(headline, border_style="cyan"),
        Panel(stages, title="Pipeline stages", border_style="blue"),
        Panel(jobs, title="Training jobs", border_style="blue"),
        Panel(gpus, title="GPUs", border_style="blue"),
        Panel(warnings, title="Attention", border_style="yellow" if snapshot.warnings else "green"),
    )


def _write_json(path: Path, snapshot: DashboardSnapshot) -> None:
    payload = snapshot.to_dict()
    payload["gpu_stats"] = {str(key): value for key, value in gpu_stats().items()}
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, help="dashboard JSON configuration")
    parser.add_argument("--refresh", type=float, default=2.0,
                        help="live refresh interval in seconds (default: 2)")
    parser.add_argument("--once", action="store_true", help="render once and exit")
    parser.add_argument("--json", action="store_true", help="print one JSON snapshot and exit")
    parser.add_argument("--json-output", help="atomically update a JSON snapshot file")
    parser.add_argument("--no-color", action="store_true", help="disable terminal colors")
    args = parser.parse_args()
    if args.refresh < 0.5:
        raise SystemExit("--refresh must be at least 0.5 seconds")
    try:
        config = load_config(args.config)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    console = Console(no_color=args.no_color)

    def snapshot() -> DashboardSnapshot:
        result = build_snapshot(config)
        if args.json_output:
            _write_json(Path(args.json_output), result)
        return result

    first = snapshot()
    if args.json:
        print(json.dumps(first.to_dict(), ensure_ascii=False, indent=2))
        return
    if args.once:
        console.print(render(first))
        return
    try:
        with Live(render(first), console=console, refresh_per_second=4, screen=True) as live:
            while True:
                time.sleep(args.refresh)
                live.update(render(snapshot()))
    except KeyboardInterrupt:
        return


if __name__ == "__main__":
    main()
