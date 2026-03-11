"""
Testes do Benchmark Agent — escritos ANTES da implementação (Spec Driven).

Rode com: pytest tests/unit/test_benchmark.py -v
"""

import pytest
from unittest.mock import patch, MagicMock


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def nfr_benchmark():
    return {
        "target_url":        "http://localhost:8080",
        "max_rps":           1000,
        "p99_latency_ms":    200,
        "duration_seconds":  30,
        "users":             10,
        "spawn_rate":        5,
    }


@pytest.fixture
def sample_endpoints():
    return ["/products", "/orders", "/orders/1"]


@pytest.fixture
def mock_stats_before():
    """Simula stats do Locust antes dos fixes — performance ruim."""
    return {
        "total_requests":   3000,
        "failed_requests":  126,
        "rps":              45.2,
        "p50_ms":           420.0,
        "p95_ms":           680.0,
        "p99_ms":           850.0,
        "min_ms":           35.0,
        "max_ms":           1200.0,
        "error_rate_pct":   4.2,
        "duration_seconds": 30,
    }


@pytest.fixture
def mock_stats_after():
    """Simula stats do Locust depois dos fixes — performance boa."""
    return {
        "total_requests":   33000,
        "failed_requests":  33,
        "rps":              1100.0,
        "p50_ms":           45.0,
        "p95_ms":           120.0,
        "p99_ms":           210.0,
        "min_ms":           8.0,
        "max_ms":           350.0,
        "error_rate_pct":   0.1,
        "duration_seconds": 30,
    }


# =============================================================================
# TESTES — BenchmarkReport (modelo de dados)
# =============================================================================

class TestBenchmarkReport:

    def test_create_benchmark_report(self, mock_stats_before):
        from tools.benchmark.models import BenchmarkReport
        report = BenchmarkReport(phase="before", **mock_stats_before)
        assert report.phase == "before"
        assert report.rps == 45.2
        assert report.p99_ms == 850.0

    def test_benchmark_report_has_timestamp(self, mock_stats_before):
        from tools.benchmark.models import BenchmarkReport
        report = BenchmarkReport(phase="before", **mock_stats_before)
        assert report.timestamp is not None
        assert len(report.timestamp) > 0

    def test_benchmark_report_error_rate(self, mock_stats_before):
        from tools.benchmark.models import BenchmarkReport
        report = BenchmarkReport(phase="before", **mock_stats_before)
        assert report.error_rate_pct == 4.2


# =============================================================================
# TESTES — delta e comparação
# =============================================================================

class TestBenchmarkComparison:

    def test_calculate_delta_rps(self, mock_stats_before, mock_stats_after):
        from tools.benchmark.comparator import calculate_delta
        before_rps = mock_stats_before["rps"]   # 45.2
        after_rps  = mock_stats_after["rps"]    # 1100.0
        delta = calculate_delta(before_rps, after_rps)
        assert delta > 100  # mais de 100% de melhoria

    def test_calculate_delta_negative_improvement(self):
        from tools.benchmark.comparator import calculate_delta
        # P99 caiu de 850 para 210 → delta negativo (melhoria)
        delta = calculate_delta(850.0, 210.0)
        assert delta < 0
        assert abs(delta) > 70  # mais de 70% de redução

    def test_sla_pass_when_below_threshold(self, mock_stats_after, nfr_benchmark):
        from tools.benchmark.comparator import validate_slas
        from tools.benchmark.models import BenchmarkReport
        after = BenchmarkReport(phase="after", **mock_stats_after)
        result = validate_slas(after, nfr_benchmark)
        # RPS: after=1100, sla=1000 → PASS
        assert result["rps"]["status"] == "PASS"

    def test_sla_fail_when_above_latency_threshold(self, mock_stats_after, nfr_benchmark):
        from tools.benchmark.comparator import validate_slas
        from tools.benchmark.models import BenchmarkReport
        after = BenchmarkReport(phase="after", **mock_stats_after)
        # p99=210ms, sla=200ms → FAIL (mas melhorou)
        result = validate_slas(after, nfr_benchmark)
        assert result["p99_latency_ms"]["status"] == "FAIL"
        assert result["p99_latency_ms"]["trend"] == "IMPROVING"

    def test_sla_validation_has_all_keys(self, mock_stats_after, nfr_benchmark):
        from tools.benchmark.comparator import validate_slas
        from tools.benchmark.models import BenchmarkReport
        after = BenchmarkReport(phase="after", **mock_stats_after)
        result = validate_slas(after, nfr_benchmark)
        for key in result:
            assert "sla" in result[key]
            assert "after" in result[key]
            assert "delta_pct" in result[key]
            assert "status" in result[key]
            assert "trend" in result[key]

    def test_compare_before_and_after(self, mock_stats_before, mock_stats_after, nfr_benchmark):
        from tools.benchmark.comparator import compare_benchmarks
        from tools.benchmark.models import BenchmarkReport
        before = BenchmarkReport(phase="before", **mock_stats_before)
        after  = BenchmarkReport(phase="after",  **mock_stats_after)
        result = compare_benchmarks(before, after, nfr_benchmark)
        assert result["rps"]["before"] == 45.2
        assert result["rps"]["after"]  == 1100.0
        assert result["rps"]["status"] == "PASS"

    def test_improving_trend_when_latency_reduced(self, mock_stats_before, mock_stats_after, nfr_benchmark):
        from tools.benchmark.comparator import compare_benchmarks
        from tools.benchmark.models import BenchmarkReport
        before = BenchmarkReport(phase="before", **mock_stats_before)
        after  = BenchmarkReport(phase="after",  **mock_stats_after)
        result = compare_benchmarks(before, after, nfr_benchmark)
        assert result["p99_latency_ms"]["trend"] == "IMPROVING"

    def test_degrading_trend_when_latency_increased(self, mock_stats_before, nfr_benchmark):
        from tools.benchmark.comparator import compare_benchmarks
        from tools.benchmark.models import BenchmarkReport
        before = BenchmarkReport(phase="before", **mock_stats_before)
        # after pior que before
        worse_stats = {**mock_stats_before, "p99_ms": 1200.0, "rps": 30.0}
        after  = BenchmarkReport(phase="after", **worse_stats)
        result = compare_benchmarks(before, after, nfr_benchmark)
        assert result["p99_latency_ms"]["trend"] == "DEGRADING"


