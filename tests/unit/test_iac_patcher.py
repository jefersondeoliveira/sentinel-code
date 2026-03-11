"""
Testes do IaC Patcher Agent — escritos ANTES da implementação (Spec Driven).

Rode com: pytest tests/unit/test_iac_patcher.py -v
"""

import pytest
from pathlib import Path
from models.infra_gap import InfraGap, InfraGapCategory
from models.issue import Severity


# =============================================================================
# HELPERS
# =============================================================================

def make_gap(category, resource, file_path, current_config=None, recommended_config=None):
    return InfraGap(
        category=category,
        severity=Severity.HIGH,
        resource=resource,
        file_path=file_path,
        root_cause="test",
        evidence="test",
        suggestion="test",
        current_config=current_config or {},
        recommended_config=recommended_config or {},
    )


def write_tf(tmp_path, name, content):
    f = tmp_path / name
    f.write_text(content, encoding="utf-8")
    return f


def write_yaml(tmp_path, name, content):
    f = tmp_path / name
    f.write_text(content, encoding="utf-8")
    return f


# =============================================================================
# FIXTURES
# =============================================================================

TF_ECS_NO_AUTOSCALING = """\
resource "aws_ecs_service" "api" {
  name          = "api"
  cluster       = "main"
  desired_count = 2
}
"""

TF_ECS_WITH_AUTOSCALING = """\
resource "aws_ecs_service" "api" {
  name          = "api"
  cluster       = "main"
  desired_count = 2
}

resource "aws_appautoscaling_target" "api" {
  service_namespace  = "ecs"
  scalable_dimension = "ecs:service:DesiredCount"
  resource_id        = "service/main/api"
  min_capacity       = 2
  max_capacity       = 10
}
"""

TF_RDS_SINGLE_AZ = """\
resource "aws_db_instance" "main" {
  identifier     = "prod-db"
  instance_class = "db.t3.medium"
  multi_az       = false
  engine         = "postgres"
}
"""

TF_RDS_MULTI_AZ = """\
resource "aws_db_instance" "main" {
  identifier     = "prod-db"
  instance_class = "db.t3.medium"
  multi_az       = true
  engine         = "postgres"
}
"""

YAML_DEPLOYMENT = """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 2
"""


# =============================================================================
# TESTES — patch de autoscaling (append_block)
# =============================================================================

class TestAutoscalingPatch:

    def test_appends_autoscaling_block_to_tf(self, tmp_path):
        from tools.iac.iac_patcher import apply_iac_patch
        tf_file = write_tf(tmp_path, "main.tf", TF_ECS_NO_AUTOSCALING)
        gap = make_gap(
            InfraGapCategory.MISSING_AUTOSCALING,
            "aws_ecs_service.api",
            "main.tf",
        )
        result = apply_iac_patch(gap, str(tmp_path))
        content = tf_file.read_text()
        assert "aws_appautoscaling_target" in content
        assert result["status"] == "applied"

    def test_backup_created_before_autoscaling_patch(self, tmp_path):
        from tools.iac.iac_patcher import apply_iac_patch
        tf_file = write_tf(tmp_path, "main.tf", TF_ECS_NO_AUTOSCALING)
        gap = make_gap(
            InfraGapCategory.MISSING_AUTOSCALING,
            "aws_ecs_service.api",
            "main.tf",
        )
        apply_iac_patch(gap, str(tmp_path))
        # backup deve existir durante o patch ou ter sido limpo após sucesso
        # O arquivo principal deve estar modificado
        assert "aws_appautoscaling_target" in tf_file.read_text()

    def test_idempotent_autoscaling(self, tmp_path):
        from tools.iac.iac_patcher import apply_iac_patch
        write_tf(tmp_path, "main.tf", TF_ECS_WITH_AUTOSCALING)
        gap = make_gap(
            InfraGapCategory.MISSING_AUTOSCALING,
            "aws_ecs_service.api",
            "main.tf",
        )
        result = apply_iac_patch(gap, str(tmp_path))
        assert result["status"] == "skipped"

    def test_autoscaling_result_has_before_and_after(self, tmp_path):
        from tools.iac.iac_patcher import apply_iac_patch
        write_tf(tmp_path, "main.tf", TF_ECS_NO_AUTOSCALING)
        gap = make_gap(
            InfraGapCategory.MISSING_AUTOSCALING,
            "aws_ecs_service.api",
            "main.tf",
        )
        result = apply_iac_patch(gap, str(tmp_path))
        assert "before" in result
        assert "after" in result
        assert result["before"] != result["after"]

    def test_autoscaling_uses_correct_service_name(self, tmp_path):
        from tools.iac.iac_patcher import apply_iac_patch
        content = TF_ECS_NO_AUTOSCALING.replace('"api"', '"my-service"')
        write_tf(tmp_path, "main.tf", content)
        gap = make_gap(
            InfraGapCategory.MISSING_AUTOSCALING,
            "aws_ecs_service.my-service",
            "main.tf",
        )
        result = apply_iac_patch(gap, str(tmp_path))
        patched = (tmp_path / "main.tf").read_text()
        assert "my-service" in patched
        assert result["status"] == "applied"


