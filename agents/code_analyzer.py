"""
Code Analyzer Agent
────────────────────
Orquestra a análise de um projeto Java/Spring Boot em 3 etapas:

  1. read_files_node      → lê arquivos .java e configs
  2. detect_issues_node   → roda detectores estáticos (N+1, cache, pool)
  3. enrich_with_llm_node → LLM enriquece cada issue com análise real do código

Retorna o AgentState com `issues` preenchidos, prontos para o Fix Agent.
"""

from __future__ import annotations

from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

from config import settings
from models.state import AgentState
from models.issue import Issue
from tools.java.file_reader import read_java_files, read_application_properties
from tools.java.issue_detectors import (
    detect_n_plus_one,
    detect_missing_cache,
    detect_connection_pool,
    detect_pagination_issues,
    detect_lazy_loading,
    detect_thread_blocking,
    detect_missing_index,
)

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
# Cada nó é uma função pura: recebe o estado atual, retorna um dict
# com os campos que quer atualizar. O LangGraph faz o merge automático.
# =============================================================================

def read_files_node(state: AgentState) -> dict:
    """
    Nó 1: lê todos os arquivos do projeto.

    Por que é um nó separado?
    Separar I/O da análise facilita testar e trocar a fonte de dados
    no futuro (ex: ler de um ZIP, de um repositório Git remoto, etc.)
    """
    if _ui:
        _ui.agent_start("CODE ANALYZER", ["read_files", "detect_issues", "enrich_with_llm"])
        _ui.node_start("read_files")
    else:
        print("\n📂 [1/3] Lendo arquivos do projeto...")

    project_path = state["project_path"]

    java_files = read_java_files(project_path)
    app_configs = read_application_properties(project_path)

    _log(f"✅ {len(java_files)} arquivo(s) Java encontrado(s)")
    _log(f"✅ {len(app_configs)} arquivo(s) de config encontrado(s)")

    if _ui:
        _ui.node_done("read_files")

    return {
        "java_files": java_files,
        "messages": [f"Arquivos lidos: {len(java_files)} Java, {len(app_configs)} configs"],
        # Guarda configs no state para o detector de pool
        "non_functional_requirements": {
            **state.get("non_functional_requirements", {}),
            "_app_configs": app_configs,
        },
    }


def detect_issues_node(state: AgentState) -> dict:
    """
    Nó 2: roda os detectores estáticos e coleta todos os issues.

    Os detectores são rápidos (análise local, sem LLM).
    O LLM só entra no próximo nó para enriquecer, não para detectar.
    Isso mantém o custo baixo e o feedback rápido.
    """
    if _ui:
        _ui.node_start("detect_issues")
    else:
        print("\n🔍 [2/3] Executando detectores de performance...")

    java_files = state.get("java_files", [])
    app_configs = state["non_functional_requirements"].get("_app_configs", {})

    issues: list[Issue] = []

    # Roda cada detector e reporta quantos encontrou
    n1_issues = detect_n_plus_one(java_files)
    _log(f"N+1 Query:       {len(n1_issues)} issue(s)")
    issues.extend(n1_issues)

    cache_issues = detect_missing_cache(java_files)
    _log(f"Cache Ausente:   {len(cache_issues)} issue(s)")
    issues.extend(cache_issues)

    pool_issues = detect_connection_pool(app_configs)
    _log(f"Connection Pool: {len(pool_issues)} issue(s)")
    issues.extend(pool_issues)

    pagination_issues = detect_pagination_issues(java_files)
    _log(f"Paginação:       {len(pagination_issues)} issue(s)")
    issues.extend(pagination_issues)

    lazy_issues = detect_lazy_loading(java_files)
    _log(f"Lazy Loading:    {len(lazy_issues)} issue(s)")
    issues.extend(lazy_issues)

    blocking_issues = detect_thread_blocking(java_files)
    _log(f"Thread Blocking: {len(blocking_issues)} issue(s)")
    issues.extend(blocking_issues)

    index_issues = detect_missing_index(java_files)
    _log(f"Índice Ausente:  {len(index_issues)} issue(s)")
    issues.extend(index_issues)

    _log(f"Total: {len(issues)} issue(s) encontrado(s)")

    if _ui:
        _ui.node_done("detect_issues")

    return {
        "issues": issues,
        "messages": [f"Detecção concluída: {len(issues)} issues encontrados"],
    }


