"""
IaC File Reader
────────────────
Lê e parseia arquivos de infraestrutura como código.

Suporte:
  - Terraform (.tf)        → python-hcl2
  - Kubernetes (.yaml/yml) → pyyaml
  - CloudFormation         → pyyaml (futuro)

Retorna lista de dicts com:
  path    : caminho relativo ao projeto
  type    : "terraform" | "kubernetes" | "unknown"
  content : conteúdo bruto do arquivo
  parsed  : dict parseado (None se parse falhou)
"""

from pathlib import Path
from typing import List


# Arquivos e diretórios a ignorar
IGNORE_FILES = {".terraform.lock.hcl", "terraform.tfstate", "terraform.tfstate.backup"}
IGNORE_DIRS  = {".terraform", ".git", "node_modules", "__pycache__"}


def read_iac_files(project_path: str) -> List[dict]:
    """
    Varre recursivamente o projeto e retorna todos os arquivos IaC.

    Raises:
        FileNotFoundError: se o diretório não existir
    """
    root = Path(project_path)

    if not root.exists():
        raise FileNotFoundError(f"Pasta não encontrada: {project_path}")

    iac_files = []

    for file_path in sorted(root.rglob("*")):
        # Ignora diretórios
        if not file_path.is_file():
            continue

        # Ignora arquivos e diretórios bloqueados
        if file_path.name in IGNORE_FILES:
            continue
        if any(part in IGNORE_DIRS for part in file_path.parts):
            continue

        suffix = file_path.suffix.lower()

        if suffix == ".tf":
            iac_files.append(_read_terraform_file(file_path, root))
        elif suffix in {".yaml", ".yml"}:
            iac_files.append(_read_yaml_file(file_path, root))

    return iac_files


# =============================================================================
# HELPERS PRIVADOS
# =============================================================================

def _read_terraform_file(file_path: Path, root: Path) -> dict:
    """Lê e parseia um arquivo Terraform HCL."""
    content = file_path.read_text(encoding="utf-8", errors="replace")
    parsed  = _safe_parse_hcl(content)

    return {
        "path":      str(file_path.relative_to(root)),
        "full_path": str(file_path),
        "type":      "terraform",
        "content":   content,
        "parsed":    parsed,
    }


def _read_yaml_file(file_path: Path, root: Path) -> dict:
    """Lê e parseia um arquivo YAML (K8s ou CloudFormation)."""
    content  = file_path.read_text(encoding="utf-8", errors="replace")
    parsed   = _safe_parse_yaml(content)
    iac_type = _detect_yaml_type(parsed)

    return {
        "path":      str(file_path.relative_to(root)),
        "full_path": str(file_path),
        "type":      iac_type,
        "content":   content,
        "parsed":    parsed,
    }


def _safe_parse_hcl(content: str) -> dict | None:
    """Parseia HCL com python-hcl2. Retorna None se falhar."""
    try:
        import hcl2
        import io
        return hcl2.load(io.StringIO(content))
    except Exception:
        return None


def _safe_parse_yaml(content: str) -> dict | None:
    """Parseia YAML. Retorna None se falhar."""
    try:
        import yaml
        return yaml.safe_load(content)
    except Exception:
        return None


def _detect_yaml_type(parsed: dict | None) -> str:
    """Detecta se o YAML é Kubernetes, CloudFormation ou desconhecido."""
    if not parsed or not isinstance(parsed, dict):
        return "unknown"

    # Kubernetes tem apiVersion
    if "apiVersion" in parsed or "kind" in parsed:
        return "kubernetes"

    # CloudFormation tem AWSTemplateFormatVersion ou Resources
    if "AWSTemplateFormatVersion" in parsed or (
        "Resources" in parsed and "Outputs" in parsed
    ):
        return "cloudformation"

    return "unknown"