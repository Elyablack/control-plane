from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, List, Optional


@dataclass
class ProcessInfo:
    pid: int
    rss_kb: int
    mem_percent: float
    command: str

    @property
    def rss_mb(self) -> float:
        return self.rss_kb / 1024.0


@dataclass
class Metrics:
    timestamp_utc: str
    timestamp_unix: int
    memory_free_percent: Optional[float]
    swap_used_mb: Optional[float]
    uptime_days: Optional[float]
    disk_used_percent: Optional[int]
    battery_percent: Optional[int]
    power_source: str
    top_processes: List[ProcessInfo]
    brew_outdated_count: Optional[int]
    tm_latest_backup: Optional[str]
    timemachine_age_seconds: Optional[int]


@dataclass
class Evaluation:
    status: str
    reasons: List[str]
    suggested_action: str


@dataclass
class MacAuditSnapshot:
    host: str
    timestamp_utc: str
    timestamp_unix: int
    memory_free_percent: Optional[float]
    swap_used_mb: Optional[float]
    uptime_days: Optional[float]
    disk_used_percent: Optional[int]
    battery_percent: Optional[int]
    power_source: str
    tm_latest_backup: Optional[str]
    timemachine_age_seconds: Optional[int]
    brew_outdated_count: Optional[int]
    agent_launchd_loaded: Optional[bool]
    agent_launchd_running: Optional[bool]
    top_processes: List[ProcessInfo]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
