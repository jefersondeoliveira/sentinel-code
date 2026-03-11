"""
Comparador de benchmarks.
Calcula deltas, tendências e valida SLAs.
"""

from typing import Optional
from tools.benchmark.models import BenchmarkReport


def calculate_delta(before: float, after: float) -> float:
    """
    Calcula variação percentual entre before e after.
    Negativo = melhoria (ex: latência caiu).
    Positivo = aumento (ex: RPS subiu).
    """
    if before == 0:
        return 0.0
    return round(((after - before) / before) * 100, 1)


def _trend(before: float, after: float, higher_is_better: bool) -> str:
    """Retorna IMPROVING, DEGRADING ou STABLE."""
    if before == after:
        return "STABLE"
    improved = after > before if higher_is_better else after < before
    return "IMPROVING" if improved else "DEGRADING"


def validate_slas(
    after: BenchmarkReport,
    nfr: dict,
    before: Optional[BenchmarkReport] = None,
) -> dict:
    """
    Valida o relatório after contra os SLAs definidos nos NFRs.
    Se before for fornecido, calcula trend e delta.
    """
    result = {}

    # RPS — maior é melhor
    if "max_rps" in nfr:
        sla = nfr["max_rps"]
        delta = calculate_delta(before.rps, after.rps) if before else 0.0
        trend = _trend(before.rps, after.rps, higher_is_better=True) if before else (
            "IMPROVING" if after.rps >= sla else "DEGRADING"
        )
        result["rps"] = {
            "sla":       sla,
            "after":     after.rps,
            "delta_pct": delta,
            "status":    "PASS" if after.rps >= sla else "FAIL",
            "trend":     trend,
        }

    # P99 latência — menor é melhor
    if "p99_latency_ms" in nfr:
        sla = nfr["p99_latency_ms"]
        delta = calculate_delta(before.p99_ms, after.p99_ms) if before else 0.0
        if before:
            trend = _trend(before.p99_ms, after.p99_ms, higher_is_better=False)
        else:
            # Sem before: IMPROVING se está próximo do SLA, DEGRADING se muito acima
            trend = "IMPROVING" if after.p99_ms <= sla * 1.2 else "DEGRADING"
        result["p99_latency_ms"] = {
            "sla":       sla,
            "after":     after.p99_ms,
            "delta_pct": delta,
            "status":    "PASS" if after.p99_ms <= sla else "FAIL",
            "trend":     trend,
        }

    # Error rate — menor é melhor (SLA implícito: < 1%)
    error_sla = nfr.get("max_error_rate_pct", 1.0)
    delta = calculate_delta(before.error_rate_pct, after.error_rate_pct) if before else 0.0
    trend = _trend(before.error_rate_pct, after.error_rate_pct, higher_is_better=False) if before else (
        "IMPROVING" if after.error_rate_pct <= error_sla else "DEGRADING"
    )
    result["error_rate_pct"] = {
        "sla":       error_sla,
        "after":     after.error_rate_pct,
        "delta_pct": delta,
        "status":    "PASS" if after.error_rate_pct <= error_sla else "FAIL",
        "trend":     trend,
    }

    return result


def compare_benchmarks(
    before: BenchmarkReport,
    after: BenchmarkReport,
    nfr: dict,
) -> dict:
    """
    Compara dois relatórios e valida SLAs com contexto de antes/depois.
    """
    result = {}

    # RPS
    if "max_rps" in nfr:
        sla = nfr["max_rps"]
        result["rps"] = {
            "sla":       sla,
            "before":    before.rps,
            "after":     after.rps,
            "delta_pct": calculate_delta(before.rps, after.rps),
            "status":    "PASS" if after.rps >= sla else "FAIL",
            "trend":     _trend(before.rps, after.rps, higher_is_better=True),
        }

    # P99 latência
    if "p99_latency_ms" in nfr:
        sla = nfr["p99_latency_ms"]
        result["p99_latency_ms"] = {
            "sla":       sla,
            "before":    before.p99_ms,
            "after":     after.p99_ms,
            "delta_pct": calculate_delta(before.p99_ms, after.p99_ms),
            "status":    "PASS" if after.p99_ms <= sla else "FAIL",
            "trend":     _trend(before.p99_ms, after.p99_ms, higher_is_better=False),
        }

    # P95 latência
    result["p95_latency_ms"] = {
        "sla":       nfr.get("p95_latency_ms", None),
        "before":    before.p95_ms,
        "after":     after.p95_ms,
        "delta_pct": calculate_delta(before.p95_ms, after.p95_ms),
        "status":    "INFO",
        "trend":     _trend(before.p95_ms, after.p95_ms, higher_is_better=False),
    }

    # Error rate
    error_sla = nfr.get("max_error_rate_pct", 1.0)
    result["error_rate_pct"] = {
        "sla":       error_sla,
        "before":    before.error_rate_pct,
        "after":     after.error_rate_pct,
        "delta_pct": calculate_delta(before.error_rate_pct, after.error_rate_pct),
        "status":    "PASS" if after.error_rate_pct <= error_sla else "FAIL",
        "trend":     _trend(before.error_rate_pct, after.error_rate_pct, higher_is_better=False),
    }

    return result