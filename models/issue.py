from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Severity(str, Enum):
    """
    Nível de severidade de um problema encontrado.
    Usamos str como base para serializar facilmente em JSON/logs.
    """
    CRITICAL = "CRÍTICO"    # Impacto direto em produção, corrigir imediatamente
    HIGH = "ALTO"           # Impacto significativo de performance ou escalabilidade
    MEDIUM = "MÉDIO"        # Melhoria importante, mas não urgente
    LOW = "BAIXO"           # Boas práticas, impacto menor


class IssueCategory(str, Enum):
    """
    Categoria do problema — permite filtrar e agrupar no relatório.
    """
    N_PLUS_ONE = "N+1 Query"
    MISSING_CACHE = "Cache Ausente"
    CONNECTION_POOL = "Connection Pool"
    MISSING_INDEX = "Índice Ausente"
    PAGINATION = "Paginação"
    LAZY_LOADING = "Lazy Loading"
    THREAD_BLOCKING = "Thread Bloqueante"
    GENERAL = "Geral"


@dataclass
class Issue:
    """
    Representa um problema de performance encontrado no código.

    Campos:
        category    : Tipo do problema (ex: N+1 Query)
        severity    : Quão urgente é corrigir (CRITICAL → LOW)
        file_path   : Caminho do arquivo onde foi encontrado
        line        : Linha aproximada (None se não aplicável)
        root_cause  : Explicação técnica da causa raiz
        evidence    : Trecho de código ou detalhe concreto que comprova o problema
        suggestion  : O que o Fix Agent deve fazer para corrigir
        fix_applied : Preenchido pelo Fix Agent após a correção
        before_code : Código original (antes da correção)
        after_code  : Código corrigido (após a correção)
    """
    category: IssueCategory
    severity: Severity
    file_path: str
    root_cause: str
    evidence: str
    suggestion: str
    line: Optional[int] = None
    fix_applied: bool = False
    before_code: Optional[str] = None
    after_code: Optional[str] = None

    def __str__(self) -> str:
        loc = f"{self.file_path}:{self.line}" if self.line else self.file_path
        return f"[{self.severity.value}] {self.category.value} — {loc}"