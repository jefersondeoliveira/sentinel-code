from typing import TypedDict, List, Optional, Annotated
import operator
from models.issue import Issue


class AgentState(TypedDict):
    """
    Estado global compartilhado entre todos os agentes via LangGraph.
    """

    # --- Input do usuário ---
    project_path: str
    project_type: str
    non_functional_requirements: dict

    # --- Fase Java ---
    java_files: Annotated[List[dict], operator.add]
    issues: Annotated[List[Issue], operator.add]

    # --- Fase IaC ---
    iac_files: Annotated[List[dict], operator.add]
    infra_gaps: Annotated[List, operator.add]   # List[InfraGap]

    # --- Fase de correção ---
    applied_fixes: Annotated[List[dict], operator.add]

    # --- Test Agent ---
    test_plan:       List[dict]
    generated_tests: Annotated[List[dict], operator.add]
    test_results:    Optional[dict]

    # --- Relatório final ---
    final_report: Optional[str]

    # --- Log interno ---
    messages: Annotated[List[str], operator.add]