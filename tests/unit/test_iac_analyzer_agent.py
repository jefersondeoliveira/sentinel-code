"""
Testes do IaC Analyzer Agent — fluxo completo do grafo LangGraph.

Testa o agente como um todo (integração entre nós),
sem mockar o LLM (o enriquecimento é opcional e pode ser skipado).

Rode com: pytest tests/unit/test_iac_analyzer_agent.py -v
"""

import pytest
from pathlib import Path


# =============================================================================
# FIXTURES — projetos IaC de exemplo em disco
# =============================================================================

@pytest.fixture
def terraform_project_with_gaps(tmp_path):
    """Projeto Terraform com vários problemas de infra."""
    (tmp_path / "main.tf").write_text("""
resource "aws_ecs_service" "api" {
  name            = "api"
  cluster         = "main"
  desired_count   = 1
}

resource "aws_db_instance" "main" {
  identifier     = "prod-db"
  instance_class = "db.t3.micro"
  multi_az       = false
  engine         = "postgres"
}

resource "aws_instance" "worker" {
  ami           = "ami-12345"
  instance_type = "t3.micro"
}
""")
    return str(tmp_path)


@pytest.fixture
def terraform_project_clean(tmp_path):
    """Projeto Terraform bem configurado — não deve gerar gaps."""
    (tmp_path / "main.tf").write_text("""
resource "aws_ecs_service" "api" {
  name          = "api"
  desired_count = 2
}

resource "aws_appautoscaling_target" "api" {
  service_namespace  = "ecs"
  scalable_dimension = "ecs:service:DesiredCount"
  resource_id        = "service/main/api"
  min_capacity       = 2
  max_capacity       = 10
}

resource "aws_db_instance" "main" {
  identifier     = "prod-db"
  instance_class = "db.m5.large"
  multi_az       = true
  engine         = "postgres"
}
""")
    return str(tmp_path)


@pytest.fixture
def k8s_project_without_hpa(tmp_path):
    """Projeto K8s sem HPA — deve gerar gap de autoscaling."""
    (tmp_path / "deployment.yaml").write_text("""
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
      - name: api
        image: api:latest
""")
    return str(tmp_path)


@pytest.fixture
def k8s_project_with_hpa(tmp_path):
    """Projeto K8s com HPA — não deve gerar gap de autoscaling."""
    (tmp_path / "deployment.yaml").write_text("""
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 2
""")
    (tmp_path / "hpa.yaml").write_text("""
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: api-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: api
  minReplicas: 2
  maxReplicas: 10
  targetCPUUtilizationPercentage: 70
""")
    return str(tmp_path)


@pytest.fixture
def nfr_high():
    return {"availability": "99.9%", "max_rps": 10000}


@pytest.fixture
def nfr_low():
    return {"availability": "99.0%", "max_rps": 500}


@pytest.fixture
def initial_state_iac(terraform_project_with_gaps, nfr_high):
    return {
        "project_path": terraform_project_with_gaps,
        "project_type": "terraform",
        "non_functional_requirements": nfr_high,
        "java_files": [],
        "issues": [],
        "iac_files": [],
        "infra_gaps": [],
        "applied_fixes": [],
        "final_report": None,
        "messages": [],
    }


# =============================================================================
# TESTES — pipeline do IaC Analyzer
# =============================================================================

