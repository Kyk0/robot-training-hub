import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Config:
    data: Path = field(
        default_factory=lambda: Path(os.getenv("HUB_DATA", ROOT / "data")).resolve()
    )
    base_repo: Path = field(
        default_factory=lambda: Path(
            os.getenv("HUB_BASE_REPO", ROOT / "vendor/booster_mjlab")
        ).resolve()
    )
    mjlab_repo: Path = field(
        default_factory=lambda: Path(
            os.getenv("HUB_MJLAB_REPO", ROOT / "vendor/mjlab")
        ).resolve()
    )
    public_url: str = field(
        default_factory=lambda: os.getenv("HUB_PUBLIC_URL", "http://127.0.0.1:8000")
    )
    development: bool = field(
        default_factory=lambda: os.getenv("HUB_DEVELOPMENT", "0") == "1"
    )
    heartbeat_timeout: int = 45
    artifact_limit: int = 512 * 1024 * 1024
    session_seconds: int = 43200

    @property
    def db(self):
        return self.data / "hub.sqlite3"


DEFAULT_SETTINGS = {
    "paused": False,
    "default_envs": 2048,
    "min_envs": 1024,
    "max_envs": 4096,
    "presets": [1024, 2048, 4096],
    "max_iterations": 30000,
    "max_running_jobs": 10,
    "gpu_memory_percent": 80,
    "motions": [],
    "tasks": ["Mjlab-Tracking-Flat-Booster-K1"],
    "memory_profiles": {"base_mb": 4096, "per_env_mb": 5.0, "safety_factor": 1.3},
    "reward_bounds": {"motion_foot_pos": [0.0, 5.0], "action_rate_l2": [-1.0, 0.0]},
    "learning_rate_bounds": [0.00001, 0.003],
}
DEFAULT_SERVER = {
    "enabled": True,
    "max_envs": 4096,
    "max_jobs": 10,
    "reserve_mb": 46080,
    "margin_mb": 2048,
    "mode": "direct",
    "institutional_permission": False,
    "mps_enabled": False,
    "mps_required": False,
    "mps_kind": "legacy",
    "mps_pipe": "",
    "mps_log": "",
    "mps_threads": 50,
    "mps_memory_mb": 0,
}
