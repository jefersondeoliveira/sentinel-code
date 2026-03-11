"""
Orchestrator
─────────────
Grafo principal que conecta todos os agentes em sequência:

  Code Analyzer → Fix Agent → Reporter → END
"""

from langgraph.graph import StateGraph, END

from models.state import AgentState
from agents.code_analyzer import read_files_node, detect_issues_node, enrich_with_llm_node
from agents.fix_agent import plan_fixes_node, apply_fixes_node, validate_fixes_node
from agents.reporter import generate_report_node


def build_full_pipeline() -> StateGraph:
    graph = StateGraph(AgentState)

    # ── Code Analyzer ──
    graph.add_node("read_files",      read_files_node)
    graph.add_node("detect_issues",   detect_issues_node)
    graph.add_node("enrich_with_llm", enrich_with_llm_node)

    # ── Fix Agent ──
    graph.add_node("plan_fixes",      plan_fixes_node)
    graph.add_node("apply_fixes",     apply_fixes_node)
    graph.add_node("validate_fixes",  validate_fixes_node)

    # ── Reporter ──
    graph.add_node("generate_report", generate_report_node)

    # ── Fluxo ──
    graph.set_entry_point("read_files")
    graph.add_edge("read_files",      "detect_issues")
    graph.add_edge("detect_issues",   "enrich_with_llm")
    graph.add_edge("enrich_with_llm", "plan_fixes")
    graph.add_edge("plan_fixes",      "apply_fixes")
    graph.add_edge("apply_fixes",     "validate_fixes")
    graph.add_edge("validate_fixes",  "generate_report")
    graph.add_edge("generate_report", END)

    return graph.compile()