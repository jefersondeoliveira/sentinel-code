"""
Testes dos detectores K8s — Fase 3.

Rode com:
    pytest tests/unit/test_k8s_detectors.py -v
"""

import pytest
from tools.iac.gap_detectors import (
    detect_k8s_missing_resource_limits,
    detect_k8s_missing_probes,
)
from models.infra_gap import InfraGapCategory
from models.issue import Severity


# =============================================================================
# Fixtures
# =============================================================================

def _deployment(containers: list, name: str = "api") -> dict:
    """Constrói um arquivo IaC K8s no formato esperado pelo detector."""
    return {
        "path": f"k8s/{name}.yaml",
        "type": "kubernetes",
        "content": "",
        "parsed": {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": name},
            "spec": {
                "template": {
                    "spec": {
                        "containers": containers,
                    }
                }
            },
        },
    }


def _terraform_file() -> dict:
    return {"path": "main.tf", "type": "terraform", "content": "", "parsed": {}}


CONTAINER_NO_RESOURCES = {"name": "api", "image": "api:latest"}

CONTAINER_WITH_RESOURCES = {
    "name": "api",
    "image": "api:latest",
    "resources": {
        "requests": {"cpu": "100m", "memory": "128Mi"},
        "limits": {"cpu": "500m", "memory": "512Mi"},
    },
}

CONTAINER_WITH_PROBES = {
    "name": "api",
    "image": "api:latest",
    "livenessProbe": {"httpGet": {"path": "/actuator/health", "port": 8080}},
    "readinessProbe": {"httpGet": {"path": "/actuator/health", "port": 8080}},
}


# =============================================================================
# detect_k8s_missing_resource_limits
# =============================================================================

class TestK8sMissingResourceLimits:

    def test_detects_missing_resources(self):
        files = [_deployment([CONTAINER_NO_RESOURCES])]
        gaps = detect_k8s_missing_resource_limits(files, {})
        assert len(gaps) >= 1
        assert gaps[0].category == InfraGapCategory.UNDERSIZED_INSTANCE
        assert gaps[0].severity == Severity.HIGH

    def test_no_gap_when_resources_present(self):
        files = [_deployment([CONTAINER_WITH_RESOURCES])]
        gaps = detect_k8s_missing_resource_limits(files, {})
        assert len(gaps) == 0

    def test_ignores_terraform_files(self):
        gaps = detect_k8s_missing_resource_limits([_terraform_file()], {})
        assert len(gaps) == 0

    def test_returns_empty_on_empty_input(self):
        assert detect_k8s_missing_resource_limits([], {}) == []

    def test_handles_missing_spec_gracefully(self):
        files = [{
            "path": "bad.yaml",
            "type": "kubernetes",
            "content": "",
            "parsed": {"kind": "Deployment", "metadata": {"name": "x"}},
        }]
        gaps = detect_k8s_missing_resource_limits(files, {})
        assert isinstance(gaps, list)

    def test_ignores_non_deployment_kinds(self):
        files = [{
            "path": "service.yaml",
            "type": "kubernetes",
            "content": "",
            "parsed": {"kind": "Service", "metadata": {"name": "api"}},
        }]
        gaps = detect_k8s_missing_resource_limits(files, {})
        assert len(gaps) == 0

    def test_resource_name_format(self):
        files = [_deployment([CONTAINER_NO_RESOURCES], name="backend")]
        gaps = detect_k8s_missing_resource_limits(files, {})
        assert len(gaps) >= 1
        assert "Deployment/backend" in gaps[0].resource

    def test_detects_partial_resources(self):
        """Detecta container com requests mas sem limits."""
        container = {
            "name": "api",
            "image": "api:latest",
            "resources": {"requests": {"cpu": "100m"}},
        }
        files = [_deployment([container])]
        gaps = detect_k8s_missing_resource_limits(files, {})
        assert len(gaps) >= 1


# =============================================================================
# detect_k8s_missing_probes
# =============================================================================

class TestK8sMissingProbes:

    def test_detects_missing_probes(self):
        files = [_deployment([CONTAINER_NO_RESOURCES])]
        gaps = detect_k8s_missing_probes(files, {})
        assert len(gaps) >= 1
        assert gaps[0].category == InfraGapCategory.MISSING_HEALTH_CHECK
        assert gaps[0].severity == Severity.HIGH

    def test_no_gap_when_probes_present(self):
        files = [_deployment([CONTAINER_WITH_PROBES])]
        gaps = detect_k8s_missing_probes(files, {})
        assert len(gaps) == 0

    def test_ignores_terraform_files(self):
        gaps = detect_k8s_missing_probes([_terraform_file()], {})
        assert len(gaps) == 0

    def test_returns_empty_on_empty_input(self):
        assert detect_k8s_missing_probes([], {}) == []

    def test_ignores_non_deployment_kinds(self):
        files = [{
            "path": "svc.yaml",
            "type": "kubernetes",
            "content": "",
            "parsed": {"kind": "Service", "metadata": {"name": "x"}},
        }]
        gaps = detect_k8s_missing_probes(files, {})
        assert len(gaps) == 0

    def test_evidence_mentions_missing_probes(self):
        files = [_deployment([CONTAINER_NO_RESOURCES])]
        gaps = detect_k8s_missing_probes(files, {})
        assert len(gaps) >= 1
        assert "Probe" in gaps[0].evidence or "probe" in gaps[0].evidence.lower()
