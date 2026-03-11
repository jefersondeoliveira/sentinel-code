"""
Test Planner
─────────────
Analisa arquivos Java e fixes aplicados para montar um plano de testes.

Retorna lista de plan_items:
  {
    "category": "functional" | "regression" | "performance",
    "endpoint": "/products",
    "method":   "GET",
    "context":  "descrição do que testar",
    "fix_info": dict | None,
  }
"""

import re
from typing import List, Optional


def plan_tests(
    java_files: List[dict],
    applied_fixes: List[dict],
    nfr: dict,
) -> List[dict]:
    """
    Monta o plano de testes a partir dos arquivos Java e fixes.
    """
    if not java_files:
        return []

    endpoints = extract_endpoints(java_files)
    plan      = []

    # Testes funcionais — um por endpoint
    for endpoint, method in endpoints.items():
        plan.append({
            "category": "functional",
            "endpoint": endpoint,
            "method":   method,
            "context":  f"Teste funcional de {method} {endpoint}",
            "fix_info": None,
        })

    # Testes de regressão — um por fix aplicado
    for fix in applied_fixes:
        if fix.get("status") != "applied":
            continue
        endpoint = _infer_endpoint_from_fix(fix, endpoints)
        plan.append({
            "category": "regression",
            "endpoint": endpoint,
            "method":   "GET",
            "context":  f"Regressão: fix {fix.get('category', 'desconhecido')} em {fix.get('file', '')}",
            "fix_info": fix,
        })

    # Testes de performance — só se NFR tem SLA de latência ou RPS
    has_perf_sla = "p99_latency_ms" in nfr or "max_rps" in nfr
    if has_perf_sla:
        for endpoint, method in list(endpoints.items())[:3]:  # max 3 endpoints
            if method == "GET":
                plan.append({
                    "category": "performance",
                    "endpoint": endpoint,
                    "method":   "GET",
                    "context":  f"Valida SLA de {endpoint}",
                    "fix_info": None,
                })
                break  # um teste de performance por execução

    return plan


def extract_endpoints(java_files: List[dict]) -> dict:
    """
    Extrai endpoints dos arquivos Java.
    Retorna dict: {"/endpoint": "GET"}
    """
    endpoints = {}

    mapping_pattern = re.compile(
        r'@(Get|Post|Put|Delete|Patch)Mapping\s*\(\s*["\']([^"\']+)["\']'
    )
    value_pattern = re.compile(
        r'@(Get|Post|Put|Delete|Patch)Mapping\s*\(\s*value\s*=\s*["\']([^"\']+)["\']'
    )

    method_map = {
        "Get":    "GET",
        "Post":   "POST",
        "Put":    "PUT",
        "Delete": "DELETE",
        "Patch":  "PATCH",
    }

    for f in java_files:
        content = f.get("content", "")

        for pattern in [mapping_pattern, value_pattern]:
            for match in pattern.finditer(content):
                http_method = method_map.get(match.group(1), "GET")
                endpoint    = match.group(2)
                if not endpoint.startswith("/"):
                    endpoint = "/" + endpoint
                endpoints[endpoint] = http_method

    return endpoints


def _infer_endpoint_from_fix(fix: dict, endpoints: dict) -> str:
    """Tenta inferir o endpoint associado ao fix pelo nome do arquivo."""
    fix_file = fix.get("file", "").lower()

    for endpoint in endpoints:
        # Heurística: /products → ProductService, /orders → OrderService
        endpoint_name = endpoint.strip("/").split("/")[0].lower()
        if endpoint_name in fix_file:
            return endpoint

    # Fallback: primeiro endpoint GET disponível
    for endpoint, method in endpoints.items():
        if method == "GET":
            return endpoint

    return "/api"