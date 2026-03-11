"""
IaC Gap Detectors
──────────────────
Detectores estáticos de gaps de infraestrutura.

Cada detector:
  - Recebe lista de arquivos IaC parseados + NFRs
  - Retorna List[InfraGap]
  - NÃO usa LLM
  - NÃO lança exceções — retorna [] em caso de erro
  - É idempotente
"""

from typing import List
from models.infra_gap import InfraGap, InfraGapCategory
from models.issue import Severity


# Mapa de capacidade estimada de RPS por tipo de instância AWS
INSTANCE_RPS_CAPACITY = {
    "t3.nano":    200,
    "t3.micro":   500,
    "t3.small":   1_000,
    "t3.medium":  2_500,
    "t3.large":   5_000,
    "t3.xlarge":  10_000,
    "m5.large":   8_000,
    "m5.xlarge":  15_000,
    "m5.2xlarge": 30_000,
    "m5.4xlarge": 60_000,
    "c5.large":   10_000,
    "c5.xlarge":  20_000,
    "c5.2xlarge": 40_000,
    # RDS / instâncias db.*
    "db.t3.micro":   500,
    "db.t3.small":   1_000,
    "db.t3.medium":  2_500,
    "db.m5.large":   8_000,
    "db.m5.xlarge":  15_000,
}


# =============================================================================
# DETECTOR 1 — Autoscaling Ausente
# =============================================================================

def detect_missing_autoscaling(
    iac_files: List[dict],
    nfr: dict,
) -> List[InfraGap]:
    """
    Detecta recursos de compute sem política de autoscaling associada.

    Terraform: aws_ecs_service sem aws_appautoscaling_target
    Kubernetes: Deployment sem HorizontalPodAutoscaler
    """
    gaps = []

    tf_files = [f for f in iac_files if f["type"] == "terraform" and f["parsed"]]
    k8s_files = [f for f in iac_files if f["type"] == "kubernetes" and f["parsed"]]

    gaps.extend(_check_ecs_autoscaling(tf_files, nfr))
    gaps.extend(_check_k8s_hpa(k8s_files, nfr))

    return gaps


def _check_ecs_autoscaling(tf_files: List[dict], nfr: dict) -> List[InfraGap]:
    """Verifica se cada aws_ecs_service tem um aws_appautoscaling_target."""
    gaps = []

    # Coleta todos os recursos de todos os arquivos
    all_resources = _collect_all_resources(tf_files)

    ecs_services    = all_resources.get("aws_ecs_service", {})
    autoscaling     = all_resources.get("aws_appautoscaling_target", {})
    autoscaling_ecs = {
        name for name, cfg in autoscaling.items()
        if "ecs" in str(cfg.get("service_namespace", ""))
    }

    severity = _availability_severity(nfr, Severity.HIGH, Severity.MEDIUM)

    for service_name, config in ecs_services.items():
        if service_name not in autoscaling_ecs:
            # Encontra o arquivo que contém este serviço
            file_path = _find_resource_file(tf_files, "aws_ecs_service", service_name)

            gaps.append(InfraGap(
                category=InfraGapCategory.MISSING_AUTOSCALING,
                severity=severity,
                resource=f"aws_ecs_service.{service_name}",
                file_path=file_path,
                root_cause=(
                    f"O serviço ECS '{service_name}' não tem aws_appautoscaling_target "
                    "associado. Sem autoscaling, picos de tráfego causam degradação."
                ),
                evidence=f"aws_ecs_service.{service_name} sem aws_appautoscaling_target",
                suggestion=(
                    f"Adicione um aws_appautoscaling_target e aws_appautoscaling_policy "
                    f"para o serviço '{service_name}' com min_capacity=2 e max_capacity=10."
                ),
                current_config={"desired_count": config.get("desired_count", "não definido")},
                recommended_config={"min_capacity": 2, "max_capacity": 10, "target_cpu": 70},
            ))

    return gaps


