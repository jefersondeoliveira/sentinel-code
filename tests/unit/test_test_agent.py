"""
Testes do Test Agent — escritos ANTES da implementação (Spec Driven).

Rode com: pytest tests/unit/test_test_agent.py -v
"""

import ast
import pytest
from pathlib import Path
from models.issue import Issue, Severity, IssueCategory


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def sample_issues():
    return [
        Issue(
            category=IssueCategory.N_PLUS_ONE,
            severity=Severity.CRITICAL,
            file_path="src/main/java/OrderService.java",
            line=10,
            evidence="itemRepository.findByOrder(order)",
            suggestion="Use JOIN FETCH",
            root_cause="N+1 detectado em processOrders() — query dentro de loop",
        ),
        Issue(
            category=IssueCategory.MISSING_CACHE,
            severity=Severity.HIGH,
            file_path="src/main/java/ProductService.java",
            line=16,
            evidence="@GetMapping(\"/products\")",
            suggestion="Adicione @Cacheable",
            root_cause="Cache ausente em getAllProducts()",
        ),
    ]


@pytest.fixture
def sample_fixes():
    return [
        {
            "category": "N+1 Query",
            "file":     "src/main/java/OrderService.java",
            "status":   "applied",
            "before":   "itemRepository.findByOrder(order)",
            "after":    "orderRepository.findAllWithItems()",
        },
        {
            "category": "Cache Ausente",
            "file":     "src/main/java/ProductService.java",
            "status":   "applied",
            "before":   "@GetMapping(\"/products\")",
            "after":    "@Cacheable(\"products\")\n@GetMapping(\"/products\")",
        },
    ]


@pytest.fixture
def nfr_with_sla():
    return {
        "target_url":     "http://localhost:8080",
        "p99_latency_ms": 200,
        "max_rps":        1000,
    }


@pytest.fixture
def nfr_no_sla():
    return {"target_url": "http://localhost:8080"}


@pytest.fixture
def nfr_no_url():
    return {"p99_latency_ms": 200, "max_rps": 1000}


@pytest.fixture
def sample_java_files():
    return [
        {
            "path":    "src/main/java/OrderService.java",
            "content": '''
@RestController
public class OrderService {
    @GetMapping("/orders")
    public List<Order> getAllOrders() { return orderRepo.findAll(); }

    @GetMapping("/orders/{id}")
    public Order getOrder(@PathVariable Long id) { return orderRepo.findById(id); }
}
''',
        },
        {
            "path":    "src/main/java/ProductService.java",
            "content": '''
@RestController
public class ProductService {
    @GetMapping("/products")
    public List<Product> getAllProducts() { return productRepo.findAll(); }
}
''',
        },
    ]


# =============================================================================
# TESTES — planner
# =============================================================================

class TestTestPlanner:

    def test_plan_generates_functional_test_for_each_endpoint(
        self, sample_java_files, sample_fixes, nfr_with_sla
    ):
        from tools.test_gen.planner import plan_tests
        plan = plan_tests(sample_java_files, sample_fixes, nfr_with_sla)
        functional = [p for p in plan if p["category"] == "functional"]
        assert len(functional) >= 1

    def test_plan_generates_regression_test_for_each_fix(
        self, sample_java_files, sample_fixes, nfr_with_sla
    ):
        from tools.test_gen.planner import plan_tests
        plan = plan_tests(sample_java_files, sample_fixes, nfr_with_sla)
        regression = [p for p in plan if p["category"] == "regression"]
        assert len(regression) == len(sample_fixes)

    def test_plan_no_regression_when_no_fixes(
        self, sample_java_files, nfr_with_sla
    ):
        from tools.test_gen.planner import plan_tests
        plan = plan_tests(sample_java_files, [], nfr_with_sla)
        regression = [p for p in plan if p["category"] == "regression"]
        assert len(regression) == 0

    def test_plan_generates_performance_test_when_sla_defined(
        self, sample_java_files, sample_fixes, nfr_with_sla
    ):
        from tools.test_gen.planner import plan_tests
        plan = plan_tests(sample_java_files, sample_fixes, nfr_with_sla)
        performance = [p for p in plan if p["category"] == "performance"]
        assert len(performance) >= 1

    def test_plan_no_performance_when_no_sla(
        self, sample_java_files, sample_fixes, nfr_no_sla
    ):
        from tools.test_gen.planner import plan_tests
        plan = plan_tests(sample_java_files, sample_fixes, nfr_no_sla)
        performance = [p for p in plan if p["category"] == "performance"]
        assert len(performance) == 0

    def test_plan_extracts_endpoints_from_java(
        self, sample_java_files, nfr_with_sla
    ):
        from tools.test_gen.planner import plan_tests, extract_endpoints
        endpoints = extract_endpoints(sample_java_files)
        assert "/orders" in endpoints
        assert "/products" in endpoints

    def test_plan_handles_path_variables(self, sample_java_files, nfr_with_sla):
        from tools.test_gen.planner import extract_endpoints
        endpoints = extract_endpoints(sample_java_files)
        # /orders/{id} deve ser incluído (com placeholder)
        path_var = [e for e in endpoints if "id" in e or "{" in e]
        assert len(path_var) >= 1

    def test_plan_empty_java_files_returns_empty(self, nfr_with_sla):
        from tools.test_gen.planner import plan_tests
        plan = plan_tests([], [], nfr_with_sla)
        assert plan == []


# =============================================================================
# TESTES — gerador de código
# =============================================================================

