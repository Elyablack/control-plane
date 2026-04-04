from dataclasses import dataclass
from typing import List, Optional


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
    top_processes: List[ProcessInfo]


@dataclass
class Evaluation:
    status: str
    reasons: List[str]
