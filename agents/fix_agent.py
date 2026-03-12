"""
Fix Agent
──────────
Recebe os issues enriquecidos pelo Code Analyzer e aplica
as correções nos arquivos reais do projeto.

Fluxo:
  1. plan_fixes_node     → decide quais issues têm fix automático viável
  2. apply_fixes_node    → aplica correções cirúrgicas no arquivo
  3. validate_fixes_node → verifica que o patch não introduziu novos problemas
"""

from __future__ import annotations

from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

from config import settings
from models.state import AgentState
from models.issue import Issue, IssueCategory
from tools.java.code_patcher import apply_patch, apply_config_patch

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


# Categorias com fix automático implementado
FIXABLE_CATEGORIES = {
    IssueCategory.N_PLUS_ONE,
    IssueCategory.MISSING_CACHE,
    IssueCategory.CONNECTION_POOL,
}


# =============================================================================
# NÓS DO GRAFO
# =============================================================================

def plan_fixes_node(state: AgentState) -> dict:
    """
    Nó 1: separa issues fixáveis dos que precisam de intervenção manual.
    """
    if _ui:
        _ui.agent_start("FIX AGENT", ["plan_fixes", "apply_fixes", "validate_fixes"])
        _ui.node_start("plan_fixes")
    else:
        print("\n🗂️  [1/3] Planejando correções...")

    issues  = state.get("_enriched_issues") or state.get("issues", [])
    fixable = [i for i in issues if i.category in FIXABLE_CATEGORIES]
    manual  = [i for i in issues if i.category not in FIXABLE_CATEGORIES]

    for i in fixable:
        _log(f"✅ Fixável: {i.category.value}")
    for i in manual:
        _log(f"⚠️  Manual: {i.category.value}")

    _log(f"Total fixável: {len(fixable)} | Manual: {len(manual)}")

    if _ui:
        _ui.node_done("plan_fixes")

    return {
        "messages": [f"Planejamento: {len(fixable)} fixes automáticos, {len(manual)} manuais"],
    }


def apply_fixes_node(state: AgentState) -> dict:
    """
    Nó 2: aplica cada fix cirurgicamente no arquivo.

    Estratégia por categoria:
    - MISSING_CACHE    → insere @Cacheable diretamente (sem LLM)
    - CONNECTION_POOL  → cria/atualiza application.yml (sem LLM)
    - N_PLUS_ONE       → extrai snippet pela linha + pede LLM só o código corrigido
    """
    if _ui:
        _ui.node_start("apply_fixes")
    else:
        print("\n🛠️  [2/3] Aplicando correções...")

    all_issues     = state.get("_enriched_issues") or state.get("issues", [])
    fixable_issues = [i for i in all_issues if i.category in FIXABLE_CATEGORIES]
    project_path   = state["project_path"]

    if not fixable_issues:
        _log("⚠️  Nenhum issue fixável encontrado.")
        if _ui:
            _ui.node_done("apply_fixes")
        return {"applied_fixes": [], "messages": ["Nenhum fix aplicado."]}

    llm = ChatOpenAI(
        model=settings.openai_model,
        api_key=settings.openai_api_key,
        temperature=0,
    )

    file_index    = _build_file_index(project_path, fixable_issues)
    applied_fixes = []

    for i, issue in enumerate(fixable_issues):
        _log(f"[{i+1}/{len(fixable_issues)}] {issue.category.value} — {issue.file_path}")

        try:
            fix_record = _apply_single_fix(llm, issue, project_path, file_index)

            if fix_record["success"]:
                applied_fixes.append(fix_record)
                _log(f"✅ {fix_record['diff_summary']}")
                # Atualiza índice para o próximo fix no mesmo arquivo
                file_index[issue.file_path]                     = fix_record["after"]
                file_index[issue.file_path.replace("\\", "/")] = fix_record["after"]
            else:
                _log(f"❌ {fix_record['error']}")

        except Exception as e:
            _log(f"❌ Erro: {e}")

    _log(f"✅ {len(applied_fixes)}/{len(fixable_issues)} correção(ões) aplicada(s)")

    if _ui:
        _ui.node_done("apply_fixes")

    return {
        "applied_fixes": applied_fixes,
        "messages":      [f"{len(applied_fixes)} fixes aplicados com sucesso"],
    }


