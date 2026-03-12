"""
IaC Patcher Agent
──────────────────
Aplica correções nos arquivos IaC identificados pelo IaC Analyzer.

Fluxo:
  1. plan_iac_patches_node    → filtra gaps patcháveis
  2. apply_iac_patches_node   → aplica cada patch
  3. validate_iac_patches_node → valida e atualiza flags
"""

from __future__ import annotations

from langgraph.graph import StateGraph, END
from models.state import AgentState
from tools.iac.iac_patcher import apply_iac_patch
from models.infra_gap import InfraGap

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

def plan_iac_patches_node(state: AgentState) -> dict:
    if _ui:
        _ui.agent_start("IAC PATCHER", ["plan_iac_patches", "apply_iac_patches", "validate_iac_patches"])
        _ui.node_start("plan_iac_patches")
    else:
        print("\n🗂️  [1/3] Planejando patches IaC...")

    gaps = state.get("infra_gaps", [])
    fixable   = [g for g in gaps if not g.fix_applied]
    unfixable = [g for g in gaps if g.fix_applied]

    _log(f"✅ Patchável automaticamente: {len(fixable)}")
    _log(f"⏭️  Já corrigido / skip:       {len(unfixable)}")

    if _ui:
        _ui.node_done("plan_iac_patches")

    return {"messages": [f"IaC Patcher: {len(fixable)} gaps para aplicar"]}


def apply_iac_patches_node(state: AgentState) -> dict:
    if _ui:
        _ui.node_start("apply_iac_patches")
    else:
        print("\n🛠️  [2/3] Aplicando patches IaC...")

    gaps         = state.get("infra_gaps", [])
    project_path = state["project_path"]
    fixable      = [g for g in gaps if not g.fix_applied]

    if not fixable:
        _log("⚠️  Nenhum gap para aplicar.")
        if _ui:
            _ui.node_done("apply_iac_patches")
        return {"applied_fixes": [], "messages": ["Nenhum patch IaC aplicado."]}

    applied_fixes = []
    updated_gaps  = list(gaps)

    for i, gap in enumerate(fixable):
        _log(f"[{i+1}/{len(fixable)}] {gap.category.value} — {gap.resource}")

        result = apply_iac_patch(gap, project_path)
        applied_fixes.append(result)

        if result["status"] == "applied":
            _log("✅ Patch aplicado")
            # Atualiza o gap original com fix_applied=True
            idx = next(
                (j for j, g in enumerate(updated_gaps) if g is gap),
                None
            )
            if idx is not None:
                import dataclasses
                updated_gaps[idx] = dataclasses.replace(gap, fix_applied=True)
        elif result["status"] == "skipped":
            _log(f"⏭️  Skip: {result.get('reason', '')}")
        else:
            _log(f"❌ Falhou: {result.get('reason', '')}")

    applied_count = sum(1 for f in applied_fixes if f["status"] == "applied")
    _log(f"✅ {applied_count}/{len(fixable)} patch(es) aplicado(s)")

    if _ui:
        _ui.node_done("apply_iac_patches")

    return {
        "applied_fixes": applied_fixes,
        "infra_gaps":    [],   # será sobrescrito pelo reduce de operator.add
        "messages":      [f"IaC Patcher: {applied_count} patches aplicados"],
    }


def validate_iac_patches_node(state: AgentState) -> dict:
    if _ui:
        _ui.node_start("validate_iac_patches")
    else:
        print("\n✔️  [3/3] Validando patches IaC...")

    fixes = state.get("applied_fixes", [])
    iac_fixes = [f for f in fixes if "strategy" in f]

    applied  = sum(1 for f in iac_fixes if f["status"] == "applied")
    skipped  = sum(1 for f in iac_fixes if f["status"] == "skipped")
    failed   = sum(1 for f in iac_fixes if f["status"] == "failed")

    _log(f"Aplicados: {applied} | Skipped: {skipped} | Falhas: {failed}")

    if _ui:
        _ui.node_done("validate_iac_patches")
        _ui.agent_done(f"{applied} patch(es) aplicado(s)")

    return {"messages": [f"Validação IaC: {applied} OK, {failed} falhas"]}


# =============================================================================
# CONSTRUÇÃO DO GRAFO
# =============================================================================

def build_iac_patcher_graph() -> StateGraph:
    graph = StateGraph(AgentState)

    graph.add_node("plan_iac_patches",    plan_iac_patches_node)
    graph.add_node("apply_iac_patches",   apply_iac_patches_node)
    graph.add_node("validate_iac_patches", validate_iac_patches_node)

    graph.set_entry_point("plan_iac_patches")
    graph.add_edge("plan_iac_patches",    "apply_iac_patches")
    graph.add_edge("apply_iac_patches",   "validate_iac_patches")
    graph.add_edge("validate_iac_patches", END)

    return graph.compile()