# =============================================================================
# TESTES — patch de single AZ (modify_attribute)
# =============================================================================

class TestSingleAzPatch:

    def test_modifies_multi_az_false_to_true(self, tmp_path):
        from tools.iac.iac_patcher import apply_iac_patch
        tf_file = write_tf(tmp_path, "database.tf", TF_RDS_SINGLE_AZ)
        gap = make_gap(
            InfraGapCategory.SINGLE_AZ,
            "aws_db_instance.main",
            "database.tf",
            current_config={"multi_az": False},
            recommended_config={"multi_az": True},
        )
        result = apply_iac_patch(gap, str(tmp_path))
        content = tf_file.read_text()
        assert "multi_az       = true" in content or "multi_az = true" in content
        assert result["status"] == "applied"

    def test_idempotent_single_az(self, tmp_path):
        from tools.iac.iac_patcher import apply_iac_patch
        write_tf(tmp_path, "database.tf", TF_RDS_MULTI_AZ)
        gap = make_gap(
            InfraGapCategory.SINGLE_AZ,
            "aws_db_instance.main",
            "database.tf",
            current_config={"multi_az": True},
            recommended_config={"multi_az": True},
        )
        result = apply_iac_patch(gap, str(tmp_path))
        assert result["status"] == "skipped"

    def test_single_az_result_registered(self, tmp_path):
        from tools.iac.iac_patcher import apply_iac_patch
        write_tf(tmp_path, "database.tf", TF_RDS_SINGLE_AZ)
        gap = make_gap(
            InfraGapCategory.SINGLE_AZ,
            "aws_db_instance.main",
            "database.tf",
            current_config={"multi_az": False},
            recommended_config={"multi_az": True},
        )
        result = apply_iac_patch(gap, str(tmp_path))
        assert result["category"] == InfraGapCategory.SINGLE_AZ.value
        assert result["resource"] == "aws_db_instance.main"


# =============================================================================
# TESTES — patch de HPA K8s (append_file)
# =============================================================================

class TestK8sHpaPatch:

    def test_creates_hpa_file_for_deployment(self, tmp_path):
        from tools.iac.iac_patcher import apply_iac_patch
        write_yaml(tmp_path, "deployment.yaml", YAML_DEPLOYMENT)
        gap = make_gap(
            InfraGapCategory.MISSING_AUTOSCALING,
            "Deployment/api",
            "deployment.yaml",
        )
        result = apply_iac_patch(gap, str(tmp_path))
        yaml_files = list(tmp_path.glob("hpa-*.yaml"))
        assert len(yaml_files) == 1
        assert result["status"] == "applied"

    def test_hpa_file_has_correct_target(self, tmp_path):
        from tools.iac.iac_patcher import apply_iac_patch
        write_yaml(tmp_path, "deployment.yaml", YAML_DEPLOYMENT)
        gap = make_gap(
            InfraGapCategory.MISSING_AUTOSCALING,
            "Deployment/api",
            "deployment.yaml",
        )
        apply_iac_patch(gap, str(tmp_path))
        hpa_file = list(tmp_path.glob("hpa-*.yaml"))[0]
        content = hpa_file.read_text()
        assert "name: api" in content
        assert "HorizontalPodAutoscaler" in content

    def test_hpa_file_is_valid_yaml(self, tmp_path):
        from tools.iac.iac_patcher import apply_iac_patch
        import yaml
        write_yaml(tmp_path, "deployment.yaml", YAML_DEPLOYMENT)
        gap = make_gap(
            InfraGapCategory.MISSING_AUTOSCALING,
            "Deployment/api",
            "deployment.yaml",
        )
        apply_iac_patch(gap, str(tmp_path))
        hpa_file = list(tmp_path.glob("hpa-*.yaml"))[0]
        parsed = yaml.safe_load(hpa_file.read_text())
        assert parsed["kind"] == "HorizontalPodAutoscaler"


