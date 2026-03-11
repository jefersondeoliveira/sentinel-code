"""
IaC Analyzer Agent
───────────────────
Analisa arquivos de infraestrutura como código (Terraform, K8s)
contra requisitos não funcionais e identifica gaps.

Fluxo:
  1. read_iac_files_node      → lê e parseia .tf, .yaml, .yml
  2. detect_infra_gaps_node   → roda detectores estáticos
  3. enrich_iac_with_llm_node → LLM enriquece cada gap com contexto real
"""

from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

from config import settings
from models.state import AgentState
from tools.iac.file_reader import read_iac_files
from tools.iac.gap_detectors import (
    detect_missing_autoscaling,
    detect_single_az,
    detect_undersized_instance,
    detect_k8s_missing_resource_limits,
    detect_k8s_missing_probes,
)


# =============================================================================
# NÓS DO GRAFO
# =============================================================================

def read_iac_files_node(state: AgentState) -> dict:
    """Nó 1: lê todos os arquivos IaC do projeto."""
    print("\n📂 [1/3] Lendo arquivos IaC...")

    project_path = state["project_path"]

    try:
        iac_files = read_iac_files(project_path)
    except FileNotFoundError as e:
        print(f"    ❌ {e}")
        return {"iac_files": [], "messages": [str(e)]}

    tf_count  = sum(1 for f in iac_files if f["type"] == "terraform")
    k8s_count = sum(1 for f in iac_files if f["type"] == "kubernetes")

    print(f"    ✅ {tf_count} arquivo(s) Terraform | {k8s_count} arquivo(s) K8s")

    return {
        "iac_files": iac_files,
        "messages":  [f"IaC lido: {tf_count} Terraform, {k8s_count} K8s"],
    }


def detect_infra_gaps_node(state: AgentState) -> dict:
    """Nó 2: roda os detectores estáticos."""
    print("\n🔍 [2/3] Detectando gaps de infraestrutura...")

    iac_files = state.get("iac_files", [])
    nfr       = state.get("non_functional_requirements", {})

    if not iac_files:
        print("    ⚠️  Nenhum arquivo IaC encontrado.")
        return {"infra_gaps": [], "messages": ["Nenhum arquivo IaC para analisar."]}

    gaps = []

    autoscaling_gaps = detect_missing_autoscaling(iac_files, nfr)
    print(f"    Autoscaling Ausente:     {len(autoscaling_gaps)} gap(s)")
    gaps.extend(autoscaling_gaps)

    single_az_gaps = detect_single_az(iac_files, nfr)
    print(f"    Single AZ:               {len(single_az_gaps)} gap(s)")
    gaps.extend(single_az_gaps)

    undersized_gaps = detect_undersized_instance(iac_files, nfr)
    print(f"    Instância Subdimensionada: {len(undersized_gaps)} gap(s)")
    gaps.extend(undersized_gaps)

    k8s_resource_gaps = detect_k8s_missing_resource_limits(iac_files, nfr)
    print(f"    K8s Resource Limits:       {len(k8s_resource_gaps)} gap(s)")
    gaps.extend(k8s_resource_gaps)

    k8s_probe_gaps = detect_k8s_missing_probes(iac_files, nfr)
    print(f"    K8s Health Probes:         {len(k8s_probe_gaps)} gap(s)")
    gaps.extend(k8s_probe_gaps)

    print(f"    ─────────────────────────────")
    print(f"    Total: {len(gaps)} gap(s) encontrado(s)")

    return {
        "infra_gaps": gaps,
        "messages":   [f"Detecção IaC: {len(gaps)} gaps encontrados"],
    }


