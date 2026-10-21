import math
import re
from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator
from typing import Literal


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Email(Strict):
    email: EmailStr


class NewJob(Strict):
    name: str = Field(min_length=1, max_length=80, pattern=r"^[^\x00-\x1f\x7f]+$")
    task: Literal["Mjlab-Tracking-Flat-Booster-K1"] = "Mjlab-Tracking-Flat-Booster-K1"
    motion_id: str = Field(max_length=100)
    num_envs: int = Field(ge=1, le=16384)
    iterations: int = Field(ge=1, le=100000)
    seed: int = Field(default=42, ge=0, le=2147483647)
    learning_rate: float | None = None
    rewards: dict[str, float] = Field(default_factory=dict, max_length=8)


class UserEdit(Strict):
    approved: bool
    role: Literal["participant", "admin"] = "participant"
    env_limit: int | None = Field(default=None, ge=1, le=16384)


class Motion(Strict):
    id: str = Field(pattern=r"^[\w-]{1,80}$")
    label: str = Field(min_length=1, max_length=120)
    artifact: str = Field(pattern=r"^[\w.\-/]+:v\d+$")
    sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")


class MemoryProfile(Strict):
    base_mb: int = Field(ge=256, le=200000)
    per_env_mb: float = Field(ge=0, le=1000)
    safety_factor: float = Field(ge=1, le=4)


class Settings(Strict):
    paused: bool = False
    default_envs: int = Field(ge=1, le=16384)
    min_envs: int = Field(ge=1, le=16384)
    max_envs: int = Field(ge=1, le=16384)
    presets: list[int] = Field(min_length=1, max_length=16)
    max_iterations: int = Field(ge=1, le=100000)
    motions: list[Motion] = Field(max_length=100)
    tasks: list[Literal["Mjlab-Tracking-Flat-Booster-K1"]]
    memory_profiles: MemoryProfile
    reward_bounds: dict[str, tuple[float, float]]
    learning_rate_bounds: tuple[float, float]

    @model_validator(mode="after")
    def consistent(self):
        if (
            not self.min_envs <= self.default_envs <= self.max_envs
            or self.default_envs not in self.presets
        ):
            raise ValueError("Default must be an allowed preset within limits")
        if any(not self.min_envs <= n <= self.max_envs for n in self.presets):
            raise ValueError("Preset outside limits")
        if len(set(m.id for m in self.motions)) != len(self.motions):
            raise ValueError("Motion IDs must be unique")
        if not set(self.reward_bounds) <= {"motion_foot_pos", "action_rate_l2"}:
            raise ValueError("Reward is not reviewed")
        if any(lo > hi for lo, hi in self.reward_bounds.values()):
            raise ValueError("Invalid reward range")
        lo, hi = self.learning_rate_bounds
        if not 0 < lo <= hi <= 0.01:
            raise ValueError("Invalid learning rate bounds")
        return self


class GPULimits(Strict):
    max_jobs: int = Field(ge=1, le=18)
    reserve_mb: int = Field(ge=0, le=1000000)
    margin_mb: int = Field(ge=256, le=100000)
    max_envs: int = Field(ge=1, le=16384)


class ServerConfig(GPULimits):
    enabled: bool = True
    mode: Literal["direct", "slurm"] = "direct"
    institutional_permission: bool = False
    mps_enabled: bool = False
    mps_required: bool = False
    mps_kind: Literal["legacy", "v3"] = "legacy"
    mps_pipe: str = Field(default="", max_length=300)
    mps_log: str = Field(default="", max_length=300)
    mps_threads: int = Field(default=50, ge=1, le=100)
    mps_memory_mb: int = Field(default=0, ge=0, le=1000000)
    mps_namespace: str = Field(default="", max_length=64, pattern=r"^[a-z0-9_]*$")
    mps_server: str = Field(default="", max_length=64, pattern=r"^[a-z0-9_]*$")
    gpu_limits: dict[str, GPULimits] = Field(default_factory=dict, max_length=32)

    @model_validator(mode="after")
    def paths(self):
        if self.mps_required and not self.mps_enabled:
            raise ValueError("Required MPS must be enabled")
        for p in (self.mps_pipe, self.mps_log):
            if p and (not p.startswith("/") or ".." in p.split("/")):
                raise ValueError("MPS directories must be absolute")
        return self


class NewServer(Strict):
    name: str = Field(pattern=r"^[\w .-]{1,80}$")
    config: ServerConfig


class GPU(Strict):
    uuid: str = Field(pattern=r"^[\w-]{1,100}$")
    name: str = Field(max_length=120)
    total_mb: int = Field(ge=1, le=1000000)
    free_mb: int = Field(ge=0, le=1000000)
    utilization: int = Field(ge=0, le=100)
    driver: str = Field(max_length=80)


class Inventory(Strict):
    gpus: list[GPU] = Field(max_length=32)
    mps: dict = Field(default_factory=dict)
    cuda: str = Field(default="", max_length=1000)
    institutional_scheduler: bool = False
    slurm_job_id: str | None = None
    hostname: str = Field(default="", max_length=120)
    mock: bool = False


class Heartbeat(Strict):
    boot_id: str = Field(max_length=100)
    inventory: Inventory
    active: list[str] = Field(default_factory=list, max_length=40)
    unresolved: list[str] = Field(default_factory=list, max_length=40)


class Report(Strict):
    lease: str = Field(max_length=100)
    iteration: int = Field(default=0, ge=0)
    metrics: dict[str, float] = Field(default_factory=dict, max_length=50)
    logs: str = Field(default="", max_length=131072)
    log_seq: int = Field(default=0, ge=0)
    gpu_mb: int = Field(default=0, ge=0, le=1000000)
    status: Literal["RUNNING", "COMPLETED", "FAILED", "CANCELED"] = "RUNNING"
    error: str | None = Field(default=None, max_length=4000)
    execution: dict | None = None