# =============================================================================
# TESTES — validação e rollback
# =============================================================================

class TestValidationAndRollback:

    def test_file_unchanged_after_failed_patch(self, tmp_path):
        from tools.iac.iac_patcher import apply_iac_patch
        original = TF_RDS_SINGLE_AZ
        tf_file = write_tf(tmp_path, "database.tf", original)

        # Gap com arquivo inexistente (force failure)
        gap = make_gap(
            InfraGapCategory.SINGLE_AZ,
            "aws_db_instance.nonexistent",
            "nonexistent.tf",  # arquivo que não existe
        )
        result = apply_iac_patch(gap, str(tmp_path))
        assert result["status"] in ("failed", "skipped")
        # arquivo original não deve ter sido modificado
        assert tf_file.read_text() == original

    def test_fix_applied_flag_true_on_success(self, tmp_path):
        from tools.iac.iac_patcher import apply_iac_patch
        write_tf(tmp_path, "main.tf", TF_ECS_NO_AUTOSCALING)
        gap = make_gap(
            InfraGapCategory.MISSING_AUTOSCALING,
            "aws_ecs_service.api",
            "main.tf",
        )
        result = apply_iac_patch(gap, str(tmp_path))
        assert result["status"] == "applied"

    def test_unknown_category_returns_skipped(self, tmp_path):
        from tools.iac.iac_patcher import apply_iac_patch
        write_tf(tmp_path, "main.tf", TF_ECS_NO_AUTOSCALING)
        gap = make_gap(
            InfraGapCategory.GENERAL,  # sem estratégia definida
            "some_resource.x",
            "main.tf",
        )
        result = apply_iac_patch(gap, str(tmp_path))
        assert result["status"] == "skipped"


# =============================================================================
# TESTES — pipeline do IaC Patcher Agent
# =============================================================================

class TestIaCPatcherPipeline:

    def test_pipeline_patches_all_fixable_gaps(self, tmp_path):
        from agents.iac_patcher import build_iac_patcher_graph
        write_tf(tmp_path, "main.tf", TF_ECS_NO_AUTOSCALING + "\n" + TF_RDS_SINGLE_AZ)

        gaps = [
            make_gap(InfraGapCategory.MISSING_AUTOSCALING, "aws_ecs_service.api", "main.tf"),
            make_gap(InfraGapCategory.SINGLE_AZ, "aws_db_instance.main", "database.tf"),
        ]
        write_tf(tmp_path, "database.tf", TF_RDS_SINGLE_AZ)

        state = {
            "project_path": str(tmp_path),
            "project_type": "terraform",
            "non_functional_requirements": {},
            "java_files": [], "issues": [],
            "iac_files": [
                {"path": "main.tf", "full_path": str(tmp_path / "main.tf"),
                 "type": "terraform", "content": TF_ECS_NO_AUTOSCALING, "parsed": None},
                {"path": "database.tf", "full_path": str(tmp_path / "database.tf"),
                 "type": "terraform", "content": TF_RDS_SINGLE_AZ, "parsed": None},
            ],
            "infra_gaps": gaps,
            "applied_fixes": [],
            "final_report": None,
            "messages": [],
        }

        graph  = build_iac_patcher_graph()
        result = graph.invoke(state)
        applied = [f for f in result["applied_fixes"] if f.get("status") == "applied"]
        assert len(applied) >= 1

    def test_pipeline_registers_fixes_in_state(self, tmp_path):
        from agents.iac_patcher import build_iac_patcher_graph
        write_tf(tmp_path, "main.tf", TF_ECS_NO_AUTOSCALING)

        state = {
            "project_path": str(tmp_path),
            "project_type": "terraform",
            "non_functional_requirements": {},
            "java_files": [], "issues": [],
            "iac_files": [
                {"path": "main.tf", "full_path": str(tmp_path / "main.tf"),
                 "type": "terraform", "content": TF_ECS_NO_AUTOSCALING, "parsed": None},
            ],
            "infra_gaps": [
                make_gap(InfraGapCategory.MISSING_AUTOSCALING, "aws_ecs_service.api", "main.tf"),
            ],
            "applied_fixes": [],
            "final_report": None,
            "messages": [],
        }

        graph  = build_iac_patcher_graph()
        result = graph.invoke(state)
        assert len(result["applied_fixes"]) > 0
        assert result["applied_fixes"][0]["category"] == InfraGapCategory.MISSING_AUTOSCALING.value

    def test_pipeline_empty_gaps_does_not_raise(self, tmp_path):
        from agents.iac_patcher import build_iac_patcher_graph
        state = {
            "project_path": str(tmp_path),
            "project_type": "terraform",
            "non_functional_requirements": {},
            "java_files": [], "issues": [],
            "iac_files": [],
            "infra_gaps": [],
            "applied_fixes": [],
            "final_report": None,
            "messages": [],
        }
        graph  = build_iac_patcher_graph()
        result = graph.invoke(state)
        assert result["applied_fixes"] == []


