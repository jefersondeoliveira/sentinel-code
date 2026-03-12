"""
Benchmark Agent
────────────────
Executa testes de carga antes e depois dos fixes e compara resultados.

Fluxo:
  1. setup_benchmark_node      → verifica URL, detecta endpoints, gera script
  2. run_before_benchmark_node → executa Locust (fase before)
  3. run_after_benchmark_node  → executa Locust (fase after)
  4. compare_benchmarks_node   → calcula deltas e valida SLAs
"""

from __future__ import annotations

from typing import Optional
from langgraph.graph import StateGraph, END

from models.state import AgentState
from tools.benchmark.runner import check_url_available, run_benchmark
from tools.benchmark.script_generator import generate_locust_script
from tools.benchmark.comparator import compare_benchmarks
from tools.benchmark.models import BenchmarkReport

# ── UI (opcional) ─────────────────────────────────────────────────────────────
_ui: "PipelineUI | None" = None  # type: ignore[name-defined]  # noqa: F821


def set_ui(ui) -> None:
    global _ui
    _ui = ui


def _log(msg: str) -> None:
    if _ui:
        _ui.log(msg)
    else:
        print(msg)


# =============================================================================
# NÓS DO GRAFO
# =============================================================================

def setup_benchmark_node(state: AgentState) -> dict:
    if _ui:
        _ui.agent_start("BENCHMARK", ["setup_benchmark", "run_before", "run_after", "compare_benchmarks"])
        _ui.node_start("setup_benchmark")
    else:
        print("\n⚙️  [1/4] Configurando benchmark...")

    nfr        = state.get("non_functional_requirements", {})
    target_url = nfr.get("target_url", "")

    if not target_url:
        _log("⚠️  target_url não informado — benchmark ignorado.")
        if _ui:
            _ui.node_done("setup_benchmark")
            _ui.agent_done("Benchmark ignorado: sem target_url")
        return {"messages": ["Benchmark ignorado: target_url ausente."]}

    if not check_url_available(target_url):
        _log(f"⚠️  URL não acessível: {target_url}")
        if _ui:
            _ui.node_done("setup_benchmark")
            _ui.agent_done(f"Benchmark ignorado: URL indisponível")
        return {"messages": [f"Benchmark ignorado: URL {target_url} indisponível."]}

    # Detecta endpoints a partir dos issues Java
    endpoints = _extract_endpoints(state)
    script    = generate_locust_script(endpoints, nfr)

    _log(f"✅ URL acessível: {target_url}")
    _log(f"✅ {len(endpoints)} endpoint(s) detectado(s)")

    if _ui:
        _ui.node_done("setup_benchmark")

    return {
        "_benchmark_script":   script,
        "_benchmark_ready":    True,
        "messages": [f"Benchmark configurado: {len(endpoints)} endpoints"],
    }


def run_before_benchmark_node(state: AgentState) -> dict:
    if _ui:
        _ui.node_start("run_before")
    else:
        print("\n📊 [2/4] Executando benchmark BEFORE...")

    if not state.get("_benchmark_ready"):
        _log("⏭️  Benchmark não configurado — pulando.")
        if _ui:
            _ui.node_done("run_before")
        return {"messages": ["Benchmark before: pulado."]}

    nfr    = state.get("non_functional_requirements", {})
    script = state.get("_benchmark_script", "")

    _log("Executando Locust (fase BEFORE)...")
    report = run_benchmark(script, nfr, phase="before")

    if report:
        _log(f"✅ RPS={report.rps:.1f} | P99={report.p99_ms:.0f}ms | Erros={report.error_rate_pct:.1f}%")
        if _ui:
            _ui.node_done("run_before")
        return {
            "_benchmark_before": report,
            "messages": [f"Benchmark before: RPS={report.rps:.1f}, P99={report.p99_ms:.0f}ms"],
        }
    else:
        _log("❌ Benchmark before falhou.")
        if _ui:
            _ui.node_done("run_before")
        return {"messages": ["Benchmark before: falhou."]}


