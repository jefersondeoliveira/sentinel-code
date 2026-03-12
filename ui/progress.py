"""
PipelineUI — Interface de terminal rica para o SentinelCode
────────────────────────────────────────────────────────────
Cada agente do pipeline ganha um painel Rich animado que aparece,
atualiza em tempo real com spinner + logs verbosos, e "trava"
completo ao terminar (scroll natural no terminal).

Ao final do pipeline, render_summary() exibe cards de métricas.

Uso:
    ui = PipelineUI()
    try:
        ui.agent_start("CODE ANALYZER", ["read_files", "detect_issues"])
        ui.node_start("read_files")
        ui.log("Lendo arquivos Java...")
        ui.node_done("read_files")
        ui.agent_done("7 issues encontrados")
    finally:
        ui.close()
    ui.render_summary(state, with_iac=True, with_benchmark=False)

Regras internas:
    - log() NUNCA chama print() — usa live.update() para não corromper o terminal
    - print() só é chamado quando _ui is None (sem UI ativa)
    - close() garante que o Live é parado mesmo em exceção
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

if TYPE_CHECKING:
    pass

_SPINNER = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
_MAX_LOGS = 6


class _AgentRenderable:
    """
    Renderable dinâmico: chamado pelo Rich a cada refresh_per_second.
    Computa o painel a partir do estado atual do PipelineUI,
    garantindo que spinner e timer animem automaticamente.
    """

    def __init__(self, ui: "PipelineUI") -> None:
        self._ui = ui

    def __rich_console__(self, console, options):  # type: ignore[override]
        yield self._ui._build_panel()


class PipelineUI:
    """Interface de terminal rica para o pipeline SentinelCode."""

    def __init__(self) -> None:
        self.console = Console()
        self._live: Live | None = None
        self._renderable: _AgentRenderable | None = None
        self._agent_name: str = ""
        self._nodes: list[str] = []
        self._node_states: list[str] = []   # "pending" | "running" | "done"
        self._logs: list[str] = []
        self._start: float = 0.0
        self.completed: list[dict] = []     # {name, summary, elapsed}

    # ── API Pública ──────────────────────────────────────────────────────────

    def agent_start(self, name: str, nodes: list[str]) -> None:
        """Inicia painel Rich.Live para este agente."""
        self._agent_name = name
        self._nodes = list(nodes)
        self._node_states = ["pending"] * len(nodes)
        self._logs = []
        self._start = time.time()
        self._renderable = _AgentRenderable(self)
        self._live = Live(
            self._renderable,
            console=self.console,
            refresh_per_second=4,
            transient=False,
        )
        self._live.start()

    def node_start(self, node_name: str) -> None:
        """Marca nó como running e limpa logs do nó anterior."""
        if node_name in self._nodes:
            idx = self._nodes.index(node_name)
            self._node_states[idx] = "running"
        self._logs = []
        self._refresh()

    def node_done(self, node_name: str) -> None:
        """Marca nó como done."""
        if node_name in self._nodes:
            idx = self._nodes.index(node_name)
            self._node_states[idx] = "done"
        self._refresh()

    def log(self, message: str) -> None:
        """
        Adiciona linha de log inline sob o nó atual (mantém últimas 6).
        NUNCA chama print() — atualiza o Live diretamente.
        """
        self._logs.append(message)
        self._logs = self._logs[-_MAX_LOGS:]
        self._refresh()

    def agent_done(self, summary: str) -> None:
        """Para o Live com painel verde (completo) e registra o agente."""
        elapsed = time.time() - self._start
        self._node_states = ["done"] * len(self._nodes)
        self._logs = []
        if self._live:
            self._live.update(self._build_panel(done=True))
            self._live.stop()
            self._live = None
        self.completed.append({
            "name": self._agent_name,
            "summary": summary,
            "elapsed": elapsed,
        })

    def close(self) -> None:
        """Para qualquer Live ativo — chamar em bloco finally."""
        if self._live:
            self._live.stop()
            self._live = None

    def render_summary(
        self,
        state: dict,
        *,
        with_iac: bool = True,
        with_benchmark: bool = False,
    ) -> None:
        """Renderiza cards de métricas finais após o pipeline."""
        from models.issue import IssueCategory

        issues = state.get("issues", [])
        all_fixes = state.get("applied_fixes", [])
        fixes = [
            f for f in all_fixes
            if f.get("success") or f.get("status") == "applied"
        ]
        iac_gaps = state.get("infra_gaps", []) if with_iac else []
        total_elapsed = sum(a["elapsed"] for a in self.completed)

        # Issues que requerem ação manual (não têm fix automático)
        manual_categories = {
            IssueCategory.PAGINATION,
            IssueCategory.LAZY_LOADING,
            IssueCategory.THREAD_BLOCKING,
            IssueCategory.MISSING_INDEX,
        }
        manual_issues = [i for i in issues if i.category in manual_categories]

        # ── Cards de métricas ──
        metrics = Table(
            box=box.SIMPLE_HEAVY,
            padding=(0, 3),
            show_header=False,
            show_edge=False,
        )
        metrics.add_column(justify="center", style="bold", min_width=10)
        metrics.add_column(justify="center", style="bold", min_width=10)
        metrics.add_column(justify="center", style="bold", min_width=10)
        metrics.add_column(justify="center", style="bold", min_width=10)

        metrics.add_row(
            f"[bold cyan]{len(issues)}[/bold cyan]",
            f"[bold green]{len(fixes)}[/bold green]",
            f"[bold yellow]{len(iac_gaps)}[/bold yellow]" if with_iac else "[dim]—[/dim]",
            f"[bold white]{_fmt_elapsed(total_elapsed)}[/bold white]",
        )
        metrics.add_row(
            "[dim]issues[/dim]",
            "[dim]fixes[/dim]",
            "[dim]iac gaps[/dim]" if with_iac else "[dim]iac[/dim]",
            "[dim]total[/dim]",
        )

        # ── Corpo: alertas + relatório ──
        body = Text()
        body.append("\n")

        if manual_issues:
            body.append("⚠  Ação manual necessária:\n", style="bold yellow")
            for issue in manual_issues:
                body.append(f"   · {issue.category.value}", style="yellow")
                fp = getattr(issue, "file_path", "")
                if fp:
                    body.append(f"  —  {fp}\n", style="dim")
                else:
                    body.append("\n")
            body.append("\n")

        report_path = state.get("final_report")
        if report_path:
            body.append(f"📄  {report_path}\n", style="bold cyan")

        self.console.print()
        self.console.print(
            Panel(
                Group(metrics, body),
                title="[bold cyan]SENTINELCODE — CONCLUÍDO[/bold cyan]",
                border_style="cyan",
                padding=(0, 1),
            )
        )

    # ── Internos ─────────────────────────────────────────────────────────────

    def _refresh(self) -> None:
        """Força re-render do Live sem criar novo renderable."""
        if self._live:
            self._live.update(self._renderable)

    def _build_panel(self, done: bool = False) -> Panel:
        """Monta o Panel Rich com nós, logs inline e barra de progresso."""
        elapsed = time.time() - self._start
        elapsed_str = _fmt_elapsed(elapsed)

        # Spinner frame baseado no tempo de parede → anima automaticamente
        frame = _SPINNER[int(time.time() * 10) % len(_SPINNER)]

        if done:
            border_style = "green"
            title = f"[bold green]✓  {self._agent_name}[/bold green]"
        else:
            border_style = "yellow"
            title = f"[bold yellow]{frame}  {self._agent_name}[/bold yellow]"

        content = Text()

        for node_name, node_state in zip(self._nodes, self._node_states):
            if node_state == "done":
                content.append("  ✓  ", style="green")
                content.append(f"{node_name}\n", style="green")
            elif node_state == "running":
                content.append(f"  {frame}  ", style="yellow")
                content.append(f"{node_name}\n", style="yellow")
                for line in self._logs:
                    content.append(f"      ↳ {line}\n", style="dim")
            else:
                content.append("  ◌  ", style="dim")
                content.append(f"{node_name}\n", style="dim")

        # Barra de progresso
        total = len(self._nodes)
        done_count = sum(1 for s in self._node_states if s == "done")
        if total > 0:
            bar_width = 30
            filled = int(bar_width * done_count / total)
            bar = "█" * filled + "░" * (bar_width - filled)
            content.append(f"\n  {bar}  {done_count}/{total}\n", style="dim")

        return Panel(
            content,
            title=title,
            title_align="left",
            subtitle=f"[dim]{elapsed_str}[/dim]",
            subtitle_align="right",
            border_style=border_style,
            padding=(0, 1),
        )


def _fmt_elapsed(seconds: float) -> str:
    """Formata segundos como MM:SS."""
    m = int(seconds // 60)
    s = int(seconds % 60)
    return f"{m:02d}:{s:02d}"
