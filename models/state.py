from typing import TypedDict, List, Optional, Annotated
import operator
from models.issue import Issue


class AgentState(TypedDict):
    """
    Estado global compartilhado entre todos os agentes via LangGraph.

    O LangGraph passa este dict entre os nós do grafo.
    Cada agente lê o que precisa e escreve nos campos de sua responsabilidade.

    Campos marcados com Annotated[list, operator.add] são acumulativos:
    cada agente ADICIONA à lista, em vez de sobrescrever.
    Isso é importante: o Code Analyzer pode rodar em paralelo e
    cada instância adiciona seus issues sem apagar os dos outros.
    """

    # --- Input do usuário ---
    project_path: str
    """Caminho absoluto para a raiz do projeto a ser analisado."""

    project_type: str
    """Tipo: 'java-spring' | 'terraform' | 'k8s' | 'mixed'"""

    non_functional_requirements: dict
    """
    Requisitos não funcionais em formato livre.
    Exemplos:
        {"max_rps": 10000, "p99_latency_ms": 200, "availability": "99.9%"}
    """

    # --- Fase de análise ---
    java_files: Annotated[List[dict], operator.add]
    """
    Lista de arquivos Java lidos pelo file_reader.
    Cada item: {"path": str, "content": str, "lines": int}
    """

    issues: Annotated[List[Issue], operator.add]
    """
    Problemas encontrados pelo Code Analyzer.
    Acumulativo: múltiplos detectores adicionam à mesma lista.
    """

    # --- Fase de correção ---
    applied_fixes: Annotated[List[dict], operator.add]
    """
    Correções aplicadas pelo Fix Agent.
    Cada item: {"issue": Issue, "file": str, "before": str, "after": str}
    """

    # --- Relatório final ---
    final_report: Optional[str]
    """Relatório gerado pelo Reporter Agent (Markdown ou HTML)."""

    # --- Log interno ---
    messages: Annotated[List[str], operator.add]
    """Log de mensagens entre agentes para debug e auditoria."""