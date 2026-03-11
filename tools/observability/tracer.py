"""
LangSmith Tracer
─────────────────
Configura e instrumenta o pipeline com observabilidade via LangSmith.

Uso em main.py:
    from tools.observability.tracer import setup_tracing, get_run_tags, get_run_metadata

    tracing_active = setup_tracing(settings)
    result = pipeline.invoke(
        initial_state,
        config={
            "run_name": f"sentinel-{project_name}-{timestamp}",
            "tags":     get_run_tags(initial_state, dry_run=dry_run, with_iac=with_iac),
            "metadata": get_run_metadata(initial_state),
        }
    )
"""

import os
from typing import Any


def setup_tracing(settings: Any) -> bool:
    """
    Configura as variáveis de ambiente do LangSmith.

    Retorna True se tracing foi habilitado, False caso contrário.

    Casos que retornam False:
    - LANGCHAIN_TRACING_V2=False
    - LANGCHAIN_API_KEY ausente ou vazio
    """
    tracing_enabled = getattr(settings, "langchain_tracing_v2", False)
    api_key         = getattr(settings, "langchain_api_key", None) or ""
    project         = getattr(settings, "langchain_project", "sentinel-code")

    if not tracing_enabled:
        return False

    if not api_key:
        print("    ⚠️  LangSmith: LANGCHAIN_API_KEY ausente — tracing desabilitado")
        return False

    # Seta variáveis de ambiente para o LangChain detectar automaticamente
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_API_KEY"]    = api_key
    os.environ["LANGCHAIN_PROJECT"]    = project

    endpoint = getattr(settings, "langchain_endpoint", "https://api.smith.langchain.com")
    if endpoint:
        os.environ["LANGCHAIN_ENDPOINT"] = endpoint

    return True


def is_tracing_enabled() -> bool:
    """Verifica se o tracing está ativo via variável de ambiente."""
    return os.environ.get("LANGCHAIN_TRACING_V2", "").lower() == "true"


def get_run_tags(
    state:          dict,
    dry_run:        bool = False,
    with_iac:       bool = False,
    with_benchmark: bool = False,
    with_tests:     bool = False,
) -> list:
    """
    Retorna tags para o run atual baseadas no estado e flags do pipeline.

    Tags geradas:
    - project_type (ex: "java-spring")
    - "dry_run:true" | "dry_run:false"
    - "iac:enabled" se with_iac=True
    - "benchmark:enabled" se with_benchmark=True
    - "tests:enabled" se with_tests=True
    - "has_issues:true" se há issues no state
    """
    tags = []

    # Tipo do projeto
    project_type = state.get("project_type", "unknown")
    tags.append(project_type)

    # Modo de execução
    tags.append("dry_run:true" if dry_run else "dry_run:false")

    # Flags de agentes
    if with_iac:
        tags.append("iac:enabled")
    if with_benchmark:
        tags.append("benchmark:enabled")
    if with_tests:
        tags.append("tests:enabled")

    # Estado atual
    if state.get("issues"):
        tags.append("has_issues:true")

    return tags


def get_run_metadata(state: dict) -> dict:
    """
    Retorna metadados estruturados para o run.

    Campos retornados:
    - project_path   : caminho do projeto
    - project_type   : tipo do projeto
    - issues_count   : número de issues detectados
    - fixes_count    : número de fixes aplicados
    - iac_gaps_count : número de gaps de IaC detectados
    """
    return {
        "project_path":   state.get("project_path", ""),
        "project_type":   state.get("project_type", ""),
        "issues_count":   len(state.get("issues", [])),
        "fixes_count":    len(state.get("applied_fixes", [])),
        "iac_gaps_count": len(state.get("infra_gaps", [])),
    }