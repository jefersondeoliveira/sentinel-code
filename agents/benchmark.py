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

from typing import Optional
from langgraph.graph import StateGraph, END

from models.state import AgentState
from tools.benchmark.runner import check_url_available, run_benchmark
from tools.benchmark.script_generator import generate_locust_script
from tools.benchmark.comparator import compare_benchmarks
from tools.benchmark.models import BenchmarkReport


# =============================================================================
# NÓS DO GRAFO
# =============================================================================

def setup_benchmark_node(state: AgentState) -> dict:
    print("\n⚙️  [1/4] Configurando benchmark...")

    nfr        = state.get("non_functional_requirements", {})
    target_url = nfr.get("target_url", "")

    if not target_url:
        print("    ⚠️  target_url não informado nos NFRs — benchmark ignorado.")
        return {"messages": ["Benchmark ignorado: target_url ausente."]}

    if not check_url_available(target_url):
        print(f"    ⚠️  URL não acessível: {target_url} — benchmark ignorado.")
        return {"messages": [f"Benchmark ignorado: URL {target_url} indisponível."]}

    # Detecta endpoints a partir dos issues Java
    endpoints = _extract_endpoints(state)
    script    = generate_locust_script(endpoints, nfr)

    print(f"    ✅ URL acessível: {target_url}")
    print(f"    ✅ {len(endpoints)} endpoint(s) detectado(s)")

    return {
        "_benchmark_script":   script,
        "_benchmark_ready":    True,
        "messages": [f"Benchmark configurado: {len(endpoints)} endpoints"],
    }


def run_before_benchmark_node(state: AgentState) -> dict:
    print("\n📊 [2/4] Executando benchmark BEFORE...")

    if not state.get("_benchmark_ready"):
        print("    ⏭️  Benchmark não configurado — pulando.")
        return {"messages": ["Benchmark before: pulado."]}

    nfr    = state.get("non_functional_requirements", {})
    script = state.get("_benchmark_script", "")

    report = run_benchmark(script, nfr, phase="before")

    if report:
        print(f"    ✅ Before: RPS={report.rps:.1f} | P99={report.p99_ms:.0f}ms | Erros={report.error_rate_pct:.1f}%")
        return {
            "_benchmark_before": report,
            "messages": [f"Benchmark before: RPS={report.rps:.1f}, P99={report.p99_ms:.0f}ms"],
        }
    else:
        print("    ❌ Benchmark before falhou.")
        return {"messages": ["Benchmark before: falhou."]}


def run_after_benchmark_node(state: AgentState) -> dict:
    print("\n📊 [3/4] Executando benchmark AFTER...")

    if not state.get("_benchmark_ready"):
        print("    ⏭️  Benchmark não configurado — pulando.")
        return {"messages": ["Benchmark after: pulado."]}

    applied = state.get("applied_fixes", [])
    if not any(f.get("status") == "applied" for f in applied):
        print("    ⏭️  Nenhum fix aplicado — benchmark after desnecessário.")
        return {"messages": ["Benchmark after: pulado (sem fixes)."]}

    nfr    = state.get("non_functional_requirements", {})
    script = state.get("_benchmark_script", "")

    report = run_benchmark(script, nfr, phase="after")

    if report:
        print(f"    ✅ After: RPS={report.rps:.1f} | P99={report.p99_ms:.0f}ms | Erros={report.error_rate_pct:.1f}%")
        return {
            "_benchmark_after": report,
            "messages": [f"Benchmark after: RPS={report.rps:.1f}, P99={report.p99_ms:.0f}ms"],
        }
    else:
        print("    ❌ Benchmark after falhou.")
        return {"messages": ["Benchmark after: falhou."]}


def compare_benchmarks_node(state: AgentState) -> dict:
    print("\n📈 [4/4] Comparando resultados...")

    before: Optional[BenchmarkReport] = state.get("_benchmark_before")
    after:  Optional[BenchmarkReport] = state.get("_benchmark_after")
    nfr    = state.get("non_functional_requirements", {})

    if not before and not after:
        print("    ⏭️  Sem dados de benchmark para comparar.")
        return {"messages": ["Comparação: sem dados."]}

    if before and after:
        comparison = compare_benchmarks(before, after, nfr)
        _print_comparison(comparison)
        return {
            "_benchmark_comparison": comparison,
            "messages": ["Comparação de benchmark concluída."],
        }

    if before:
        print(f"    ℹ️  Apenas before disponível: RPS={before.rps:.1f}")
        return {"messages": [f"Apenas before: RPS={before.rps:.1f}"]}

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
        print(f"    {icon} {metric}: {before} → {after} ({delta:+.1f}%) [{trend}]")