# Practical Run Dashboard

[English](README.md) | [简体中文](README.zh-CN.md)

一个可复用的 Rich 终端界面，用于长期运行且带检查点的训练流水线。它将调度器 JSON、Hugging Face `checkpoint-N/trainer_state.json`、tqdm 日志、评测进度和 `nvidia-smi` 汇总到一个实时视图中。

## 功能

- 展示准备、训练、评测和最终报告等流水线阶段；
- 展示各任务的进度条、实时 step、可恢复的检查点 step、速度和 ETA；
- 正确处理暂停状态：显示尚未保存的日志 step，但不把它计入可恢复进度；
- 展示 GPU 白名单、显存、利用率、任务归属和外部进程；
- 对心跳过期、任务暂停、任务失败和审计错误给出警告；
- 从 `progress.json` 恢复评测进度；
- 支持实时 TUI、单次终端输出、JSON 标准输出和原子 JSON 快照。

除非指定 `--json-output`，仪表盘始终是只读的。它不会启动、停止、暂停或迁移训练进程。

## 安装

从本仓库安装：

```bash
python -m pip install -e ./dashboard
```

直接从 GitHub 安装：

```bash
python -m pip install \
  "git+https://github.com/Whning0513/MyPracticalTools.git#subdirectory=dashboard"
```

开发环境：

```bash
python -m pip install -e './dashboard[test]'
python -m pytest dashboard/tests -q
```

## 运行

复制并修改 `examples/aca-rl-matrix.json`，尤其是 `project_root`、`run_dir`、任务名称和总 step 数。

```bash
practical-dashboard --config dashboard/examples/aca-rl-matrix.json
```

其他输出模式：

```bash
practical-dashboard --config dashboard/examples/aca-rl-matrix.json --once --no-color
practical-dashboard --config dashboard/examples/aca-rl-matrix.json --json
practical-dashboard --config dashboard/examples/aca-rl-matrix.json \
  --json-output /tmp/dashboard-snapshot.json
```

使用 tmux 在后台持续运行仪表盘：

```bash
tmux new-session -d -s training-dashboard \
  'practical-dashboard --config /absolute/path/to/dashboard.json'
tmux attach -t training-dashboard
```

## 配置

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

相对的 `run_dir`、准备检查项、日志和输出路径以 `project_root` 为基准解析。相对的 `project_root` 以配置文件所在目录为基准解析。

## 预期状态文件

训练状态默认位于 `<run_dir>/status.json`：

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

支持的任务状态为 `pending`、`running`、`paused`、`failed` 和 `complete`。输出目录可以包含 Hugging Face 风格的 `checkpoint-N/trainer_state.json`，日志可以包含 tqdm 的 `N/TOTAL` 和 `seconds/it` 记录。

可选的评测状态默认位于 `<run_dir>/evaluation_status.json`。每个策略都可以指向一个输出目录，其中的 `progress.json` 包含 `{"total_progress": "37/100"}`。

## 设计说明

- 实时进度来自日志，可恢复进度来自最新检查点。
- 暂停任务只统计到其可恢复检查点。
- ETA 优先使用最近检查点中 `step_time` 的中位数；缺失时回退到近期 tqdm 的 `seconds/it`。
- 当 GPU 显存用量高于 `external_gpu_threshold_mb` 且没有归属任务时，显示为 `external`，不会显示为空闲。

## 许可证

Practical Run Dashboard 使用 [MIT License](LICENSE)。
