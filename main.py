"""
SentinelCode — Entry point
────────────────────────
Uso:
    python main.py --path ./sample_project
    python main.py --path ./meu-projeto --dry-run
"""

import typer
from rich.console import Console
from rich.table import Table
from rich import box
from langgraph.graph import StateGraph, END
from models.state import AgentState

app = typer.Typer(help="SentinelCode — Análise e correção de performance")
console = Console()


@app.command()
def main(
    path: str = typer.Option(..., "--path", "-p", help="Caminho do projeto a analisar"),
    project_type: str = typer.Option("java-spring", "--type", "-t", help="Tipo do projeto"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Apenas analisa, sem aplicar fixes"),
):
    """
    Executa o pipeline completo: análise + correção + relatório HTML.
    """
    from agents.code_analyzer import read_files_node, detect_issues_node, enrich_with_llm_node
    from agents.reporter import generate_report_node

    console.rule("[bold cyan]🤖 SentinelCode[/bold cyan]")
    console.print(f"  Projeto : [bold]{path}[/bold]")
    console.print(f"  Tipo    : {project_type}")
    console.print(f"  Modo    : {'[yellow]Dry Run (sem fixes)[/yellow]' if dry_run else '[green]Completo (análise + fixes)[/green]'}")
    console.print()

    initial_state = {
        "project_path": path,
        "project_type": project_type,
        "non_functional_requirements": {},
        "java_files": [],
        "issues": [],
        "applied_fixes": [],
        "final_report": None,
        "messages": [],
    }

    # ── Monta o grafo ──
    graph = StateGraph(AgentState)

    graph.add_node("read_files",       read_files_node)
    graph.add_node("detect_issues",    detect_issues_node)
    graph.add_node("enrich_with_llm",  enrich_with_llm_node)
    graph.add_node("generate_report",  generate_report_node)

    graph.set_entry_point("read_files")
    graph.add_edge("read_files",      "detect_issues")
    graph.add_edge("detect_issues",   "enrich_with_llm")

    if not dry_run:
        from agents.fix_agent import plan_fixes_node, apply_fixes_node, validate_fixes_node
        graph.add_node("plan_fixes",     plan_fixes_node)
        graph.add_node("apply_fixes",    apply_fixes_node)
        graph.add_node("validate_fixes", validate_fixes_node)
        graph.add_edge("enrich_with_llm", "plan_fixes")
        graph.add_edge("plan_fixes",      "apply_fixes")
        graph.add_edge("apply_fixes",     "validate_fixes")
        graph.add_edge("validate_fixes",  "generate_report")
    else:
        graph.add_edge("enrich_with_llm", "generate_report")

    graph.add_edge("generate_report", END)

    pipeline = graph.compile()
    result   = pipeline.invoke(initial_state)

    # ── Tabela de issues ──
    issues = result.get("_enriched_issues") or result.get("issues", [])
    if issues:
        _print_issues_table(issues)

    # ── Tabela de fixes ──
    if not dry_run:
        fixes = _deduplicate(result.get("applied_fixes", []))
        if fixes:
            _print_fixes_table(fixes)

    # ── Link do relatório ──
    report_path = result.get("final_report")
    if report_path:
        from pathlib import Path
        console.print()
        console.rule()
        console.print(f"\n  📄 Relatório: [bold cyan]{Path(report_path).resolve()}[/bold cyan]")
        console.print("  💡 Abra o arquivo HTML no seu navegador\n")


# =============================================================================
# HELPERS
# =============================================================================

def _print_issues_table(issues):
    colors = {
        "CRÍTICO": "bold red",
        "ALTO":    "bold yellow",
        "MÉDIO":   "bold blue",
        "BAIXO":   "green",
    }
    table = Table(title="📋 Issues Encontrados", box=box.ROUNDED, show_lines=True)
    table.add_column("#",          style="dim", width=3)
    table.add_column("Severidade", width=10)
    table.add_column("Categoria",  width=22)
    table.add_column("Arquivo",    width=45)
    table.add_column("Linha",      width=6)
    for i, issue in enumerate(issues, 1):
        c = colors.get(issue.severity.value, "white")
        table.add_row(
            str(i),
            f"[{c}]{issue.severity.value}[/{c}]",
            issue.category.value,
            issue.file_path,
            str(issue.line or "—"),
        )
    console.print(table)


def _print_fixes_table(fixes):
    table = Table(title="🛠️  Fixes Aplicados", box=box.ROUNDED, show_lines=True)
    table.add_column("#",          style="dim", width=3)
    table.add_column("Categoria",  width=22)
    table.add_column("Alterações", width=40)
    table.add_column("Status",     width=14)
    for i, fix in enumerate(fixes, 1):
        status = "[green]✅ Aplicado[/green]" if fix.get("success") else "[red]❌ Falhou[/red]"
        table.add_row(
            str(i),
            fix.get("issue_category", "—"),
            fix.get("diff_summary",   "—"),
            status,
        )
    console.print(table)


def _deduplicate(fixes: list) -> list:
    seen, result = set(), []
    for fix in fixes:
        key = (fix.get("issue_category"), fix.get("diff_summary"))
        if key not in seen:
            seen.add(key)
            result.append(fix)
    return result


if __name__ == "__main__":
    app()