# =============================================================================
# TESTES — geração do script Locust
# =============================================================================

class TestLocustScriptGeneration:

    def test_generates_valid_python_script(self, sample_endpoints, nfr_benchmark):
        from tools.benchmark.script_generator import generate_locust_script
        script = generate_locust_script(sample_endpoints, nfr_benchmark)
        assert "from locust import" in script
        assert "HttpUser" in script

    def test_script_has_task_for_each_endpoint(self, sample_endpoints, nfr_benchmark):
        from tools.benchmark.script_generator import generate_locust_script
        script = generate_locust_script(sample_endpoints, nfr_benchmark)
        for endpoint in sample_endpoints:
            assert endpoint in script

    def test_script_has_wait_time(self, sample_endpoints, nfr_benchmark):
        from tools.benchmark.script_generator import generate_locust_script
        script = generate_locust_script(sample_endpoints, nfr_benchmark)
        assert "wait_time" in script

    def test_empty_endpoints_returns_default_script(self, nfr_benchmark):
        from tools.benchmark.script_generator import generate_locust_script
        script = generate_locust_script([], nfr_benchmark)
        assert "HttpUser" in script
        # deve ter pelo menos um task padrão
        assert "@task" in script

    def test_script_uses_target_url(self, sample_endpoints, nfr_benchmark):
        from tools.benchmark.script_generator import generate_locust_script
        script = generate_locust_script(sample_endpoints, nfr_benchmark)
        # host deve ser configurável via NFR
        assert "host" in script or "localhost:8080" in script


# =============================================================================
# TESTES — URL health check
# =============================================================================

class TestUrlHealthCheck:

    def test_returns_true_when_url_available(self):
        from tools.benchmark.runner import check_url_available
        with patch("tools.benchmark.runner.requests.get") as mock_get:
            mock_get.return_value = MagicMock(status_code=200)
            assert check_url_available("http://localhost:8080") is True

    def test_returns_false_when_url_unavailable(self):
        from tools.benchmark.runner import check_url_available
        import requests
        with patch("tools.benchmark.runner.requests.get") as mock_get:
            mock_get.side_effect = requests.exceptions.ConnectionError()
            assert check_url_available("http://localhost:8080") is False

    def test_returns_false_on_timeout(self):
        from tools.benchmark.runner import check_url_available
        import requests
        with patch("tools.benchmark.runner.requests.get") as mock_get:
            mock_get.side_effect = requests.exceptions.Timeout()
            assert check_url_available("http://localhost:8080") is False


# =============================================================================
# TESTES — pipeline do Benchmark Agent
# =============================================================================

class TestBenchmarkAgentPipeline:

    def _base_state(self, nfr):
        return {
            "project_path":                "/tmp/test",
            "project_type":                "java-spring",
            "non_functional_requirements": nfr,
            "java_files":     [],
            "issues":         [],
            "iac_files":      [],
            "infra_gaps":     [],
            "applied_fixes":  [],
            "final_report":   None,
            "messages":       [],
        }

    def test_pipeline_skips_when_url_unavailable(self, nfr_benchmark):
        from agents.benchmark import build_benchmark_graph
        with patch("tools.benchmark.runner.check_url_available", return_value=False):
            state  = self._base_state(nfr_benchmark)
            graph  = build_benchmark_graph()
            result = graph.invoke(state)
            # Sem URL, benchmark é pulado mas pipeline não quebra
            assert result["messages"] is not None

    def test_pipeline_skips_when_no_target_url(self):
        from agents.benchmark import build_benchmark_graph
        nfr_no_url = {"max_rps": 1000, "p99_latency_ms": 200}
        state  = self._base_state(nfr_no_url)
        graph  = build_benchmark_graph()
        result = graph.invoke(state)
        assert result is not None

    def test_pipeline_runs_benchmark_when_url_available(self, nfr_benchmark):
        from agents.benchmark import build_benchmark_graph
        from tools.benchmark.models import BenchmarkReport

        mock_report = BenchmarkReport(
            phase="before",
            total_requests=3000,
            failed_requests=10,
            rps=100.0,
            p50_ms=50.0,
            p95_ms=150.0,
            p99_ms=200.0,
            min_ms=10.0,
            max_ms=500.0,
            error_rate_pct=0.3,
            duration_seconds=30,
        )

        with patch("tools.benchmark.runner.check_url_available", return_value=True), \
             patch("tools.benchmark.runner.run_benchmark", return_value=mock_report):
            state  = self._base_state(nfr_benchmark)
            graph  = build_benchmark_graph()
            result = graph.invoke(state)
            assert len(result["messages"]) > 0