def _check_k8s_hpa(k8s_files: List[dict], nfr: dict) -> List[InfraGap]:
    """Verifica se cada Deployment K8s tem um HorizontalPodAutoscaler."""
    gaps     = []
    severity = _availability_severity(nfr, Severity.HIGH, Severity.MEDIUM)

    # Coleta nomes de Deployments e HPAs
    deployments = {}
    hpa_targets = set()

    for f in k8s_files:
        parsed = f["parsed"]
        if not parsed:
            continue

        kind = parsed.get("kind", "")
        name = parsed.get("metadata", {}).get("name", "unknown")

        if kind == "Deployment":
            deployments[name] = f["path"]

        elif kind == "HorizontalPodAutoscaler":
            target = (
                parsed.get("spec", {})
                      .get("scaleTargetRef", {})
                      .get("name", "")
            )
            if target:
                hpa_targets.add(target)

    for deployment_name, file_path in deployments.items():
        if deployment_name not in hpa_targets:
            gaps.append(InfraGap(
                category=InfraGapCategory.MISSING_AUTOSCALING,
                severity=severity,
                resource=f"Deployment/{deployment_name}",
                file_path=file_path,
                root_cause=(
                    f"O Deployment '{deployment_name}' não tem HorizontalPodAutoscaler. "
                    "Sem HPA, o número de pods é fixo independente da carga."
                ),
                evidence=f"Deployment/{deployment_name} sem HorizontalPodAutoscaler",
                suggestion=(
                    f"Crie um HorizontalPodAutoscaler para '{deployment_name}' "
                    "com minReplicas=2, maxReplicas=10 e targetCPUUtilizationPercentage=70."
                ),
                current_config={"replicas": "fixo"},
                recommended_config={"minReplicas": 2, "maxReplicas": 10, "targetCPU": 70},
            ))

    return gaps


# =============================================================================
# DETECTOR 2 — Single AZ
# =============================================================================

def detect_single_az(
    iac_files: List[dict],
    nfr: dict,
) -> List[InfraGap]:
    """
    Detecta recursos sem configuração multi-AZ.
    RDS com multi_az=false ou ausente.
    """
    gaps        = []
    tf_files    = [f for f in iac_files if f["type"] == "terraform" and f["parsed"]]
    all_resources = _collect_all_resources(tf_files)

    # Severidade baseada no NFR de disponibilidade
    availability = nfr.get("availability", "99.0%")
    high_avail   = _parse_availability(availability) >= 99.9
    severity     = Severity.CRITICAL if high_avail else Severity.MEDIUM

    # Verifica aws_db_instance
    for name, config in all_resources.get("aws_db_instance", {}).items():
        multi_az  = config.get("multi_az", False)
        file_path = _find_resource_file(tf_files, "aws_db_instance", name)

        if not multi_az:
            gaps.append(InfraGap(
                category=InfraGapCategory.SINGLE_AZ,
                severity=severity,
                resource=f"aws_db_instance.{name}",
                file_path=file_path,
                root_cause=(
                    f"O banco de dados '{name}' está configurado com multi_az=false. "
                    "Falha na AZ primária causa downtime completo do banco."
                ),
                evidence=f"aws_db_instance.{name}: multi_az = false",
                suggestion=(
                    f"Altere multi_az = true no recurso '{name}'. "
                    "O custo dobra mas a disponibilidade aumenta para 99.95%."
                ),
                current_config={"multi_az": False},
                recommended_config={"multi_az": True},
            ))

    # Verifica aws_rds_cluster (Aurora)
    for name, config in all_resources.get("aws_rds_cluster", {}).items():
        az_count  = len(config.get("availability_zones", []))
        file_path = _find_resource_file(tf_files, "aws_rds_cluster", name)

        if az_count < 2:
            gaps.append(InfraGap(
                category=InfraGapCategory.SINGLE_AZ,
                severity=severity,
                resource=f"aws_rds_cluster.{name}",
                file_path=file_path,
                root_cause=(
                    f"O cluster Aurora '{name}' não tem múltiplas AZs configuradas."
                ),
                evidence=f"aws_rds_cluster.{name}: availability_zones não configurado",
                suggestion=(
                    'Adicione availability_zones = ["us-east-1a", "us-east-1b", "us-east-1c"]'
                ),
                current_config={"availability_zones": []},
                recommended_config={"availability_zones": ["us-east-1a", "us-east-1b"]},
            ))

    return gaps