class TestCodeGenerator:

    def test_generated_test_has_valid_python_syntax(self, nfr_with_sla):
        from tools.test_gen.code_generator import generate_test_code
        plan_item = {
            "category": "functional",
            "endpoint": "/products",
            "method":   "GET",
            "context":  "Endpoint de listagem de produtos",
            "fix_info": None,
        }
        code = generate_test_code(plan_item, nfr_with_sla)
        # Valida sintaxe Python
        tree = ast.parse(code)
        assert tree is not None

    def test_generated_test_has_correct_endpoint(self, nfr_with_sla):
        from tools.test_gen.code_generator import generate_test_code
        plan_item = {
            "category": "functional",
            "endpoint": "/products",
            "method":   "GET",
            "context":  "Endpoint de listagem de produtos",
            "fix_info": None,
        }
        code = generate_test_code(plan_item, nfr_with_sla)
        assert "/products" in code

    def test_generated_regression_test_mentions_fix(self, nfr_with_sla):
        from tools.test_gen.code_generator import generate_test_code
        plan_item = {
            "category": "regression",
            "endpoint": "/orders",
            "method":   "GET",
            "context":  "Regressão: fix N+1 em processOrders()",
            "fix_info": {"category": "N+1 Query", "file": "OrderService.java"},
        }
        code = generate_test_code(plan_item, nfr_with_sla)
        assert "/orders" in code
        assert "def test_" in code

    def test_generated_performance_test_checks_latency(self, nfr_with_sla):
        from tools.test_gen.code_generator import generate_test_code
        plan_item = {
            "category": "performance",
            "endpoint": "/products",
            "method":   "GET",
            "context":  "Valida P99 de /products",
            "fix_info": None,
        }
        code = generate_test_code(plan_item, nfr_with_sla)
        assert "200" in code  # SLA de 200ms
        assert "def test_" in code

    def test_conftest_generated_with_base_url(self, nfr_with_sla):
        from tools.test_gen.code_generator import generate_conftest
        conftest = generate_conftest(nfr_with_sla)
        assert "base_url" in conftest
        assert "localhost:8080" in conftest
        assert "@pytest.fixture" in conftest

    def test_generated_test_imports_requests(self, nfr_with_sla):
        from tools.test_gen.code_generator import generate_test_code
        plan_item = {
            "category": "functional",
            "endpoint": "/products",
            "method":   "GET",
            "context":  "",
            "fix_info": None,
        }
        code = generate_test_code(plan_item, nfr_with_sla)
        assert "import requests" in code or "requests" in code


# =============================================================================
# TESTES — pipeline do Test Agent
# =============================================================================

class TestAgentPipeline:

    def _base_state(self, issues, fixes, nfr, java_files):
        return {
            "project_path":                "/tmp/test",
            "project_type":                "java-spring",
            "non_functional_requirements": nfr,
            "java_files":     java_files,
            "issues":         issues,
            "iac_files":      [],
            "infra_gaps":     [],
            "applied_fixes":  fixes,
            "final_report":   None,
            "messages":       [],
        }

    def test_pipeline_creates_generated_tests_in_state(
        self, sample_issues, sample_fixes, nfr_with_sla, sample_java_files
    ):
        from agents.test_agent import build_test_agent_graph
        state  = self._base_state(sample_issues, sample_fixes, nfr_with_sla, sample_java_files)
        graph  = build_test_agent_graph()
        result = graph.invoke(state)
        assert len(result.get("generated_tests", [])) > 0

    def test_pipeline_creates_files_on_disk(
        self, sample_issues, sample_fixes, nfr_with_sla, sample_java_files, tmp_path
    ):
        from agents.test_agent import build_test_agent_graph
        state = self._base_state(sample_issues, sample_fixes, nfr_with_sla, sample_java_files)
        state["project_path"] = str(tmp_path)
        graph  = build_test_agent_graph()
        result = graph.invoke(state)
        # Deve ter criado pelo menos 1 arquivo de teste
        test_files = list(tmp_path.rglob("test_*.py"))
        assert len(test_files) >= 1

    def test_pipeline_creates_conftest(
        self, sample_issues, sample_fixes, nfr_with_sla, sample_java_files, tmp_path
    ):
        from agents.test_agent import build_test_agent_graph
        state = self._base_state(sample_issues, sample_fixes, nfr_with_sla, sample_java_files)
        state["project_path"] = str(tmp_path)
        graph  = build_test_agent_graph()
        graph.invoke(state)
        conftest_files = list(tmp_path.rglob("conftest.py"))
        assert len(conftest_files) >= 1

    def test_pipeline_skips_execution_when_no_url(
        self, sample_issues, sample_fixes, nfr_no_url, sample_java_files
    ):
        from agents.test_agent import build_test_agent_graph
        state  = self._base_state(sample_issues, sample_fixes, nfr_no_url, sample_java_files)
        graph  = build_test_agent_graph()
        result = graph.invoke(state)
        # Pipeline não quebra sem URL
        assert result is not None

    def test_pipeline_handles_empty_issues_gracefully(
        self, nfr_with_sla, sample_java_files
    ):
        from agents.test_agent import build_test_agent_graph
        state  = self._base_state([], [], nfr_with_sla, sample_java_files)
        graph  = build_test_agent_graph()
        result = graph.invoke(state)
        assert result is not None

    def test_pipeline_handles_empty_java_files(self, nfr_with_sla):
        from agents.test_agent import build_test_agent_graph
        state = {
            "project_path":                "/tmp/test",
            "project_type":                "java-spring",
            "non_functional_requirements": nfr_with_sla,
            "java_files":    [],
            "issues":        [],
            "iac_files":     [],
            "infra_gaps":    [],
            "applied_fixes": [],
            "final_report":  None,
            "messages":      [],
        }
        graph  = build_test_agent_graph()
        result = graph.invoke(state)
        assert result["generated_tests"] == []