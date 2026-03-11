"""
IaC Patcher
────────────
Aplica correções cirúrgicas em arquivos Terraform e K8s.

Estratégias:
  append_block    — adiciona novo bloco HCL ao final do arquivo
  modify_attribute — altera valor de atributo existente
  append_file     — cria novo arquivo no mesmo diretório (ex: HPA K8s)
"""

import shutil
from pathlib import Path
from typing import Optional

from models.infra_gap import InfraGap, InfraGapCategory


# =============================================================================
# ENTRY POINT
# =============================================================================

def apply_iac_patch(gap: InfraGap, project_path: str) -> dict:
    """
    Aplica o patch para um InfraGap.

    Retorna dict com:
      category, resource, file, strategy, before, after, status, reason
    """
    base = {
        "category": gap.category.value,
        "resource": gap.resource,
        "file":     gap.file_path,
        "before":   "",
        "after":    "",
        "strategy": "unknown",
        "status":   "skipped",
        "reason":   "",
    }

    strategy = _resolve_strategy(gap)
    base["strategy"] = strategy

    if strategy == "unknown":
        base["reason"] = f"Sem estratégia automática para {gap.category.value}"
        return base

    try:
        if strategy == "append_block":
            return _patch_append_block(gap, project_path, base)
        elif strategy == "modify_attribute":
            return _patch_modify_attribute(gap, project_path, base)
        elif strategy == "append_file":
            return _patch_append_file(gap, project_path, base)
    except Exception as e:
        base["status"] = "failed"
        base["reason"] = str(e)
        return base

    return base


# =============================================================================
# ESTRATÉGIAS
# =============================================================================

def _patch_append_block(gap: InfraGap, project_path: str, result: dict) -> dict:
    """Adiciona novo bloco HCL ao final do arquivo existente."""
    file_path = Path(project_path) / gap.file_path

    if not file_path.exists():
        result["status"] = "failed"
        result["reason"] = f"Arquivo não encontrado: {gap.file_path}"
        return result

    original = file_path.read_text(encoding="utf-8")

    # Idempotência — verifica se o bloco já existe
    new_block = _generate_append_block(gap)
    if not new_block:
        result["status"] = "skipped"
        result["reason"] = "Bloco não gerado — categoria sem template"
        return result

    idempotency_key = _idempotency_key(gap)
    if idempotency_key and idempotency_key in original:
        result["status"] = "skipped"
        result["reason"] = "Bloco já existe no arquivo"
        return result

    # Backup → patch → valida → limpa backup
    backup = _create_backup(file_path)
    patched = original.rstrip() + "\n\n" + new_block + "\n"

    file_path.write_text(patched, encoding="utf-8")

    if not _validate_tf(patched):
        _restore_backup(backup, file_path)
        result["status"] = "failed"
        result["reason"] = "HCL inválido após patch — revertido"
        return result

    backup.unlink(missing_ok=True)
    result["before"] = original
    result["after"]  = patched
    result["status"] = "applied"
    return result


def _patch_modify_attribute(gap: InfraGap, project_path: str, result: dict) -> dict:
    """Altera o valor de um atributo existente no bloco HCL."""
    file_path = Path(project_path) / gap.file_path

    if not file_path.exists():
        result["status"] = "failed"
        result["reason"] = f"Arquivo não encontrado: {gap.file_path}"
        return result

    original = file_path.read_text(encoding="utf-8")
    patches  = _generate_attribute_patches(gap)

    if not patches:
        result["status"] = "skipped"
        result["reason"] = "Sem atributos para modificar"
        return result

    # Idempotência
    patched = original
    any_changed = False
    for old_val, new_val in patches:
        if old_val in patched:
            patched = patched.replace(old_val, new_val, 1)
            any_changed = True

    if not any_changed:
        result["status"] = "skipped"
        result["reason"] = "Atributo já está com valor correto"
        return result

    backup = _create_backup(file_path)
    file_path.write_text(patched, encoding="utf-8")

    if not _validate_tf(patched):
        _restore_backup(backup, file_path)
        result["status"] = "failed"
        result["reason"] = "HCL inválido após patch — revertido"
        return result

    backup.unlink(missing_ok=True)
    result["before"] = original
    result["after"]  = patched
    result["status"] = "applied"
    return result


def _patch_append_file(gap: InfraGap, project_path: str, result: dict) -> dict:
    """Cria novo arquivo no mesmo diretório (ex: HPA K8s)."""
    source_path = Path(project_path) / gap.file_path
    target_dir  = source_path.parent

    new_content  = _generate_new_file_content(gap)
    new_filename = _generate_new_filename(gap, target_dir)

    if not new_content or not new_filename:
        result["status"] = "skipped"
        result["reason"] = "Conteúdo não gerado para este gap"
        return result

    new_file = target_dir / new_filename

    # Idempotência — arquivo já existe com conteúdo similar
    if new_file.exists():
        result["status"] = "skipped"
        result["reason"] = f"Arquivo {new_filename} já existe"
        return result

    new_file.write_text(new_content, encoding="utf-8")

    if not _validate_yaml(new_content):
        new_file.unlink(missing_ok=True)
        result["status"] = "failed"
        result["reason"] = "YAML inválido — arquivo removido"
        return result

    result["before"] = ""
    result["after"]  = new_content
    result["file"]   = str(new_file.relative_to(project_path))
    result["status"] = "applied"
    return result