class TestIaCAnalyzerPipeline:

    def test_finds_gaps_in_project_with_problems(self, initial_state_iac):
        from agents.iac_analyzer import build_iac_analyzer_graph
        graph  = build_iac_analyzer_graph()
        result = graph.invoke(initial_state_iac)
        assert len(result["infra_gaps"]) > 0

    def test_reads_iac_files(self, initial_state_iac):
        from agents.iac_analyzer import build_iac_analyzer_graph
        graph  = build_iac_analyzer_graph()
        result = graph.invoke(initial_state_iac)
        assert len(result["iac_files"]) > 0

    def test_no_gaps_in_clean_project(self, terraform_project_clean, nfr_high):
        from agents.iac_analyzer import build_iac_analyzer_graph
        state = {
            "project_path": terraform_project_clean,
            "project_type": "terraform",
            "non_functional_requirements": nfr_high,
            "java_files": [], "issues": [], "iac_files": [],
            "infra_gaps": [], "applied_fixes": [],
            "final_report": None, "messages": [],
        }
        graph  = build_iac_analyzer_graph()
        result = graph.invoke(state)
        assert len(result["infra_gaps"]) == 0

    def test_detects_missing_autoscaling_in_terraform(self, initial_state_iac):
        from agents.iac_analyzer import build_iac_analyzer_graph
        from models.infra_gap import InfraGapCategory
        graph  = build_iac_analyzer_graph()
        result = graph.invoke(initial_state_iac)
        categories = [g.category for g in result["infra_gaps"]]
        assert InfraGapCategory.MISSING_AUTOSCALING in categories

    def test_detects_single_az_in_terraform(self, initial_state_iac):
        from agents.iac_analyzer import build_iac_analyzer_graph
        from models.infra_gap import InfraGapCategory
        graph  = build_iac_analyzer_graph()
        result = graph.invoke(initial_state_iac)
        categories = [g.category for g in result["infra_gaps"]]
        assert InfraGapCategory.SINGLE_AZ in categories

    def test_detects_undersized_instance(self, initial_state_iac):
        from agents.iac_analyzer import build_iac_analyzer_graph
        from models.infra_gap import InfraGapCategory
        graph  = build_iac_analyzer_graph()
        result = graph.invoke(initial_state_iac)
        categories = [g.category for g in result["infra_gaps"]]
        assert InfraGapCategory.UNDERSIZED_INSTANCE in categories

    def test_messages_are_populated(self, initial_state_iac):
        from agents.iac_analyzer import build_iac_analyzer_graph
        graph  = build_iac_analyzer_graph()
        result = graph.invoke(initial_state_iac)
        assert len(result["messages"]) > 0

    def test_empty_project_does_not_raise(self, tmp_path, nfr_high):
        from agents.iac_analyzer import build_iac_analyzer_graph
        state = {
            "project_path": str(tmp_path),
            "project_type": "terraform",
            "non_functional_requirements": nfr_high,
            "java_files": [], "issues": [], "iac_files": [],
            "infra_gaps": [], "applied_fixes": [],
            "final_report": None, "messages": [],
        }
        graph  = build_iac_analyzer_graph()
        result = graph.invoke(state)
        assert result["infra_gaps"] == []


class TestIaCAnalyzerKubernetes:

    def test_detects_missing_hpa(self, k8s_project_without_hpa, nfr_high):
        from agents.iac_analyzer import build_iac_analyzer_graph
        from models.infra_gap import InfraGapCategory
        state = {
            "project_path": k8s_project_without_hpa,
            "project_type": "k8s",
            "non_functional_requirements": nfr_high,
            "java_files": [], "issues": [], "iac_files": [],
            "infra_gaps": [], "applied_fixes": [],
            "final_report": None, "messages": [],
        }
        graph  = build_iac_analyzer_graph()
        result = graph.invoke(state)
        categories = [g.category for g in result["infra_gaps"]]
        assert InfraGapCategory.MISSING_AUTOSCALING in categories

    def test_no_gap_when_hpa_present(self, k8s_project_with_hpa, nfr_high):
        from agents.iac_analyzer import build_iac_analyzer_graph
        from models.infra_gap import InfraGapCategory
        state = {
            "project_path": k8s_project_with_hpa,
            "project_type": "k8s",
            "non_functional_requirements": nfr_high,
            "java_files": [], "issues": [], "iac_files": [],
            "infra_gaps": [], "applied_fixes": [],
            "final_report": None, "messages": [],
        }
        graph  = build_iac_analyzer_graph()
        result = graph.invoke(state)
        categories = [g.category for g in result["infra_gaps"]]
        assert InfraGapCategory.MISSING_AUTOSCALING not in categories