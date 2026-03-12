"""
Orchestrator
─────────────
Pipeline completo conectando todos os agentes em sequência:

  ┌─ Code Analyzer ──────────────────────────────────┐
  │  read_files → detect_issues → enrich_with_llm    │
  └──────────────────────────────────────────────────┘
           ↓
  ┌─ Fix Agent ───────────────────────────────────────┐
  │  plan_fixes → apply_fixes → validate_fixes        │
  └──────────────────────────────────────────────────┘
           ↓
  ┌─ IaC Analyzer ────────────────────────────────────┐
  │  read_iac_files → detect_infra_gaps               │
  │  → enrich_iac_with_llm                            │
  └──────────────────────────────────────────────────┘
           ↓
  ┌─ IaC Patcher ─────────────────────────────────────┐
  │  plan_iac_patches → apply_iac_patches             │
  │  → validate_iac_patches                           │
  └──────────────────────────────────────────────────┘
           ↓
  ┌─ Benchmark Agent ─────────────────────────────────┐
  │  setup_benchmark → run_before → run_after         │
  │  → compare_benchmarks                             │
  └──────────────────────────────────────────────────┘
           ↓
  ┌─ Test Agent ──────────────────────────────────────┐
  │  plan_tests → generate_tests → run_tests          │
  └──────────────────────────────────────────────────┘
           ↓
  ┌─ Reporter ────────────────────────────────────────┐
  │  build_report_data → render_report                │
  └──────────────────────────────────────────────────┘
"""

from __future__ import annotations

from langgraph.graph import StateGraph, END

from models.state import AgentState

import agents.code_analyzer as _code_analyzer
import agents.fix_agent as _fix_agent
import agents.iac_analyzer as _iac_analyzer
import agents.iac_patcher as _iac_patcher
import agents.benchmark as _benchmark
import agents.test_agent as _test_agent
import agents.reporter as _reporter

from agents.code_analyzer import (
    read_files_node,
    detect_issues_node,
    enrich_with_llm_node,
)
from agents.fix_agent import (
    plan_fixes_node,
    apply_fixes_node,
    validate_fixes_node,
)
from agents.iac_analyzer import (
    read_iac_files_node,
    detect_infra_gaps_node,
    enrich_iac_with_llm_node,
)
from agents.iac_patcher import (
    plan_iac_patches_node,
    apply_iac_patches_node,
    validate_iac_patches_node,
)
from agents.benchmark import (
    setup_benchmark_node,
    run_before_benchmark_node,
    run_after_benchmark_node,
    compare_benchmarks_node,
)
from agents.test_agent import (
    plan_tests_node,
    generate_tests_node,
    run_tests_node,
)
from agents.reporter import generate_report_node

_ALL_AGENT_MODULES = [
    _code_analyzer,
    _fix_agent,
    _iac_analyzer,
    _iac_patcher,
    _benchmark,
    _test_agent,
    _reporter,
]


def build_full_pipeline(
    dry_run:        bool = False,
    with_iac:       bool = True,
    with_benchmark: bool = False,
    with_tests:     bool = True,
    ui=None,
) -> StateGraph:
    """
    Monta o pipeline completo.

    Args:
        dry_run:        Se True, apenas analisa — não aplica fixes.
        with_iac:       Inclui análise e patches de IaC.
        with_benchmark: Inclui Benchmark Agent (requer target_url no NFR).
        with_tests:     Inclui geração de testes automatizados.
        ui:             PipelineUI opcional para output rico no terminal.
    """
    # Injeta UI em todos os módulos de agente (None = fallback para print)
    for mod in _ALL_AGENT_MODULES:
        mod.set_ui(ui)

    graph = StateGraph(AgentState)

    # ── Code Analyzer ──
    graph.add_node("read_files",      read_files_node)
    graph.add_node("detect_issues",   detect_issues_node)
    graph.add_node("enrich_with_llm", enrich_with_llm_node)

    graph.set_entry_point("read_files")
    graph.add_edge("read_files",      "detect_issues")
    graph.add_edge("detect_issues",   "enrich_with_llm")

    last_node = "enrich_with_llm"

    # ── Fix Agent (desabilitado em dry_run) ──
    if not dry_run:
        graph.add_node("plan_fixes",     plan_fixes_node)
        graph.add_node("apply_fixes",    apply_fixes_node)
        graph.add_node("validate_fixes", validate_fixes_node)

        graph.add_edge(last_node,       "plan_fixes")
        graph.add_edge("plan_fixes",    "apply_fixes")
        graph.add_edge("apply_fixes",   "validate_fixes")
        last_node = "validate_fixes"

    # ── IaC Analyzer + Patcher ──
    if with_iac:
        graph.add_node("read_iac_files",      read_iac_files_node)
        graph.add_node("detect_infra_gaps",   detect_infra_gaps_node)
        graph.add_node("enrich_iac_with_llm", enrich_iac_with_llm_node)

        graph.add_edge(last_node,             "read_iac_files")
        graph.add_edge("read_iac_files",      "detect_infra_gaps")
        graph.add_edge("detect_infra_gaps",   "enrich_iac_with_llm")
        last_node = "enrich_iac_with_llm"

        if not dry_run:
            graph.add_node("plan_iac_patches",     plan_iac_patches_node)
            graph.add_node("apply_iac_patches",    apply_iac_patches_node)
            graph.add_node("validate_iac_patches", validate_iac_patches_node)

            graph.add_edge(last_node,              "plan_iac_patches")
            graph.add_edge("plan_iac_patches",     "apply_iac_patches")
            graph.add_edge("apply_iac_patches",    "validate_iac_patches")
            last_node = "validate_iac_patches"

    # ── Benchmark Agent ──
    if with_benchmark:
        graph.add_node("setup_benchmark",      setup_benchmark_node)
        graph.add_node("run_before_benchmark", run_before_benchmark_node)
        graph.add_node("run_after_benchmark",  run_after_benchmark_node)
        graph.add_node("compare_benchmarks",   compare_benchmarks_node)

        graph.add_edge(last_node,              "setup_benchmark")
        graph.add_edge("setup_benchmark",      "run_before_benchmark")
        graph.add_edge("run_before_benchmark", "run_after_benchmark")
        graph.add_edge("run_after_benchmark",  "compare_benchmarks")
        last_node = "compare_benchmarks"

    # ── Test Agent ──
    if with_tests and not dry_run:
        graph.add_node("plan_tests",     plan_tests_node)
        graph.add_node("generate_tests", generate_tests_node)
        graph.add_node("run_tests",      run_tests_node)

        graph.add_edge(last_node,        "plan_tests")
        graph.add_edge("plan_tests",     "generate_tests")
        graph.add_edge("generate_tests", "run_tests")
        last_node = "run_tests"

    # ── Reporter ──
    graph.add_node("generate_report", generate_report_node)

    graph.add_edge(last_node,         "generate_report")
    graph.add_edge("generate_report", END)

    return graph.compile()