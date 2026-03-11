"""
Benchmark Runner — executa Locust programaticamente.
"""

import time
import tempfile
import importlib.util
from typing import Optional

import requests

from tools.benchmark.models import BenchmarkReport


def check_url_available(url: str, timeout: int = 5) -> bool:
    """Verifica se a URL alvo está acessível."""
    try:
        response = requests.get(url, timeout=timeout)
        return response.status_code < 500
    except (requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
            requests.exceptions.RequestException):
        return False


def run_benchmark(
    script_content: str,
    nfr: dict,
    phase: str = "before",
) -> Optional[BenchmarkReport]:
    """
    Executa o Locust programaticamente e retorna BenchmarkReport.

    Args:
        script_content: código Python do script Locust
        nfr:            requisitos não funcionais (users, duration, etc.)
        phase:          "before" ou "after"

    Returns:
        BenchmarkReport ou None se falhar
    """
    try:
        return _run_locust(script_content, nfr, phase)
    except Exception as e:
        print(f"    ❌ Benchmark falhou: {e}")
        return None


def _run_locust(script_content: str, nfr: dict, phase: str) -> BenchmarkReport:
    """Executa Locust via API programática."""
    from locust.env import Environment
    from locust.stats import StatsEntry
    import gevent

    users         = nfr.get("users", 10)
    spawn_rate    = nfr.get("spawn_rate", 5)
    duration      = max(nfr.get("duration_seconds", 30), 30)  # mínimo 30s
    target_url    = nfr.get("target_url", "http://localhost:8080")

    # Carrega a classe do script dinamicamente
    user_class = _load_user_class(script_content, target_url)

    env    = Environment(user_classes=[user_class])
    runner = env.create_local_runner()

    runner.start(user_count=users, spawn_rate=spawn_rate)
    gevent.sleep(duration)
    runner.stop()
    runner.quit()

    stats = env.runner.stats.total
    return _build_report(stats, phase, duration)


def _load_user_class(script_content: str, target_url: str):
    """Carrega dinamicamente a classe HttpUser do script gerado."""
    import types
    module = types.ModuleType("sentinel_locust_script")
    exec(compile(script_content, "sentinel_locust_script", "exec"), module.__dict__)

    # Encontra subclasse de HttpUser
    from locust import HttpUser
    for name in dir(module):
        obj = getattr(module, name)
        try:
            if isinstance(obj, type) and issubclass(obj, HttpUser) and obj is not HttpUser:
                obj.host = target_url
                return obj
        except TypeError:
            pass

    raise RuntimeError("Nenhuma classe HttpUser encontrada no script Locust")


def _build_report(stats, phase: str, duration: int) -> BenchmarkReport:
    """Constrói BenchmarkReport a partir das stats do Locust."""
    total    = stats.num_requests
    failed   = stats.num_failures
    error_rt = (failed / total * 100) if total > 0 else 0.0

    return BenchmarkReport(
        phase=phase,
        total_requests=total,
        failed_requests=failed,
        rps=round(stats.current_rps or (total / duration), 2),
        p50_ms=round(stats.get_response_time_percentile(0.50) or 0, 2),
        p95_ms=round(stats.get_response_time_percentile(0.95) or 0, 2),
        p99_ms=round(stats.get_response_time_percentile(0.99) or 0, 2),
        min_ms=round(stats.min_response_time or 0, 2),
        max_ms=round(stats.max_response_time or 0, 2),
        error_rate_pct=round(error_rt, 2),
        duration_seconds=duration,
    )