def run_after_benchmark_node(state: AgentState) -> dict:
    if _ui:
        _ui.node_start("run_after")
    else:
        print("\n📊 [3/4] Executando benchmark AFTER...")

    if not state.get("_benchmark_ready"):
        _log("⏭️  Benchmark não configurado — pulando.")
        if _ui:
            _ui.node_done("run_after")
        return {"messages": ["Benchmark after: pulado."]}

    applied = state.get("applied_fixes", [])
    if not any(f.get("status") == "applied" for f in applied):
        _log("⏭️  Nenhum fix aplicado — benchmark after desnecessário.")
        if _ui:
            _ui.node_done("run_after")
        return {"messages": ["Benchmark after: pulado (sem fixes)."]}

    nfr    = state.get("non_functional_requirements", {})
    script = state.get("_benchmark_script", "")

    _log("Executando Locust (fase AFTER)...")
    report = run_benchmark(script, nfr, phase="after")

    if report:
        _log(f"✅ RPS={report.rps:.1f} | P99={report.p99_ms:.0f}ms | Erros={report.error_rate_pct:.1f}%")
        if _ui:
            _ui.node_done("run_after")
        return {
            "_benchmark_after": report,
            "messages": [f"Benchmark after: RPS={report.rps:.1f}, P99={report.p99_ms:.0f}ms"],
        }
    else:
        _log("❌ Benchmark after falhou.")
        if _ui:
            _ui.node_done("run_after")
        return {"messages": ["Benchmark after: falhou."]}


def compare_benchmarks_node(state: AgentState) -> dict:
    if _ui:
        _ui.node_start("compare_benchmarks")
    else:
        print("\n📈 [4/4] Comparando resultados...")

    before: Optional[BenchmarkReport] = state.get("_benchmark_before")
    after:  Optional[BenchmarkReport] = state.get("_benchmark_after")
    nfr    = state.get("non_functional_requirements", {})

    if not before and not after:
        _log("⏭️  Sem dados de benchmark para comparar.")
        if _ui:
            _ui.node_done("compare_benchmarks")
            _ui.agent_done("Sem dados de benchmark")
        return {"messages": ["Comparação: sem dados."]}

    if before and after:
        comparison = compare_benchmarks(before, after, nfr)
        _print_comparison(comparison)
        if _ui:
            _ui.node_done("compare_benchmarks")
            _ui.agent_done("Comparação concluída")
        return {
            "_benchmark_comparison": comparison,
            "messages": ["Comparação de benchmark concluída."],
        }

    if before:
        _log(f"ℹ️  Apenas before disponível: RPS={before.rps:.1f}")
        if _ui:
            _ui.node_done("compare_benchmarks")
            _ui.agent_done(f"Before: RPS={before.rps:.1f}")
        return {"messages": [f"Apenas before: RPS={before.rps:.1f}"]}

    if _ui:
        _ui.node_done("compare_benchmarks")
        _ui.agent_done("Apenas after disponível")
    return {"messages": ["Apenas after disponível."]}


# =============================================================================
# CONSTRUÇÃO DO GRAFO
# =============================================================================

def build_benchmark_graph() -> StateGraph:
    graph = StateGraph(AgentState)

    graph.add_node("setup_benchmark",      setup_benchmark_node)
    graph.add_node("run_before_benchmark", run_before_benchmark_node)
    graph.add_node("run_after_benchmark",  run_after_benchmark_node)
    graph.add_node("compare_benchmarks",   compare_benchmarks_node)

    graph.set_entry_point("setup_benchmark")
    graph.add_edge("setup_benchmark",      "run_before_benchmark")
    graph.add_edge("run_before_benchmark", "run_after_benchmark")
    graph.add_edge("run_after_benchmark",  "compare_benchmarks")
    graph.add_edge("compare_benchmarks",   END)

    return graph.compile()


# =============================================================================
# HELPERS
# =============================================================================

def _extract_endpoints(state: AgentState) -> list:
    """Extrai endpoints dos issues Java detectados."""
    endpoints = []
    for issue in state.get("issues", []):
        file_path = getattr(issue, "file_path", "")
        # Tenta extrair endpoint do código enriquecido
        evidence = getattr(issue, "evidence", "")
        for line in evidence.splitlines():
            if "@GetMapping" in line or "@PostMapping" in line:
                import re
                match = re.search(r'"(/[^"]*)"', line)
                if match:
                    endpoints.append(match.group(1))
    return list(set(endpoints)) or ["/api/v1"]


def _print_comparison(comparison: dict) -> None:
    for metric, data in comparison.items():
        status = data.get("status", "INFO")
        trend  = data.get("trend", "")
        before = data.get("before", "-")
        after  = data.get("after", "-")
        delta  = data.get("delta_pct", 0)
        icon   = "✅" if status == "PASS" else ("ℹ️ " if status == "INFO" else "❌")
        _log(f"{icon} {metric}: {before} → {after} ({delta:+.1f}%) [{trend}]")