"""
Reporter Agent
───────────────
Consolida o AgentState completo (issues + fixes) num relatório HTML.

Não usa LLM — tudo é renderização de template Jinja2 com os dados
já coletados pelos agentes anteriores. Rápido e sem custo de API.

Saída: arquivo HTML salvo em ./outputs/report_<timestamp>.html
"""

import os
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from langgraph.graph import StateGraph, END

from models.state import AgentState
from models.issue import Severity


def generate_report_node(state: AgentState) -> dict:
    """
    Nó único: prepara os dados e renderiza o relatório HTML em um passo só.
    Evita o problema de campos temporários não persistidos entre nós.
    """
    print("\n📊 [1/2] Preparando dados do relatório...")

    issues = state.get("_enriched_issues") or state.get("issues", [])
    fixes  = state.get("applied_fixes", [])

    # Deduplica fixes
    seen, unique_fixes = set(), []
    for fix in fixes:
        key = (fix.get("issue_category"), fix.get("file_path"), fix.get("diff_summary"))
        if key not in seen:
            seen.add(key)
            unique_fixes.append(fix)

    counts = {
        "critical": sum(1 for i in issues if i.severity == Severity.CRITICAL),
        "high":     sum(1 for i in issues if i.severity == Severity.HIGH),
        "medium":   sum(1 for i in issues if i.severity == Severity.MEDIUM),
        "low":      sum(1 for i in issues if i.severity == Severity.LOW),
        "fixed":    sum(1 for f in unique_fixes if f.get("success")),
        "total":    len(issues),
    }

    issues_data = []
    for issue in issues:
        fix_record = next(
            (f for f in unique_fixes if issue.category.value in f.get("issue_category", "")),
            None
        )
        before = fix_record.get("original_snippet") if fix_record else issue.before_code
        after  = fix_record.get("fixed_snippet")    if fix_record else issue.after_code
        issues_data.append({
            "category":    issue.category.value,
            "severity":    issue.severity.value,
            "file_path":   issue.file_path,
            "line":        issue.line,
            "root_cause":  issue.root_cause,
            "suggestion":  issue.suggestion,
            "evidence":    issue.evidence,
            "before_code": before,
            "after_code":  after,
        })

    project_name = Path(state.get("project_path", ".")).name
    context = {
        "project_name":  project_name,
        "project_type":  state.get("project_type", "java-spring"),
        "generated_at":  datetime.now().strftime("%d/%m/%Y %H:%M"),
        "counts":        counts,
        "issues":        issues_data,
        "fixes":         unique_fixes,
        "messages":      state.get("messages", []),
    }

    print(f"    ✅ {len(issues_data)} issue(s) | {len(unique_fixes)} fix(es) preparados")
    print("\n📝 [2/2] Renderizando relatório HTML...")

    templates_dir = Path(__file__).parent.parent / "templates"
    env = Environment(
        loader=FileSystemLoader(str(templates_dir)),
        autoescape=select_autoescape(["html"]),
    )
    html_content = env.get_template("report.html.j2").render(**context)

    output_dir = Path("outputs")
    output_dir.mkdir(exist_ok=True)
    timestamp    = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path  = output_dir / f"report_{project_name}_{timestamp}.html"
    output_path.write_text(html_content, encoding="utf-8")

    print(f"    ✅ Relatório salvo em: {output_path}")

    return {
        "final_report": str(output_path),
        "messages": [f"Relatório gerado: {output_path}"],
    }


def build_reporter_graph() -> StateGraph:
    graph = StateGraph(AgentState)
    graph.add_node("generate_report", generate_report_node)
    graph.set_entry_point("generate_report")
    graph.add_edge("generate_report", END)
    return graph.compile()