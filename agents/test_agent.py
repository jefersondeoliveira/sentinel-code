"""
Test Agent
───────────
Gera testes funcionais, de regressão e de performance para os
endpoints Java/Spring Boot identificados pelo Code Analyzer.

Fluxo:
  1. plan_tests_node      → analisa issues/fixes e monta plano
  2. generate_tests_node  → gera código dos testes e salva em disco
  3. run_tests_node       → executa via pytest (se URL disponível)
"""

from __future__ import annotations

from pathlib import Path
from langgraph.graph import StateGraph, END

from models.state import AgentState
from tools.test_gen.planner import plan_tests
from tools.test_gen.code_generator import generate_test_code, generate_conftest

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


# Diretório base para testes gerados (relativo ao project_path)
TESTS_OUTPUT_DIR = "tests/generated"


# =============================================================================
# NÓS DO GRAFO
# =============================================================================

def plan_tests_node(state: AgentState) -> dict:
    if _ui:
        _ui.agent_start("TEST AGENT", ["plan_tests", "generate_tests", "run_tests"])
        _ui.node_start("plan_tests")
    else:
        print("\n📋 [1/3] Planejando testes...")

    java_files = state.get("java_files", [])
    if not java_files:
        _log("⚠️  Nenhum arquivo Java — testes não gerados.")
        if _ui:
            _ui.node_done("plan_tests")
            _ui.agent_done("Sem arquivos Java")
        return {
            "generated_tests": [],
            "messages": ["Test Agent: sem arquivos Java para analisar."],
        }

    fixes = [f for f in state.get("applied_fixes", []) if f.get("status") == "applied"]
    nfr   = state.get("non_functional_requirements", {})
    plan  = plan_tests(java_files, fixes, nfr)

    functional  = sum(1 for p in plan if p["category"] == "functional")
    regression  = sum(1 for p in plan if p["category"] == "regression")
    performance = sum(1 for p in plan if p["category"] == "performance")

    _log(f"Funcionais: {functional} | Regressão: {regression} | Performance: {performance}")
    _log(f"Total: {len(plan)} teste(s) planejado(s)")

    if _ui:
        _ui.node_done("plan_tests")

    return {
        "test_plan": plan,   # era "_test_plan"
        "messages":  [f"Test Agent: {len(plan)} testes planejados"],
    }


def generate_tests_node(state: AgentState) -> dict:
    if _ui:
        _ui.node_start("generate_tests")
    else:
        print("\n✍️  [2/3] Gerando código dos testes...")

    plan         = state.get("test_plan", [])
    nfr          = state.get("non_functional_requirements", {})
    project_path = state.get("project_path", "/tmp")

    if not plan:
        _log("⚠️  Plano vazio — nenhum teste gerado.")
        if _ui:
            _ui.node_done("generate_tests")
        return {"generated_tests": [], "messages": ["Test Agent: plano vazio."]}

    output_dir = Path(project_path) / TESTS_OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    # Gera conftest.py
    conftest_path = output_dir / "conftest.py"
    conftest_path.write_text(generate_conftest(nfr), encoding="utf-8")
    _log("✅ conftest.py gerado")

    generated = []
    by_category = {}

    for item in plan:
        category = item["category"]
        endpoint = item["endpoint"]
        code     = generate_test_code(item, nfr)

        # Organiza por categoria
        cat_dir = output_dir / category
        cat_dir.mkdir(exist_ok=True)

        func_name = _endpoint_to_filename(endpoint)
        filename  = f"test_{func_name}_{category}.py"
        file_path = cat_dir / filename

        file_path.write_text(code, encoding="utf-8")

        test_entry = {
            "category":  category,
            "endpoint":  endpoint,
            "method":    item.get("method", "GET"),
            "file_path": str(file_path.relative_to(project_path)),
            "executed":  False,
            "passed":    False,
        }
        generated.append(test_entry)
        by_category[category] = by_category.get(category, 0) + 1
        _log(f"✅ [{category}] {filename}")

    _log(f"✅ {len(generated)} arquivo(s) gerado(s) em {TESTS_OUTPUT_DIR}/")

    if _ui:
        _ui.node_done("generate_tests")

    return {
        "generated_tests": generated,
        "messages":        [f"Test Agent: {len(generated)} testes gerados"],
    }


def run_tests_node(state: AgentState) -> dict:
    if _ui:
        _ui.node_start("run_tests")
    else:
        print("\n🧪 [3/3] Executando testes gerados...")

    nfr        = state.get("non_functional_requirements", {})
    target_url = nfr.get("target_url", "")

    if not target_url:
        _log("⚠️  target_url não informado — execução pulada.")
        if _ui:
            _ui.node_done("run_tests")
            _ui.agent_done("Execução pulada (sem target_url)")
        return {"messages": ["Test Agent: execução pulada (sem target_url)."]}

    generated    = state.get("generated_tests", [])
    project_path = state.get("project_path", "/tmp")
    tests_dir    = Path(project_path) / TESTS_OUTPUT_DIR

    if not generated or not tests_dir.exists():
        _log("⚠️  Nenhum teste para executar.")
        if _ui:
            _ui.node_done("run_tests")
            _ui.agent_done("Nenhum teste para executar")
        return {"messages": ["Test Agent: nenhum teste para executar."]}

    try:
        import subprocess
        _log("Executando pytest...")
        result = subprocess.run(
            ["python", "-m", "pytest", str(tests_dir), "-v", "--tb=short",
             f"--base-url={target_url}"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        passed = "passed" in result.stdout
        _log(f"{'✅' if passed else '❌'} pytest exit code: {result.returncode}")
        if _ui:
            _ui.node_done("run_tests")
            _ui.agent_done(f"pytest exit={result.returncode}")
        return {
            "test_results": {
                "exit_code": result.returncode,
                "output":    result.stdout[-2000:],  # últimas 2000 chars
                "passed":    result.returncode == 0,
            },
            "messages": [f"Test Agent: testes executados (exit={result.returncode})"],
        }
    except Exception as e:
        _log(f"⚠️  Execução falhou: {e}")
        if _ui:
            _ui.node_done("run_tests")
            _ui.agent_done(f"Execução falhou: {e}")
        return {"messages": [f"Test Agent: execução falhou — {e}"]}


# =============================================================================
# CONSTRUÇÃO DO GRAFO
# =============================================================================

def build_test_agent_graph() -> StateGraph:
    graph = StateGraph(AgentState)

    graph.add_node("plan_tests",     plan_tests_node)
    graph.add_node("generate_tests", generate_tests_node)
    graph.add_node("run_tests",      run_tests_node)

    graph.set_entry_point("plan_tests")
    graph.add_edge("plan_tests",     "generate_tests")
    graph.add_edge("generate_tests", "run_tests")
    graph.add_edge("run_tests",      END)

    return graph.compile()


# =============================================================================
# HELPERS
# =============================================================================

def _endpoint_to_filename(endpoint: str) -> str:
    """Converte endpoint em nome de arquivo."""
    name = endpoint.strip("/").replace("/", "_").replace("-", "_")
    name = name.replace("{", "").replace("}", "")
    name = "".join(c for c in name if c.isalnum() or c == "_")
    return name or "root"