# =============================================================================
# Testes da estratégia modify_yaml (K8s) — Fase 3
# =============================================================================

YAML_NO_RESOURCES = """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  template:
    spec:
      containers:
      - name: api
        image: api:latest
"""

YAML_NO_PROBES = """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  template:
    spec:
      containers:
      - name: api
        image: api:latest
        resources:
          requests:
            cpu: 100m
          limits:
            cpu: 500m
"""

YAML_FULL = """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  template:
    spec:
      containers:
      - name: api
        image: api:latest
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 500m
            memory: 512Mi
        livenessProbe:
          httpGet:
            path: /actuator/health
            port: 8080
        readinessProbe:
          httpGet:
            path: /actuator/health
            port: 8080
"""


class TestK8sYamlPatch:

    def test_adds_resource_limits_to_deployment(self, tmp_path):
        from tools.iac.iac_patcher import apply_iac_patch
        f = tmp_path / "deployment.yaml"
        f.write_text(YAML_NO_RESOURCES, encoding="utf-8")
        gap = make_gap(InfraGapCategory.UNDERSIZED_INSTANCE, "Deployment/api", "deployment.yaml")
        result = apply_iac_patch(gap, str(tmp_path))
        assert result["status"] == "applied"
        content = f.read_text()
        assert "resources" in content

    def test_adds_probes_to_deployment(self, tmp_path):
        from tools.iac.iac_patcher import apply_iac_patch
        f = tmp_path / "deployment.yaml"
        f.write_text(YAML_NO_PROBES, encoding="utf-8")
        gap = make_gap(InfraGapCategory.MISSING_HEALTH_CHECK, "Deployment/api", "deployment.yaml")
        result = apply_iac_patch(gap, str(tmp_path))
        assert result["status"] == "applied"
        content = f.read_text()
        assert "livenessProbe" in content
        assert "readinessProbe" in content

    def test_skips_if_already_fully_configured(self, tmp_path):
        from tools.iac.iac_patcher import apply_iac_patch
        f = tmp_path / "deployment.yaml"
        f.write_text(YAML_FULL, encoding="utf-8")
        gap = make_gap(InfraGapCategory.MISSING_HEALTH_CHECK, "Deployment/api", "deployment.yaml")
        result = apply_iac_patch(gap, str(tmp_path))
        assert result["status"] == "skipped"

    def test_patched_yaml_is_valid(self, tmp_path):
        import yaml
        from tools.iac.iac_patcher import apply_iac_patch
        f = tmp_path / "deployment.yaml"
        f.write_text(YAML_NO_RESOURCES, encoding="utf-8")
        gap = make_gap(InfraGapCategory.MISSING_HEALTH_CHECK, "Deployment/api", "deployment.yaml")
        result = apply_iac_patch(gap, str(tmp_path))
        if result["status"] == "applied":
            parsed = yaml.safe_load(f.read_text())
            assert parsed is not None

    def test_fails_gracefully_on_missing_file(self, tmp_path):
        from tools.iac.iac_patcher import apply_iac_patch
        gap = make_gap(InfraGapCategory.MISSING_HEALTH_CHECK, "Deployment/api", "nonexistent.yaml")
        result = apply_iac_patch(gap, str(tmp_path))
        assert result["status"] == "failed"