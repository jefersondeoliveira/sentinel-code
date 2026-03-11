"""
Gerador de scripts Locust a partir dos endpoints detectados.
"""

from typing import List


def generate_locust_script(endpoints: List[str], nfr: dict) -> str:
    """
    Gera um script Locust baseado nos endpoints e NFRs.

    Regras:
    - Endpoints de listagem (sem parâmetro) têm peso 3
    - Endpoints de detalhe (com ID) têm peso 1
    - wait_time derivado do max_rps
    - Se endpoints vazio → task padrão GET /
    """
    target_url  = nfr.get("target_url", "http://localhost:8080")
    max_rps     = nfr.get("max_rps", 100)
    users       = nfr.get("users", 10)

    # wait_time entre requisições
    min_wait = round(1 / max(max_rps, 1), 3)
    max_wait = round(min_wait * 2, 3)

    # Se sem endpoints, usa padrão
    if not endpoints:
        endpoints = ["/"]

    tasks = _build_tasks(endpoints)

    return f"""\
from locust import HttpUser, task, between

# Gerado automaticamente pelo SentinelCode Benchmark Agent
# target_url: {target_url}
# max_rps: {max_rps} | users: {users}


class SentinelLoadTest(HttpUser):
    host = "{target_url}"
    wait_time = between({min_wait}, {max_wait})

{tasks}
"""


def _build_tasks(endpoints: List[str]) -> str:
    lines = []
    for i, endpoint in enumerate(endpoints):
        # Endpoints com ID na URL têm peso menor
        weight = 1 if _has_id(endpoint) else 3
        method_name = _to_method_name(endpoint, i)
        lines.append(f"    @task({weight})")
        lines.append(f"    def {method_name}(self):")
        lines.append(f'        self.client.get("{endpoint}")')
        lines.append("")
    return "\n".join(lines)


def _has_id(endpoint: str) -> bool:
    """Verifica se o endpoint tem parâmetro de ID."""
    parts = endpoint.strip("/").split("/")
    return any(p.isdigit() or p.startswith("{") or p.startswith(":") for p in parts)


def _to_method_name(endpoint: str, idx: int) -> str:
    """Converte endpoint em nome de método Python válido."""
    name = endpoint.strip("/").replace("/", "_").replace("-", "_").replace("{", "").replace("}", "")
    name = "".join(c for c in name if c.isalnum() or c == "_")
    return f"endpoint_{name}" if name else f"endpoint_{idx}"