from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from models.issue import Severity


class InfraGapCategory(str, Enum):
    MISSING_AUTOSCALING  = "Autoscaling Ausente"
    UNDERSIZED_INSTANCE  = "Instância Subdimensionada"
    SINGLE_AZ            = "Single AZ"
    MISSING_CDN          = "CDN Ausente"
    MISSING_CACHE_LAYER  = "Camada de Cache Ausente"
    CONNECTION_LIMIT     = "Limite de Conexões"
    MISSING_HEALTH_CHECK = "Health Check Ausente"
    OPEN_SECURITY_GROUP  = "Security Group Aberto"
    GENERAL              = "Geral"


@dataclass
class InfraGap:
    """
    Representa um gap de infraestrutura encontrado no código IaC.

    Campos:
        category          : Tipo do gap
        severity          : Quão urgente é corrigir
        resource          : Nome do recurso IaC (ex: aws_ecs_service.api)
        file_path         : Arquivo onde foi encontrado
        root_cause        : Explicação técnica da causa raiz
        evidence          : Trecho do código que evidencia o problema
        suggestion        : O que o IaC Patcher deve fazer
        current_config    : Configuração atual extraída do código
        recommended_config: Configuração recomendada
        line              : Linha aproximada no arquivo
        cost_impact       : Estimativa de impacto de custo (opcional)
        fix_applied       : Preenchido pelo IaC Patcher após correção
        before_code       : Bloco HCL/YAML original
        after_code        : Bloco HCL/YAML corrigido
    """
    category: InfraGapCategory
    severity: Severity
    resource: str
    file_path: str
    root_cause: str
    evidence: str
    suggestion: str
    current_config: dict = field(default_factory=dict)
    recommended_config: dict = field(default_factory=dict)
    line: Optional[int] = None
    cost_impact: Optional[str] = None
    fix_applied: bool = False
    before_code: Optional[str] = None
    after_code: Optional[str] = None

    def __str__(self) -> str:
        loc = f"{self.file_path}:{self.line}" if self.line else self.file_path
        return f"[{self.severity.value}] {self.category.value} — {self.resource} ({loc})"