# =============================================================================
# GERADORES DE CONTEÚDO
# =============================================================================

def _generate_append_block(gap: InfraGap) -> Optional[str]:
    """Gera o bloco HCL a ser adicionado."""
    resource_name = gap.resource.split(".")[-1]

    if gap.category == InfraGapCategory.MISSING_AUTOSCALING:
        if gap.resource.startswith("aws_ecs_service"):
            return _ecs_autoscaling_block(resource_name)

    return None


def _ecs_autoscaling_block(service_name: str) -> str:
    return f"""\
resource "aws_appautoscaling_target" "{service_name}" {{
  service_namespace  = "ecs"
  scalable_dimension = "ecs:service:DesiredCount"
  resource_id        = "service/${{var.cluster_name}}/{service_name}"
  min_capacity       = 2
  max_capacity       = 10
}}

resource "aws_appautoscaling_policy" "{service_name}_cpu" {{
  name               = "{service_name}-cpu-scaling"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.{service_name}.resource_id
  scalable_dimension = aws_appautoscaling_target.{service_name}.scalable_dimension
  service_namespace  = aws_appautoscaling_target.{service_name}.service_namespace

  target_tracking_scaling_policy_configuration {{
    target_value = 70.0
    predefined_metric_specification {{
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }}
  }}
}}"""


def _generate_attribute_patches(gap: InfraGap) -> list[tuple[str, str]]:
    """Retorna lista de (valor_antigo, valor_novo) para substituição."""
    if gap.category == InfraGapCategory.SINGLE_AZ:
        return [
            ("multi_az       = false", "multi_az       = true"),
            ("multi_az = false",       "multi_az = true"),
            ("multi_az=false",         "multi_az=true"),
        ]
    return []


def _generate_new_file_content(gap: InfraGap) -> Optional[str]:
    """Gera conteúdo para novo arquivo (ex: HPA K8s)."""
    if gap.category == InfraGapCategory.MISSING_AUTOSCALING:
        if gap.resource.startswith("Deployment/"):
            deployment_name = gap.resource.split("/")[-1]
            return _k8s_hpa_content(deployment_name)
    return None


def _k8s_hpa_content(deployment_name: str) -> str:
    return f"""\
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: {deployment_name}-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: {deployment_name}
  minReplicas: 2
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
"""


def _generate_new_filename(gap: InfraGap, target_dir: Path) -> Optional[str]:
    """Gera nome para o novo arquivo."""
    if gap.category == InfraGapCategory.MISSING_AUTOSCALING:
        if gap.resource.startswith("Deployment/"):
            deployment_name = gap.resource.split("/")[-1]
            # Garante nome único
            i = 1
            while (target_dir / f"hpa-{deployment_name}-{i}.yaml").exists():
                i += 1
            return f"hpa-{deployment_name}-{i}.yaml"
    return None


def _idempotency_key(gap: InfraGap) -> Optional[str]:
    """Chave para verificar se o patch já foi aplicado."""
    resource_name = gap.resource.split(".")[-1]
    if gap.category == InfraGapCategory.MISSING_AUTOSCALING:
        if gap.resource.startswith("aws_ecs_service"):
            return f'aws_appautoscaling_target" "{resource_name}"'
    return None


# =============================================================================
# BACKUP / RESTORE / VALIDAÇÃO
# =============================================================================

def _create_backup(file_path: Path) -> Path:
    backup = file_path.with_suffix(file_path.suffix + ".bak")
    shutil.copy2(file_path, backup)
    return backup


def _restore_backup(backup: Path, original: Path) -> None:
    if backup.exists():
        shutil.copy2(backup, original)
        backup.unlink(missing_ok=True)


def _validate_tf(content: str) -> bool:
    """Valida HCL tentando parsear com python-hcl2."""
    try:
        import hcl2
        import io
        hcl2.load(io.StringIO(content))
        return True
    except Exception:
        return False


def _validate_yaml(content: str) -> bool:
    """Valida YAML tentando parsear com pyyaml."""
    try:
        import yaml
        yaml.safe_load(content)
        return True
    except Exception:
        return False


# =============================================================================
# ESTRATÉGIA RESOLVER
# =============================================================================

_STRATEGY_MAP = {
    InfraGapCategory.MISSING_AUTOSCALING: {
        "aws_ecs_service": "append_block",
        "Deployment":      "append_file",
    },
    InfraGapCategory.SINGLE_AZ: {
        "aws_db_instance": "modify_attribute",
        "aws_rds_cluster": "modify_attribute",
    },
    InfraGapCategory.UNDERSIZED_INSTANCE: {
        "aws_instance":    "modify_attribute",
    },
}


def _resolve_strategy(gap: InfraGap) -> str:
    # Terraform: "aws_ecs_service.api"  -> prefix = "aws_ecs_service"
    # K8s:       "Deployment/api"       -> prefix = "Deployment"
    resource = gap.resource
    if "/" in resource:
        resource_prefix = resource.split("/")[0]
    else:
        resource_prefix = resource.split(".")[0]
    strategies = _STRATEGY_MAP.get(gap.category, {})
    return strategies.get(resource_prefix, "unknown")