def validate_fixes_node(state: AgentState) -> dict:
    """
    Nó 3: valida que o patch não introduziu novos problemas estruturais.

    Estratégia: compara o balanço de chaves antes e depois.
    Se o balanço piorou (ficou mais negativo), o patch introduziu um problema.
    Se ficou igual ou melhorou, o fix é válido — mesmo em arquivos
    intencionalmente incompletos como os do sample_project.
    """
    if _ui:
        _ui.node_start("validate_fixes")
    else:
        print("\n✔️  [3/3] Validando correções...")

    applied_fixes = state.get("applied_fixes", [])
    project_path  = state["project_path"]
    validated     = []
    reverted      = []

    for fix in applied_fixes:
        fp = fix.get("file_path", "")

        # Config files não precisam de validação Java
        if fp.endswith(".yml") or fp.endswith(".properties"):
            validated.append(fix)
            _log(f"✅ Config válida: {fp}")
            continue

        before_balance = _brace_balance(fix.get("before", ""))
        after_balance  = _brace_balance(fix.get("after", ""))

        # O patch é válido se não piorou o balanço de chaves
        if after_balance >= before_balance:
            validated.append(fix)
            _log(f"✅ Java válido: {fp}")
        else:
            from tools.java.code_patcher import restore_backup
            rel_path = fp.replace(str(project_path), "").lstrip("/\\")
            restore_backup(project_path, rel_path)
            reverted.append(fix)
            _log(f"⚠️  Backup restaurado: {fp}")

    _log(f"Validados: {len(validated)} | Revertidos: {len(reverted)}")

    if _ui:
        _ui.node_done("validate_fixes")
        _ui.agent_done(f"{len(validated)} fix(es) validado(s)")

    return {
        "applied_fixes": validated,
        "messages":      [f"Validação: {len(validated)} OK, {len(reverted)} revertidos"],
    }


# =============================================================================
# CONSTRUÇÃO DO GRAFO
# =============================================================================

def build_fix_agent_graph() -> StateGraph:
    graph = StateGraph(AgentState)

    graph.add_node("plan_fixes",     plan_fixes_node)
    graph.add_node("apply_fixes",    apply_fixes_node)
    graph.add_node("validate_fixes", validate_fixes_node)

    graph.set_entry_point("plan_fixes")
    graph.add_edge("plan_fixes",     "apply_fixes")
    graph.add_edge("apply_fixes",    "validate_fixes")
    graph.add_edge("validate_fixes", END)

    return graph.compile()


# =============================================================================
# FIXES CIRÚRGICOS POR CATEGORIA
# =============================================================================

def _apply_single_fix(
    llm: ChatOpenAI,
    issue: Issue,
    project_path: str,
    file_index: dict,
) -> dict:
    """Despacha para o fix correto baseado na categoria do issue."""

    if issue.category == IssueCategory.CONNECTION_POOL:
        return _fix_connection_pool(issue, project_path)

    file_content = file_index.get(issue.file_path, "")
    if not file_content:
        return {
            "success": False,
            "error":   f"Arquivo não encontrado no índice: {issue.file_path}",
            "issue":   str(issue),
        }

    if issue.category == IssueCategory.MISSING_CACHE:
        return _fix_missing_cache(issue, project_path, file_content)

    # N+1 e outros: extrai snippet pela linha e usa LLM só para o código corrigido
    return _fix_with_llm(llm, issue, project_path, file_content)


def _fix_missing_cache(issue: Issue, project_path: str, file_content: str) -> dict:
    """
    Insere @Cacheable antes do @GetMapping detectado.
    Fix cirúrgico de uma linha — sem LLM, sem risco de desbalancear chaves.
    """
    lines  = file_content.splitlines()
    idx    = (issue.line or 1) - 1

    # Sobe para achar o @GetMapping exato
    target = idx
    for i in range(idx, max(0, idx - 5) - 1, -1):
        if "@GetMapping" in lines[i] or "@RequestMapping" in lines[i]:
            target = i
            break

    indent           = len(lines[target]) - len(lines[target].lstrip())
    cache_name       = _derive_cache_name(issue)
    cacheable_line   = " " * indent + f'@Cacheable(value = "{cache_name}")'
    original_snippet = lines[target]
    fixed_snippet    = cacheable_line + "\n" + lines[target]

    result = apply_patch(
        project_path=project_path,
        relative_file_path=issue.file_path,
        original_snippet=original_snippet,
        fixed_snippet=fixed_snippet,
    )

    return _build_fix_record(issue, result, original_snippet, fixed_snippet)


def _fix_connection_pool(issue: Issue, project_path: str) -> dict:
    """
    Adiciona configuração HikariCP no application.yml.
    Fix totalmente determinístico — sem LLM.
    """
    hikari_config = (
        "spring:\n"
        "  datasource:\n"
        "    hikari:\n"
        "      maximum-pool-size: 20\n"
        "      minimum-idle: 5\n"
        "      connection-timeout: 30000\n"
        "      idle-timeout: 600000\n"
        "      max-lifetime: 1800000\n"
    )

    result = apply_config_patch(
        project_path=project_path,
        config_content=hikari_config,
        filename="src/main/resources/application.yml",
    )

    return _build_fix_record(issue, result, "", hikari_config)


