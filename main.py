"""
SentinelCode — Entry point
───────────────────────────
Uso:
    python main.py --path ./sample_project
    python main.py --path ./meu-projeto --dry-run
    python main.py --path ./meu-projeto --no-iac
    python main.py --path ./meu-projeto --benchmark --nfr '{"target_url":"http://localhost:8080","p99_latency_ms":200}'
"""

import json
import typer
from rich.console import Console
from rich.table   import Table
from rich         import box

from models.state import AgentState
from tools.observability.tracer import setup_tracing, get_run_tags, get_run_metadata
from config import settings

from pathlib import Path

app     = typer.Typer(help="SentinelCode — Análise e correção de performance")
console = Console()


@app.command()
def main(
    path: str = typer.Option(
        ..., "--path", "-p", help="Caminho do projeto a analisar"
    ),
    project_type: str = typer.Option(
        "java-spring", "--type", "-t", help="Tipo do projeto"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Apenas analisa, sem aplicar fixes"
    ),
    with_iac: bool = typer.Option(
        True, "--iac/--no-iac", help="Inclui análise de IaC (Terraform/K8s)"
    ),
    with_benchmark: bool = typer.Option(
        False, "--benchmark", help="Executa Benchmark Agent (requer target_url no --nfr)"
    ),
    with_tests: bool = typer.Option(
        True, "--tests/--no-tests", help="Gera testes automatizados"
    ),
    nfr_json: str = typer.Option(
        "{}", "--nfr", help='NFRs em JSON: \'{"target_url":"http://...","p99_latency_ms":200}\''
    ),
    pdf: bool = typer.Option(
        False, "--pdf", help="Gera relatório em PDF além do HTML (requer weasyprint)"
    ),
):
    """
    Executa o pipeline completo: análise → correção → IaC → benchmark → testes → relatório.
    """
    from agents.orchestrator import build_full_pipeline

    # Parse NFR
    try:
        nfr = json.loads(nfr_json)
    except json.JSONDecodeError:
        console.print("[red]❌ --nfr inválido. Use JSON válido, ex: '{\"p99_latency_ms\": 200}'[/red]")
        raise typer.Exit(1)
    
    tracing_active = setup_tracing(settings)

    # Header
    console.rule("[bold cyan]🤖 SentinelCode[/bold cyan]")
    console.print(f"  Projeto   : [bold]{path}[/bold]")
    console.print(f"  Tipo      : {project_type}")
    console.print(f"  Modo      : {'[yellow]Dry Run[/yellow]' if dry_run else '[green]Completo[/green]'}")
    console.print(f"  IaC       : {'[green]sim[/green]' if with_iac else '[dim]não[/dim]'}")
    console.print(f"  Benchmark : {'[green]sim[/green]' if with_benchmark else '[dim]não[/dim]'}")
    console.print(f"  Testes    : {'[green]sim[/green]' if with_tests and not dry_run else '[dim]não[/dim]'}")
    console.print(f"  LangSmith : {'[green]ativo ✅[/green]' if tracing_active else '[dim]desabilitado[/dim]'}")
    console.print(f"  Formato   : {'[cyan]PDF[/cyan]' if pdf else '[dim]HTML[/dim]'}")
    if nfr:
        console.print(f"  NFR       : {nfr}")
    console.print()

    initial_state: AgentState = {
        "project_path":                path,
        "project_type":                project_type,
        "non_functional_requirements": nfr,
        "java_files":                  [],
        "issues":                      [],
        "iac_files":                   [],
        "infra_gaps":                  [],
        "applied_fixes":               [],
        "test_plan":                   [],
        "generated_tests":             [],
        "test_results":                None,
        "report_format":               "pdf" if pdf else "html",
        "final_report":                None,
        "messages":                    [],
    }

    pipeline = build_full_pipeline(
        dry_run=dry_run,
        with_iac=with_iac,
        with_benchmark=with_benchmark,
        with_tests=with_tests,
    )

    from datetime import datetime
    project_name = Path(path).name
    timestamp    = datetime.now().strftime("%Y%m%d_%H%M%S")

    result = pipeline.invoke(
        initial_state,
        config={
            "run_name": f"sentinel-{project_name}-{timestamp}",
            "tags":     get_run_tags(initial_state, dry_run=dry_run, with_iac=with_iac, with_benchmark=with_benchmark, with_tests=with_tests),
            "metadata": get_run_metadata(initial_state),
        }
    )

    # ── Tabela de issues Java ──
    issues = result.get("issues", [])
    if issues:
        _print_issues_table(issues)

    # ── Tabela de gaps IaC ──
    infra_gaps = result.get("infra_gaps", [])
    if infra_gaps:
        _print_infra_gaps_table(infra_gaps)

    # ── Tabela de fixes ──
    if not dry_run:
        fixes = _deduplicate(result.get("applied_fixes", []))
        if fixes:
            _print_fixes_table(fixes)

    # ── Testes gerados ──
    generated_tests = result.get("generated_tests", [])
    if generated_tests:
        _print_tests_table(generated_tests)

    # ── Link do relatório ──
    report_path = result.get("final_report")
    if report_path:
        console.print()
        console.rule()
        console.print(f"\n  📄 Relatório: [bold cyan]{Path(report_path).resolve()}[/bold cyan]")
        hint = "Abra o PDF no seu visualizador" if pdf else "Abra o arquivo HTML no seu navegador"
        console.print(f"  💡 {hint}\n")