def enrich_iac_with_llm_node(state: AgentState) -> dict:
    """
    Nó 3: usa o LLM para enriquecer cada gap com análise do código real.
    """
    print("\n🤖 [3/3] Enriquecendo gaps com análise do LLM...")

    gaps      = state.get("infra_gaps", [])
    iac_files = state.get("iac_files", [])

    if not gaps:
        print("    ⚠️  Nenhum gap para enriquecer.")
        return {"messages": ["Nenhum gap IaC para enriquecer."]}

    llm = ChatOpenAI(
        model=settings.openai_model,
        api_key=settings.openai_api_key,
        temperature=0,
    )

    file_index = {f["path"]: f["content"] for f in iac_files}
    enriched   = []

    for i, gap in enumerate(gaps):
        print(f"    Analisando gap {i+1}/{len(gaps)}: {gap.category.value}...")

        snippet  = _extract_iac_snippet(file_index, gap)
        prompt   = _build_iac_enrichment_prompt(gap, snippet)

        try:
            response = llm.invoke([HumanMessage(content=prompt)])
            enriched.append(_parse_iac_enrichment(response.content, gap))
        except Exception as e:
            print(f"    ⚠️  LLM falhou: {e}")
            enriched.append(gap)

    print(f"\n    ✅ {len(enriched)} gap(s) enriquecido(s)")

    return {
        "_enriched_gaps": enriched,
        "messages": [f"Enriquecimento IaC concluído: {len(enriched)} gaps"],
    }


# =============================================================================
# CONSTRUÇÃO DO GRAFO
# =============================================================================

def build_iac_analyzer_graph() -> StateGraph:
    graph = StateGraph(AgentState)

    graph.add_node("read_iac_files",      read_iac_files_node)
    graph.add_node("detect_infra_gaps",   detect_infra_gaps_node)
    graph.add_node("enrich_iac_with_llm", enrich_iac_with_llm_node)

    graph.set_entry_point("read_iac_files")
    graph.add_edge("read_iac_files",      "detect_infra_gaps")
    graph.add_edge("detect_infra_gaps",   "enrich_iac_with_llm")
    graph.add_edge("enrich_iac_with_llm", END)

    return graph.compile()


# =============================================================================
# HELPERS
# =============================================================================

def _extract_iac_snippet(file_index: dict, gap) -> str:
    """Extrai o trecho relevante do arquivo IaC para o gap."""
    content = file_index.get(gap.file_path, "")
    if not content:
        return f"[Arquivo não encontrado: {gap.file_path}]"

    # Tenta encontrar o bloco do recurso
    resource_name = gap.resource.split(".")[-1] if "." in gap.resource else gap.resource
    lines = content.splitlines()

    start = 0
    for i, line in enumerate(lines):
        if resource_name in line:
            start = max(0, i - 1)
            break

    return "\n".join(lines[start:min(start + 20, len(lines))])


def _build_iac_enrichment_prompt(gap, snippet: str) -> str:
    return f"""Você é um especialista em infraestrutura cloud e IaC.

Analise o seguinte gap de infraestrutura:

CATEGORIA: {gap.category.value}
SEVERIDADE: {gap.severity.value}
RECURSO: {gap.resource}
CAUSA DETECTADA: {gap.root_cause}

TRECHO DO CÓDIGO IaC:
```
{snippet}
```

Responda em português com exatamente este formato:

CAUSA_RAIZ: [causa raiz específica para este recurso]
IMPACTO: [impacto concreto em produção]
CORRECAO: [bloco HCL/YAML exato para corrigir]"""


def _parse_iac_enrichment(response: str, original_gap):
    """Parseia a resposta do LLM e atualiza o gap."""
    import re
    import dataclasses

    def extract(key: str) -> str | None:
        match = re.search(rf"{key}:\s*(.+?)(?=\n[A-Z_]+:|$)", response, re.DOTALL)
        return match.group(1).strip() if match else None

    causa   = extract("CAUSA_RAIZ")
    correcao = extract("CORRECAO")

    return dataclasses.replace(
        original_gap,
        root_cause=causa    or original_gap.root_cause,
        after_code=correcao or original_gap.after_code,
    )