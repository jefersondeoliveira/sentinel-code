"""
Testes dos detectores IaC — escritos ANTES da implementação (Spec Driven).

Cada teste define o comportamento esperado de um detector.
A implementação só está correta quando todos passam.

Rode com: pytest tests/unit/test_iac_detectors.py -v
"""

import pytest
from models.infra_gap import InfraGapCategory
from models.issue import Severity


# =============================================================================
# FIXTURES — arquivos IaC de exemplo
# =============================================================================

@pytest.fixture
def ecs_without_autoscaling():
    return [{
        "path": "main.tf",
        "type": "terraform",
        "content": """
resource "aws_ecs_service" "api" {
  name            = "api"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = 2
}
""",
        "parsed": {
            "resource": {
                "aws_ecs_service": {
                    "api": {
                        "name": "api",
                        "desired_count": 2
                    }
                }
            }
        }
    }]


@pytest.fixture
def ecs_with_autoscaling():
    return [{
        "path": "main.tf",
        "type": "terraform",
        "content": """
resource "aws_ecs_service" "api" {
  name          = "api"
  desired_count = 2
}

resource "aws_appautoscaling_target" "api" {
  service_namespace  = "ecs"
  scalable_dimension = "ecs:service:DesiredCount"
  resource_id        = "service/main/api"
  min_capacity       = 2
  max_capacity       = 10
}
""",
        "parsed": {
            "resource": {
                "aws_ecs_service": {"api": {"desired_count": 2}},
                "aws_appautoscaling_target": {
                    "api": {
                        "service_namespace": "ecs",
                        "min_capacity": 2,
                        "max_capacity": 10
                    }
                }
            }
        }
    }]


@pytest.fixture
def rds_single_az():
    return [{
        "path": "database.tf",
        "type": "terraform",
        "content": """
resource "aws_db_instance" "main" {
  identifier        = "prod-db"
  instance_class    = "db.t3.medium"
  multi_az          = false
  engine            = "postgres"
}
""",
        "parsed": {
            "resource": {
                "aws_db_instance": {
                    "main": {
                        "identifier": "prod-db",
                        "instance_class": "db.t3.medium",
                        "multi_az": False
                    }
                }
            }
        }
    }]


@pytest.fixture
def rds_multi_az():
    return [{
        "path": "database.tf",
        "type": "terraform",
        "content": """
resource "aws_db_instance" "main" {
  identifier     = "prod-db"
  instance_class = "db.t3.medium"
  multi_az       = true
  engine         = "postgres"
}
""",
        "parsed": {
            "resource": {
                "aws_db_instance": {
                    "main": {"multi_az": True}
                }
            }
        }
    }]


@pytest.fixture
def undersized_instance_high_rps():
    return [{
        "path": "compute.tf",
        "type": "terraform",
        "content": """
resource "aws_instance" "api" {
  ami           = "ami-12345"
  instance_type = "t3.micro"
}
""",
        "parsed": {
            "resource": {
                "aws_instance": {
                    "api": {"instance_type": "t3.micro"}
                }
            }
        }
    }]


@pytest.fixture
def nfr_high_availability():
    return {"availability": "99.9%", "max_rps": 10000}


@pytest.fixture
def nfr_low():
    return {"availability": "99.0%", "max_rps": 500}


@pytest.fixture
def empty_project():
    return []


# =============================================================================
# TESTES — detect_missing_autoscaling
# =============================================================================

class TestDetectMissingAutoscaling:

    def test_detects_ecs_without_autoscaling(self, ecs_without_autoscaling, nfr_high_availability):
        from tools.iac.gap_detectors import detect_missing_autoscaling
        gaps = detect_missing_autoscaling(ecs_without_autoscaling, nfr_high_availability)
        assert len(gaps) == 1
        assert gaps[0].category == InfraGapCategory.MISSING_AUTOSCALING

    def test_severity_high_when_high_availability_nfr(self, ecs_without_autoscaling, nfr_high_availability):
        from tools.iac.gap_detectors import detect_missing_autoscaling
        gaps = detect_missing_autoscaling(ecs_without_autoscaling, nfr_high_availability)
        assert gaps[0].severity == Severity.HIGH

    def test_no_gap_when_autoscaling_present(self, ecs_with_autoscaling, nfr_high_availability):
        from tools.iac.gap_detectors import detect_missing_autoscaling
        gaps = detect_missing_autoscaling(ecs_with_autoscaling, nfr_high_availability)
        assert len(gaps) == 0

    def test_resource_name_in_gap(self, ecs_without_autoscaling, nfr_low):
        from tools.iac.gap_detectors import detect_missing_autoscaling
        gaps = detect_missing_autoscaling(ecs_without_autoscaling, nfr_low)
        assert len(gaps) == 1
        assert "api" in gaps[0].resource

    def test_empty_project_returns_no_gaps(self, empty_project, nfr_high_availability):
        from tools.iac.gap_detectors import detect_missing_autoscaling
        gaps = detect_missing_autoscaling(empty_project, nfr_high_availability)
        assert gaps == []


