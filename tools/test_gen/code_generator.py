"""
Test Code Generator
────────────────────
Gera código Python de testes a partir de plan_items.
Não usa LLM — templates determinísticos por categoria.
"""

from typing import Optional


def generate_test_code(plan_item: dict, nfr: dict) -> str:
    """
    Gera código Python de teste para um plan_item.

    Estratégia:
    - functional  → template básico de status 200
    - regression  → template com validação de tempo + status
    - performance → template com loop P99
    - contract    → template de schema
    """
    category = plan_item.get("category", "functional")
    endpoint = plan_item.get("endpoint", "/")
    method   = plan_item.get("method", "GET").lower()
    context  = plan_item.get("context", "")
    fix_info = plan_item.get("fix_info")

    if category == "functional":
        return _functional_template(endpoint, method, context)
    elif category == "regression":
        return _regression_template(endpoint, method, context, fix_info)
    elif category == "performance":
        return _performance_template(endpoint, method, nfr)
    elif category == "contract":
        return _contract_template(endpoint, method, context)
    else:
        return _functional_template(endpoint, method, context)


def generate_conftest(nfr: dict) -> str:
    """Gera o conftest.py com a fixture base_url."""
    target_url = nfr.get("target_url", "http://localhost:8080")
    return f"""\
import pytest
import requests


@pytest.fixture(scope="session")
def base_url():
    \"\"\"URL base da aplicação. Configurar via NFR target_url.\"\"\"
    return "{target_url}"


@pytest.fixture(scope="session")
def http_session():
    session = requests.Session()
    yield session
    session.close()
"""


# =============================================================================
# TEMPLATES
# =============================================================================

def _functional_template(endpoint: str, method: str, context: str) -> str:
    func_name = _to_func_name(endpoint, method)
    endpoint_with_example = _replace_path_vars(endpoint)

    return f"""\
import requests


def test_{func_name}_returns_200(base_url):
    \"\"\"
    Funcional: {method.upper()} {endpoint}
    {context}
    \"\"\"
    response = requests.{method}(f"{{base_url}}{endpoint_with_example}")
    assert response.status_code == 200


def test_{func_name}_returns_valid_response(base_url):
    \"\"\"Valida que a resposta tem conteúdo.\"\"\"
    response = requests.{method}(f"{{base_url}}{endpoint_with_example}")
    assert response.status_code in (200, 201, 204)
    if response.status_code == 200:
        assert response.content is not None
"""


def _regression_template(
    endpoint: str,
    method: str,
    context: str,
    fix_info: Optional[dict],
) -> str:
    func_name  = _to_func_name(endpoint, method)
    fix_cat    = fix_info.get("category", "fix") if fix_info else "fix"
    fix_file   = fix_info.get("file", "") if fix_info else ""
    endpoint_with_example = _replace_path_vars(endpoint)

    return f"""\
import time
import requests


def test_{func_name}_regression_{_slugify(fix_cat)}(base_url):
    \"\"\"
    Regressão: {context}
    Fix aplicado: {fix_cat} em {fix_file}
    Valida que o endpoint responde corretamente após a correção.
    \"\"\"
    start    = time.time()
    response = requests.{method}(f"{{base_url}}{endpoint_with_example}")
    elapsed  = (time.time() - start) * 1000

    assert response.status_code == 200, (
        f"Endpoint retornou {{response.status_code}} após fix de {fix_cat}"
    )
    assert elapsed < 2000, (
        f"Tempo excessivo: {{elapsed:.0f}}ms — possível regressão após fix"
    )
"""


def _performance_template(endpoint: str, method: str, nfr: dict) -> str:
    func_name       = _to_func_name(endpoint, method)
    p99_sla         = nfr.get("p99_latency_ms", 500)
    iterations      = 50
    endpoint_with_example = _replace_path_vars(endpoint)

    return f"""\
import time
import requests


def test_{func_name}_p99_within_sla(base_url):
    \"\"\"
    Performance: valida que P99 de {method.upper()} {endpoint} <= {p99_sla}ms
    \"\"\"
    times = []
    for _ in range({iterations}):
        start = time.time()
        requests.{method}(f"{{base_url}}{endpoint_with_example}")
        times.append((time.time() - start) * 1000)

    times.sort()
    p99_idx = int(len(times) * 0.99)
    p99     = times[min(p99_idx, len(times) - 1)]

    assert p99 <= {p99_sla}, (
        f"P99={{p99:.0f}}ms excede SLA de {p99_sla}ms em {endpoint}"
    )
"""


def _contract_template(endpoint: str, method: str, context: str) -> str:
    func_name = _to_func_name(endpoint, method)
    endpoint_with_example = _replace_path_vars(endpoint)

    return f"""\
import requests


def test_{func_name}_contract(base_url):
    \"\"\"
    Contrato: {method.upper()} {endpoint}
    {context}
    \"\"\"
    response = requests.{method}(f"{{base_url}}{endpoint_with_example}")
    assert response.status_code == 200

    data = response.json()
    if isinstance(data, list):
        assert len(data) >= 0
        if data:
            item = data[0]
            assert isinstance(item, dict)
            assert "id" in item or len(item) > 0
    elif isinstance(data, dict):
        assert len(data) > 0
"""


# =============================================================================
# HELPERS
# =============================================================================

def _to_func_name(endpoint: str, method: str) -> str:
    """Converte endpoint em nome de função Python."""
    name = endpoint.strip("/").replace("/", "_").replace("-", "_")
    name = name.replace("{", "").replace("}", "")
    name = "".join(c for c in name if c.isalnum() or c == "_")
    return f"{method.lower()}_{name}" if name else method.lower()


def _replace_path_vars(endpoint: str) -> str:
    """Substitui variáveis de path por valores de exemplo."""
    import re
    return re.sub(r"\{[^}]+\}", "1", endpoint)


def _slugify(text: str) -> str:
    """Converte texto em slug para nome de função."""
    return text.lower().replace(" ", "_").replace("+", "plus").replace("-", "_")