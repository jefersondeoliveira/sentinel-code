"""
Modelos de dados do Benchmark Agent.
"""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class BenchmarkReport:
    """
    Resultado de uma execução de benchmark com Locust.
    """
    phase:            str    # "before" | "after"
    total_requests:   int
    failed_requests:  int
    rps:              float
    p50_ms:           float
    p95_ms:           float
    p99_ms:           float
    min_ms:           float
    max_ms:           float
    error_rate_pct:   float
    duration_seconds: int
    timestamp:        str = field(default_factory=lambda: datetime.now().strftime("%Y%m%d_%H%M%S"))

    def __str__(self) -> str:
        return (
            f"BenchmarkReport [{self.phase}] "
            f"RPS={self.rps:.1f} P99={self.p99_ms:.0f}ms "
            f"Errors={self.error_rate_pct:.1f}%"
        )