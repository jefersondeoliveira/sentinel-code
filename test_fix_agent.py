# test_fix_agent.py
from agents.code_analyzer import build_code_analyzer_graph
from agents.fix_agent import build_fix_agent_graph

PROJECT_PATH = "./sample_project"

# Passo 1: roda o analyzer para obter os issues
print("=" * 50)
print("ETAPA 1 — Code Analyzer")
print("=" * 50)

analyzer = build_code_analyzer_graph()
analysis_result = analyzer.invoke({
    "project_path": PROJECT_PATH,
    "project_type": "java-spring",
    "non_functional_requirements": {},
    "java_files": [],
    "issues": [],
    "applied_fixes": [],
    "final_report": None,
    "messages": [],
})

# Passo 2: passa os issues para o Fix Agent
print("\n" + "=" * 50)
print("ETAPA 2 — Fix Agent")
print("=" * 50)

fix_input = {
    **analysis_result,
    "applied_fixes": [],  # reseta para o fix agent preencher
}

fixer = build_fix_agent_graph()
fix_result = fixer.invoke(fix_input)

# Resultado
print("\n" + "=" * 50)
print("RESULTADO DOS FIXES")
print("=" * 50)

for fix in fix_result.get("applied_fixes", []):
    print(f"\n[{fix['issue_severity']}] {fix['issue_category']}")
    print(f"Arquivo : {fix['file_path']}")
    print(f"Status  : {'✅ OK' if fix['success'] else '❌ FALHOU'}")
    print(f"Diff    : {fix['diff_summary']}")
    if fix.get("original_snippet"):
        print(f"\n--- ANTES ---")
        print(fix["original_snippet"][:300])
        print(f"\n+++ DEPOIS +++")
        print(fix["fixed_snippet"][:300])