def _fix_with_llm(
    llm: ChatOpenAI,
    issue: Issue,
    project_path: str,
    file_content: str,
) -> dict:
    """
    Fix genérico via LLM: extrai o snippet pelo número de linha
    e pede ao LLM apenas o código corrigido.
    """
    original_snippet = _extract_snippet_from_file(file_content, issue.line, context=8)

    if not original_snippet:
        return {
            "success": False,
            "error":   "Não foi possível extrair o snippet pelo número de linha",
            "issue":   str(issue),
        }

    prompt        = _build_fix_only_prompt(issue, original_snippet)
    response      = llm.invoke([HumanMessage(content=prompt)])
    fixed_snippet = _parse_single_block(response.content)

    if not fixed_snippet:
        return {
            "success": False,
            "error":   "LLM não retornou o código corrigido no formato esperado",
            "issue":   str(issue),
        }

    result = apply_patch(
        project_path=project_path,
        relative_file_path=issue.file_path,
        original_snippet=original_snippet,
        fixed_snippet=fixed_snippet,
    )

    return _build_fix_record(issue, result, original_snippet, fixed_snippet)


# =============================================================================
# HELPERS
# =============================================================================

def _build_file_index(project_path: str, issues: list) -> dict:
    """Lê o conteúdo atual dos arquivos referenciados nos issues."""
    from pathlib import Path
    index = {}
    for issue in issues:
        normalized = issue.file_path.replace("\\", "/")
        file_path  = Path(project_path) / normalized
        if file_path.exists():
            content                                    = file_path.read_text(encoding="utf-8", errors="replace")
            index[issue.file_path]                     = content
            index[issue.file_path.replace("\\", "/")] = content
    return index


def _build_fix_record(issue: Issue, result, original_snippet: str, fixed_snippet: str) -> dict:
    """Monta o dict de registro de um fix aplicado."""
    return {
        "success":          result.success,
        "issue_category":   issue.category.value,
        "issue_severity":   issue.severity.value,
        "file_path":        result.file_path,
        "before":           result.before,
        "after":            result.after,
        "original_snippet": original_snippet,
        "fixed_snippet":    fixed_snippet,
        "diff_summary":     result.diff_summary,
        "error":            result.error,
    }


def _derive_cache_name(issue: Issue) -> str:
    """Deriva um nome de cache legível a partir da evidência do issue."""
    import re
    match = re.search(r'em:\s*(\w+)\(\)', issue.evidence or "")
    return match.group(1) if match else "perfagent-cache"


def _extract_snippet_from_file(
    content: str,
    line: int | None,
    context: int = 8,
) -> str | None:
    """
    Extrai um trecho do arquivo diretamente pelo número de linha.
    Sobe para encontrar o início do método e desce para fechar o bloco.
    Cópia exata do arquivo — sem nenhuma reescrita.
    """
    if not line:
        return None

    lines = content.splitlines()
    total = len(lines)
    idx   = line - 1  # 0-based

    # Sobe para encontrar início do método
    start = idx
    for i in range(idx, max(0, idx - context) - 1, -1):
        stripped = lines[i].strip()
        if stripped.startswith("@") or any(
            kw in stripped for kw in ["public ", "private ", "protected "]
        ):
            start = i
            break

    # Desce para fechar o bloco
    depth = 0
    end   = idx
    for i in range(start, min(total, idx + context + 10)):
        depth += lines[i].count("{") - lines[i].count("}")
        end    = i
        if depth > 0 and depth <= 0:
            break

    end     = max(end, min(idx + context, total - 1))
    snippet = "\n".join(lines[start:end + 1])
    return snippet if snippet.strip() else None


def _brace_balance(content: str) -> int:
    """
    Retorna o balanço de chaves do conteúdo (positivo = mais abre que fecha).
    Usado para comparar antes/depois do patch — se não piorou, o fix é válido.
    """
    balance = 0
    in_str  = False
    in_char = False

    for c in content:
        if c == '"' and not in_char:
            in_str = not in_str
        elif c == "'" and not in_str:
            in_char = not in_char
        elif not in_str and not in_char:
            if c == '{':
                balance += 1
            elif c == '}':
                balance -= 1

    return balance


def _build_fix_only_prompt(issue: Issue, original_snippet: str) -> str:
    """Pede ao LLM apenas o código corrigido para um snippet já identificado."""
    return f"""Você é um especialista em performance Java/Spring Boot.

Corrija APENAS o seguinte trecho de código, sem adicionar imports ou classes extras:

PROBLEMA: {issue.category.value}
CORREÇÃO: {issue.suggestion}

CÓDIGO ORIGINAL:
```java
{original_snippet}
```

Responda APENAS com o trecho corrigido, mantendo a mesma estrutura e indentação:

```java
[código corrigido]
```"""


def _parse_single_block(response: str) -> str | None:
    """Extrai um único bloco ```java ... ``` da resposta do LLM."""
    import re
    match = re.search(r'```(?:java)?\s*(.*?)```', response, re.DOTALL)
    return match.group(1).strip() if match else None