def enrich_with_llm_node(state: AgentState) -> dict:
    """
    Nó 3: usa o LLM para analisar o código real e enriquecer cada issue.

    O que o LLM faz aqui que os detectores não fazem:
    - Lê o código concreto ao redor do problema
    - Explica a causa raiz com contexto real (não genérico)
    - Sugere a correção exata para aquele trecho de código
    - Estima o impacto de performance em linguagem clara

    Para manter o custo controlado, enviamos apenas o trecho relevante
    do arquivo, não o arquivo inteiro.
    """
    if _ui:
        _ui.node_start("enrich_with_llm")
    else:
        print("\n🤖 [3/3] Enriquecendo issues com análise do LLM...")

    issues = state.get("issues", [])
    java_files = state.get("java_files", [])

    if not issues:
        _log("⚠️  Nenhum issue para enriquecer.")
        if _ui:
            _ui.node_done("enrich_with_llm")
            _ui.agent_done("Nenhum issue encontrado")
        return {"messages": ["Nenhum issue encontrado para enriquecer."]}

    llm = ChatOpenAI(
        model=settings.openai_model,
        api_key=settings.openai_api_key,
        temperature=0,  # 0 = respostas determinísticas, sem criatividade desnecessária
    )

    # Monta índice de arquivos para busca rápida por path
    file_index = {f["path"]: f["content"] for f in java_files}

    enriched_issues = []

    for i, issue in enumerate(issues):
        _log(f"Issue {i+1}/{len(issues)}: {issue.category.value}...")

        # Extrai o trecho relevante do arquivo (±15 linhas ao redor do problema)
        snippet = _extract_snippet(file_index, issue)

        prompt = _build_enrichment_prompt(issue, snippet)

        try:
            response = llm.invoke([HumanMessage(content=prompt)])
            enriched = _parse_llm_enrichment(response.content, issue)
            enriched_issues.append(enriched)
        except Exception as e:
            # Se o LLM falhar, mantém o issue original sem enriquecimento
            _log(f"⚠️  LLM falhou para issue {i+1}: {e}")
            enriched_issues.append(issue)

    _log(f"✅ {len(enriched_issues)} issue(s) enriquecido(s)")

    if _ui:
        _ui.node_done("enrich_with_llm")
        _ui.agent_done(f"{len(enriched_issues)} issue(s) enriquecido(s)")

    # Substitui a lista de issues pelo estado enriquecido
    # Usamos uma chave temporária porque issues é Annotated com operator.add
    # O merge do LangGraph adicionaria ao invés de substituir
    return {
        "messages": [f"Enriquecimento LLM concluído: {len(enriched_issues)} issues"],
        "_enriched_issues": enriched_issues,  # tratado abaixo no build_graph
    }


# =============================================================================
# CONSTRUÇÃO DO GRAFO
# =============================================================================

def build_code_analyzer_graph() -> StateGraph:
    """
    Monta o grafo LangGraph do Code Analyzer.

    Estrutura linear: read → detect → enrich → END
    Futuramente pode ter condicionais (ex: se não há Java files → pular detect)
    """
    graph = StateGraph(AgentState)

    # Adiciona os nós
    graph.add_node("read_files", read_files_node)
    graph.add_node("detect_issues", detect_issues_node)
    graph.add_node("enrich_with_llm", enrich_with_llm_node)

    # Define as arestas (fluxo de execução)
    graph.set_entry_point("read_files")
    graph.add_edge("read_files", "detect_issues")
    graph.add_edge("detect_issues", "enrich_with_llm")
    graph.add_edge("enrich_with_llm", END)

    return graph.compile()


# =============================================================================
# HELPERS PRIVADOS
# =============================================================================

def _extract_snippet(file_index: dict, issue: Issue, context_lines: int = 15) -> str:
    """
    Extrai um trecho do arquivo ao redor da linha do issue.
    Normaliza separadores de path para compatibilidade Windows/Linux.
    """
    # Normaliza o path para encontrar no índice
    normalized = issue.file_path.replace("\\", "/")
    content = None

    for key in file_index:
        if key.replace("\\", "/") == normalized:
            content = file_index[key]
            break

    if not content:
        return f"[Arquivo não encontrado: {issue.file_path}]"

    lines = content.splitlines()

    if issue.line:
        start = max(0, issue.line - context_lines - 1)
        end = min(len(lines), issue.line + context_lines)
        snippet_lines = lines[start:end]
        return "\n".join(f"{start+i+1}: {l}" for i, l in enumerate(snippet_lines))

    # Sem número de linha: retorna as primeiras 40 linhas
    return "\n".join(f"{i+1}: {l}" for i, l in enumerate(lines[:40]))


def _build_enrichment_prompt(issue: Issue, snippet: str) -> str:
    """
    Monta o prompt para enriquecer um issue com análise do LLM.
    """
    return f"""Você é um especialista em performance de aplicações Java/Spring Boot.

Analise o seguinte problema detectado automaticamente no código:

CATEGORIA: {issue.category.value}
SEVERIDADE: {issue.severity.value}
ARQUIVO: {issue.file_path}
CAUSA DETECTADA: {issue.root_cause}
EVIDÊNCIA: {issue.evidence}

TRECHO DO CÓDIGO:
```java
{snippet}
```

Responda em português com exatamente este formato (sem markdown extra):

CAUSA_RAIZ: [Explique em 1-2 frases a causa raiz real, referenciando o código acima]
IMPACTO: [Descreva o impacto concreto de performance em produção]
CORRECAO: [Descreva a correção exata para este trecho de código específico]
ANTES: [Cole o trecho problemático do código acima, exatamente como está]
DEPOIS: [Mostre como ficaria após a correção]"""


def _parse_llm_enrichment(response: str, original_issue: Issue) -> Issue:
    """
    Faz o parse da resposta do LLM e atualiza os campos do Issue.
    Se o parse falhar em algum campo, mantém o valor original.
    """
    import re
    import dataclasses

    def extract(key: str) -> str | None:
        pattern = rf"{key}:\s*(.+?)(?=\n[A-Z_]+:|$)"
        match = re.search(pattern, response, re.DOTALL)
        return match.group(1).strip() if match else None

    causa = extract("CAUSA_RAIZ")
    correcao = extract("CORRECAO")
    antes = extract("ANTES")
    depois = extract("DEPOIS")

    # dataclasses.replace cria uma cópia com campos atualizados
    return dataclasses.replace(
        original_issue,
        root_cause=causa or original_issue.root_cause,
        suggestion=correcao or original_issue.suggestion,
        before_code=antes or original_issue.before_code,
        after_code=depois or original_issue.after_code,
    )