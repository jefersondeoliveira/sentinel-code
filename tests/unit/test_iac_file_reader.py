"""
Testes do IaC File Reader — leitura e parse de arquivos Terraform e K8s.

Rode com: pytest tests/unit/test_iac_file_reader.py -v
"""

import pytest
from pathlib import Path


class TestReadTerraformFiles:

    def test_reads_single_tf_file(self, tmp_path):
        from tools.iac.file_reader import read_iac_files
        (tmp_path / "main.tf").write_text(
            'resource "aws_instance" "api" { instance_type = "t3.micro" }'
        )
        files = read_iac_files(str(tmp_path))
        assert len(files) == 1
        assert files[0]["type"] == "terraform"
        assert files[0]["path"].endswith("main.tf")

    def test_reads_multiple_tf_files(self, tmp_path):
        from tools.iac.file_reader import read_iac_files
        (tmp_path / "main.tf").write_text('resource "aws_vpc" "main" {}')
        (tmp_path / "database.tf").write_text('resource "aws_db_instance" "db" {}')
        files = read_iac_files(str(tmp_path))
        assert len(files) == 2

    def test_parses_hcl_into_dict(self, tmp_path):
        from tools.iac.file_reader import read_iac_files
        (tmp_path / "main.tf").write_text(
            'resource "aws_instance" "api" { instance_type = "t3.micro" }'
        )
        files = read_iac_files(str(tmp_path))
        assert files[0]["parsed"] is not None
        assert "resource" in files[0]["parsed"]

    def test_invalid_hcl_sets_parsed_none(self, tmp_path):
        from tools.iac.file_reader import read_iac_files
        (tmp_path / "bad.tf").write_text("this {{ is not valid HCL")
        files = read_iac_files(str(tmp_path))
        assert len(files) == 1
        assert files[0]["parsed"] is None

    def test_invalid_hcl_does_not_abort_other_files(self, tmp_path):
        from tools.iac.file_reader import read_iac_files
        (tmp_path / "bad.tf").write_text("this {{ is not valid HCL")
        (tmp_path / "good.tf").write_text('resource "aws_instance" "x" { instance_type = "t3.small" }')
        files = read_iac_files(str(tmp_path))
        assert len(files) == 2
        good = next(f for f in files if "good" in f["path"])
        assert good["parsed"] is not None

    def test_ignores_terraform_lock_file(self, tmp_path):
        from tools.iac.file_reader import read_iac_files
        (tmp_path / ".terraform.lock.hcl").write_text("# lock")
        files = read_iac_files(str(tmp_path))
        assert len(files) == 0

    def test_ignores_dot_terraform_directory(self, tmp_path):
        from tools.iac.file_reader import read_iac_files
        dot_tf = tmp_path / ".terraform"
        dot_tf.mkdir()
        (dot_tf / "hidden.tf").write_text('resource "aws_instance" "x" {}')
        files = read_iac_files(str(tmp_path))
        assert len(files) == 0

    def test_reads_nested_tf_files(self, tmp_path):
        from tools.iac.file_reader import read_iac_files
        modules = tmp_path / "modules" / "api"
        modules.mkdir(parents=True)
        (modules / "main.tf").write_text('resource "aws_ecs_service" "api" {}')
        files = read_iac_files(str(tmp_path))
        assert len(files) == 1

    def test_empty_directory_returns_empty_list(self, tmp_path):
        from tools.iac.file_reader import read_iac_files
        files = read_iac_files(str(tmp_path))
        assert files == []

    def test_nonexistent_path_raises_error(self):
        from tools.iac.file_reader import read_iac_files
        with pytest.raises(FileNotFoundError):
            read_iac_files("/caminho/que/nao/existe")


class TestReadKubernetesFiles:

    def test_reads_yaml_file(self, tmp_path):
        from tools.iac.file_reader import read_iac_files
        (tmp_path / "deployment.yaml").write_text(
            "apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: api\n"
        )
        files = read_iac_files(str(tmp_path))
        assert len(files) == 1
        assert files[0]["type"] == "kubernetes"

    def test_reads_yml_extension(self, tmp_path):
        from tools.iac.file_reader import read_iac_files
        (tmp_path / "service.yml").write_text(
            "apiVersion: v1\nkind: Service\nmetadata:\n  name: api\n"
        )
        files = read_iac_files(str(tmp_path))
        assert len(files) == 1
        assert files[0]["type"] == "kubernetes"

    def test_parses_yaml_into_dict(self, tmp_path):
        from tools.iac.file_reader import read_iac_files
        (tmp_path / "deployment.yaml").write_text(
            "apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: api\n"
        )
        files = read_iac_files(str(tmp_path))
        assert files[0]["parsed"] is not None
        assert files[0]["parsed"]["kind"] == "Deployment"

    def test_invalid_yaml_sets_parsed_none(self, tmp_path):
        from tools.iac.file_reader import read_iac_files
        (tmp_path / "bad.yaml").write_text("key: [unclosed bracket")
        files = read_iac_files(str(tmp_path))
        assert files[0]["parsed"] is None

    def test_detects_k8s_by_api_version(self, tmp_path):
        from tools.iac.file_reader import read_iac_files
        (tmp_path / "hpa.yaml").write_text(
            "apiVersion: autoscaling/v2\nkind: HorizontalPodAutoscaler\n"
        )
        files = read_iac_files(str(tmp_path))
        assert files[0]["type"] == "kubernetes"

    def test_mixed_tf_and_yaml(self, tmp_path):
        from tools.iac.file_reader import read_iac_files
        (tmp_path / "main.tf").write_text('resource "aws_instance" "x" {}')
        (tmp_path / "deployment.yaml").write_text("apiVersion: apps/v1\nkind: Deployment\n")
        files = read_iac_files(str(tmp_path))
        assert len(files) == 2
        types = {f["type"] for f in files}
        assert "terraform" in types
        assert "kubernetes" in types