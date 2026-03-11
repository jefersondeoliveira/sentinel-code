import os
from pathlib import Path
from typing import List, Optional
import javalang


def read_java_files(project_path: str) -> List[dict]:
    """
    Varre recursivamente o projeto e retorna todos os arquivos .java.

    Retorna uma lista de dicts com:
        path    : caminho relativo ao projeto
        content : conteúdo completo do arquivo
        lines   : número de linhas
        tree    : AST do javalang (None se o parse falhar — Java inválido)

    Por que guardar a AST aqui?
    Parse é caro. Fazemos uma vez e passamos o resultado para todos
    os detectores, que só precisam navegar a árvore já pronta.
    """
    root = Path(project_path)

    if not root.exists():
        raise FileNotFoundError(f"Pasta não encontrada: {project_path}")

    java_files = []

    for java_file in root.rglob("*.java"):
        # Ignora arquivos de teste por padrão (analisamos só o código de produção)
        if _is_test_file(java_file):
            continue

        content = java_file.read_text(encoding="utf-8", errors="replace")

        # Tenta fazer o parse da AST; continua mesmo se falhar
        tree = _safe_parse(content)

        java_files.append({
            "path": str(java_file.relative_to(root)),
            "full_path": str(java_file),
            "content": content,
            "lines": len(content.splitlines()),
            "tree": tree,
        })

    return java_files


def read_application_properties(project_path: str) -> dict:
    """
    Lê application.yml e application.properties procurando por
    configurações relevantes de performance (pool, cache, timeouts).

    Retorna um dict com as propriedades encontradas.
    """
    root = Path(project_path)
    config = {}

    # Procura nos locais padrão do Spring Boot
    candidates = [
        "src/main/resources/application.yml",
        "src/main/resources/application.yaml",
        "src/main/resources/application.properties",
    ]

    for candidate in candidates:
        config_file = root / candidate
        if config_file.exists():
            content = config_file.read_text(encoding="utf-8", errors="replace")
            config[candidate] = content

    return config


def read_pom_xml(project_path: str) -> Optional[str]:
    """
    Lê o pom.xml da raiz do projeto.
    Usado pelo detector de connection pool para verificar
    se HikariCP está declarado como dependência.
    """
    pom = Path(project_path) / "pom.xml"
    if pom.exists():
        return pom.read_text(encoding="utf-8", errors="replace")
    return None


# --- Helpers privados ---

def _is_test_file(path: Path) -> bool:
    """Heurística simples: arquivos em /test/ ou com sufixo Test/Spec."""
    parts = path.parts
    return (
        "test" in parts
        or path.stem.endswith("Test")
        or path.stem.endswith("Tests")
        or path.stem.endswith("Spec")
    )


def _safe_parse(content: str):
    """
    Tenta fazer parse da AST com javalang.
    Retorna None silenciosamente se o arquivo tiver sintaxe inválida
    (ex: código incompleto, anotações customizadas desconhecidas).
    """
    try:
        return javalang.parse.parse(content)
    except Exception:
        return None