# =============================================================================
# DETECTOR 3 — Instância Subdimensionada
# =============================================================================

def detect_undersized_instance(
    iac_files: List[dict],
    nfr: dict,
) -> List[InfraGap]:
    """
    Detecta instâncias cujo RPS estimado é menor que o NFR de max_rps.
    """
    gaps        = []
    max_rps     = nfr.get("max_rps", 1000)
    tf_files    = [f for f in iac_files if f["type"] == "terraform" and f["parsed"]]
    all_resources = _collect_all_resources(tf_files)

    resource_types = ["aws_instance", "aws_db_instance", "aws_elasticache_cluster"]

    for resource_type in resource_types:
        for name, config in all_resources.get(resource_type, {}).items():
            instance_type = config.get("instance_type") or config.get("node_type", "")
            if not instance_type:
                continue

            capacity  = INSTANCE_RPS_CAPACITY.get(instance_type, 999_999)
            file_path = _find_resource_file(tf_files, resource_type, name)

            if max_rps > capacity:
                gaps.append(InfraGap(
                    category=InfraGapCategory.UNDERSIZED_INSTANCE,
                    severity=Severity.CRITICAL,
                    resource=f"{resource_type}.{name}",
                    file_path=file_path,
                    root_cause=(
                        f"A instância '{instance_type}' suporta estimados ~{capacity} RPS, "
                        f"mas o NFR exige {max_rps} RPS."
                    ),
                    evidence=f"{resource_type}.{name}: instance_type = \"{instance_type}\"",
                    suggestion=(
                        f"Aumente o instance_type para suportar {max_rps} RPS. "
                        f"Referência: m5.xlarge (~15k RPS), m5.2xlarge (~30k RPS)."
                    ),
                    current_config={"instance_type": instance_type, "estimated_rps": capacity},
                    recommended_config={"estimated_needed_rps": max_rps},
                ))

    return gaps


# =============================================================================
# HELPERS PRIVADOS
# =============================================================================

def _collect_all_resources(tf_files: List[dict]) -> dict:
    """
    Agrega todos os recursos de todos os arquivos Terraform num único dict.
    Formato: {"aws_ecs_service": {"api": {...config...}}}

    Nota: python-hcl2 retorna "resource" como List[dict], não dict.
    Ex: [{"aws_ecs_service": {"api": {...}}}, {"aws_db_instance": {"main": {...}}}]
    """
    all_resources: dict = {}

    for f in tf_files:
        parsed = f.get("parsed") or {}
        resources = parsed.get("resource", [])

        # hcl2 retorna lista de dicts — normaliza para dict único
        if isinstance(resources, list):
            resource_blocks = resources
        elif isinstance(resources, dict):
            resource_blocks = [resources]
        else:
            continue

        for block in resource_blocks:
            if not isinstance(block, dict):
                continue
            for resource_type, instances in block.items():
                if resource_type not in all_resources:
                    all_resources[resource_type] = {}
                if isinstance(instances, dict):
                    all_resources[resource_type].update(instances)

    return all_resources


def _find_resource_file(
    tf_files: List[dict],
    resource_type: str,
    resource_name: str,
) -> str:
    """Encontra o arquivo que contém um recurso específico."""
    for f in tf_files:
        parsed = f.get("parsed") or {}
        resources = parsed.get("resource", {})
        if resource_type in resources and resource_name in resources[resource_type]:
            return f["path"]
    return "unknown.tf"


def _availability_severity(
    nfr: dict,
    high_severity: Severity,
    low_severity: Severity,
) -> Severity:
    """Retorna severidade baseada no NFR de disponibilidade."""
    availability = nfr.get("availability", "99.0%")
    return high_severity if _parse_availability(availability) >= 99.9 else low_severity


def _parse_availability(availability: str) -> float:
    """Converte string de disponibilidade para float. Ex: '99.9%' → 99.9"""
    try:
        return float(str(availability).replace("%", "").strip())
    except (ValueError, AttributeError):
        return 99.0