# =============================================================================
# HELPERS — tabelas de output
# =============================================================================

def _print_issues_table(issues):
    colors = {
        "CRÍTICO": "bold red",
        "ALTO":    "bold yellow",
        "MÉDIO":   "bold blue",
        "BAIXO":   "green",
    }
    table = Table(title="📋 Issues Java Encontrados", box=box.ROUNDED, show_lines=True)
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


def _print_infra_gaps_table(gaps):
    table = Table(title="🏗️  Gaps de Infraestrutura", box=box.ROUNDED, show_lines=True)
    table.add_column("#",          style="dim", width=3)
    table.add_column("Categoria",  width=25)
    table.add_column("Recurso",    width=35)
    table.add_column("Severidade", width=10)
    for i, gap in enumerate(gaps, 1):
        sev = getattr(gap, "severity", None)
        sev_val = sev.value if hasattr(sev, "value") else str(sev or "—")
        table.add_row(
            str(i),
            getattr(gap, "category", {}).value if hasattr(getattr(gap, "category", None), "value") else str(getattr(gap, "category", "—")),
            getattr(gap, "resource_name", "—"),
            sev_val,
        )
    console.print(table)


def _print_fixes_table(fixes):
    table = Table(title="🛠️  Fixes Aplicados", box=box.ROUNDED, show_lines=True)
    table.add_column("#",          style="dim", width=3)
    table.add_column("Categoria",  width=22)
    table.add_column("Arquivo",    width=40)
    table.add_column("Status",     width=14)
    for i, fix in enumerate(fixes, 1):
        applied = fix.get("status") == "applied" or fix.get("success")
        status  = "[green]✅ Aplicado[/green]" if applied else "[red]❌ Falhou[/red]"
        table.add_row(
            str(i),
            fix.get("category") or fix.get("issue_category", "—"),
            fix.get("file", fix.get("diff_summary", "—")),
            status,
        )
    console.print(table)


def _print_tests_table(tests):
    table = Table(title="🧪 Testes Gerados", box=box.ROUNDED, show_lines=True)
    table.add_column("#",          style="dim", width=3)
    table.add_column("Categoria",  width=14)
    table.add_column("Endpoint",   width=30)
    table.add_column("Método",     width=8)
    table.add_column("Arquivo",    width=45)
    for i, t in enumerate(tests, 1):
        cat_colors = {
            "functional":  "blue",
            "regression":  "yellow",
            "performance": "magenta",
            "contract":    "cyan",
        }
        cat  = t.get("category", "—")
        color = cat_colors.get(cat, "white")
        table.add_row(
            str(i),
            f"[{color}]{cat}[/{color}]",
            t.get("endpoint", "—"),
            t.get("method", "GET"),
            t.get("file_path", "—"),
        )
    console.print(table)


def _deduplicate(fixes: list) -> list:
    seen, result = set(), []
    for fix in fixes:
        key = (fix.get("category"), fix.get("file"))
        if key not in seen:
            seen.add(key)
            result.append(fix)
    return result


if __name__ == "__main__":
    app()