# =============================================================================
# TESTES — detect_single_az
# =============================================================================

class TestDetectSingleAz:

    def test_detects_rds_single_az(self, rds_single_az, nfr_high_availability):
        from tools.iac.gap_detectors import detect_single_az
        gaps = detect_single_az(rds_single_az, nfr_high_availability)
        assert len(gaps) == 1
        assert gaps[0].category == InfraGapCategory.SINGLE_AZ

    def test_severity_critical_when_high_availability(self, rds_single_az, nfr_high_availability):
        from tools.iac.gap_detectors import detect_single_az
        gaps = detect_single_az(rds_single_az, nfr_high_availability)
        assert gaps[0].severity == Severity.CRITICAL

    def test_severity_medium_when_low_availability(self, rds_single_az, nfr_low):
        from tools.iac.gap_detectors import detect_single_az
        gaps = detect_single_az(rds_single_az, nfr_low)
        assert gaps[0].severity == Severity.MEDIUM

    def test_no_gap_when_multi_az(self, rds_multi_az, nfr_high_availability):
        from tools.iac.gap_detectors import detect_single_az
        gaps = detect_single_az(rds_multi_az, nfr_high_availability)
        assert len(gaps) == 0

    def test_empty_project_returns_no_gaps(self, empty_project, nfr_high_availability):
        from tools.iac.gap_detectors import detect_single_az
        gaps = detect_single_az(empty_project, nfr_high_availability)
        assert gaps == []


# =============================================================================
# TESTES — detect_undersized_instance
# =============================================================================

class TestDetectUndersizedInstance:

    def test_detects_t3_micro_with_high_rps(self, undersized_instance_high_rps, nfr_high_availability):
        from tools.iac.gap_detectors import detect_undersized_instance
        gaps = detect_undersized_instance(undersized_instance_high_rps, nfr_high_availability)
        assert len(gaps) == 1
        assert gaps[0].category == InfraGapCategory.UNDERSIZED_INSTANCE
        assert gaps[0].severity == Severity.CRITICAL

    def test_no_gap_when_low_rps(self, undersized_instance_high_rps, nfr_low):
        from tools.iac.gap_detectors import detect_undersized_instance
        gaps = detect_undersized_instance(undersized_instance_high_rps, nfr_low)
        assert len(gaps) == 0

    def test_evidence_contains_instance_type(self, undersized_instance_high_rps, nfr_high_availability):
        from tools.iac.gap_detectors import detect_undersized_instance
        gaps = detect_undersized_instance(undersized_instance_high_rps, nfr_high_availability)
        assert "t3.micro" in gaps[0].evidence

    def test_empty_project_returns_no_gaps(self, empty_project, nfr_high_availability):
        from tools.iac.gap_detectors import detect_undersized_instance
        gaps = detect_undersized_instance(empty_project, nfr_high_availability)
        assert gaps == []


# =============================================================================
# TESTES — IaC file reader
# =============================================================================

class TestIaCFileReader:

    def test_reads_tf_files(self, tmp_path):
        from tools.iac.file_reader import read_iac_files
        tf_file = tmp_path / "main.tf"
        tf_file.write_text('resource "aws_instance" "api" { instance_type = "t3.micro" }')
        files = read_iac_files(str(tmp_path))
        assert len(files) == 1
        assert files[0]["type"] == "terraform"

    def test_reads_yaml_files(self, tmp_path):
        from tools.iac.file_reader import read_iac_files
        yaml_file = tmp_path / "deployment.yaml"
        yaml_file.write_text("apiVersion: apps/v1\nkind: Deployment\n")
        files = read_iac_files(str(tmp_path))
        assert len(files) == 1
        assert files[0]["type"] == "kubernetes"

    def test_ignores_terraform_lock(self, tmp_path):
        from tools.iac.file_reader import read_iac_files
        lock_file = tmp_path / ".terraform.lock.hcl"
        lock_file.write_text("# lock file")
        files = read_iac_files(str(tmp_path))
        assert len(files) == 0

    def test_invalid_hcl_does_not_abort(self, tmp_path):
        from tools.iac.file_reader import read_iac_files
        bad_tf  = tmp_path / "bad.tf"
        good_tf = tmp_path / "good.tf"
        bad_tf.write_text("this is not valid HCL {{{{")
        good_tf.write_text('resource "aws_instance" "x" { instance_type = "t3.micro" }')
        files = read_iac_files(str(tmp_path))
        # O arquivo inválido é incluído com parsed=None, não aborta
        assert len(files) == 2
        good = next(f for f in files if f["path"].endswith("good.tf"))
        assert good["parsed"] is not None

    def test_empty_directory_returns_empty_list(self, tmp_path):
        from tools.iac.file_reader import read_iac_files
        files = read_iac_files(str(tmp_path))
        assert files == []