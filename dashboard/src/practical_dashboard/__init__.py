"""Reusable terminal dashboard for checkpointed experiment pipelines."""

from practical_dashboard.config import DashboardConfig, load_config
from practical_dashboard.progress import DashboardSnapshot, build_snapshot

__all__ = ["DashboardConfig", "DashboardSnapshot", "build_snapshot", "load_config"]
__version__ = "0.1.0"
