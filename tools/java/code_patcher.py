"""
Code Patcher
─────────────
Responsável por aplicar correções em arquivos Java de forma segura.

Princípios:
  - Sempre faz backup antes de modificar
  - Cada patch é rastreável (before/after)
  - Falha explicitamente em vez de corromper o arquivo
"""

import shutil
from pathlib import Path
from typing import Optional
from dataclasses import dataclass


@dataclass
class PatchResult:
    """
    Resultado de uma tentativa de patch em um arquivo.

    Campos:
        success     : True se o patch foi aplicado com sucesso
        file_path   : Caminho do arquivo modificado
        before      : Conteúdo original completo do arquivo
        after       : Conteúdo após a correção
        diff_summary: Resumo legível do que mudou
        error       : Mensagem de erro se success=False
    """
    success: bool
    file_path: str
    before: str
    after: str
    diff_summary: str
    error: Optional[str] = None


def apply_patch(
    project_path: str,
    relative_file_path: str,
    original_snippet: str,
    fixed_snippet: str,
    backup: bool = True,
) -> PatchResult:
    """
    Aplica uma correção pontual num arquivo Java.

    Estratégia: substituição de string
    - Procura pelo `original_snippet` no arquivo
    - Substitui pelo `fixed_snippet`
    - Simples, previsível e reversível

    Args:
        project_path       : Raiz do projeto (ex: ./sample_project)
        relative_file_path : Caminho relativo ao projeto (ex: src/main/java/OrderService.java)
        original_snippet   : Trecho exato que será substituído
        fixed_snippet      : Código corrigido que vai no lugar
        backup             : Se True, salva .bak antes de modificar

    Returns:
        PatchResult com o resultado da operação
    """
    # Normaliza separadores de path (Windows usa \, mas o Java usa /)
    normalized_path = relative_file_path.replace("\\", "/")
    file_path = Path(project_path) / normalized_path

    if not file_path.exists():
        return PatchResult(
            success=False,
            file_path=str(file_path),
            before="",
            after="",
            diff_summary="",
            error=f"Arquivo não encontrado: {file_path}",
        )

    original_content = file_path.read_text(encoding="utf-8", errors="replace")

    # Verifica se o snippet original realmente existe no arquivo
    if original_snippet.strip() not in original_content:
        return PatchResult(
            success=False,
            file_path=str(file_path),
            before=original_content,
            after=original_content,
            diff_summary="",
            error=(
                "Snippet original não encontrado no arquivo. "
                "O LLM pode ter gerado código diferente do que está no arquivo."
            ),
        )

    # Faz backup se solicitado
    if backup:
        backup_path = file_path.with_suffix(file_path.suffix + ".bak")
        shutil.copy2(file_path, backup_path)

    # Aplica a correção
    patched_content = original_content.replace(
        original_snippet.strip(),
        fixed_snippet.strip(),
        1,  # Substitui apenas a primeira ocorrência
    )

    # Salva o arquivo corrigido
    file_path.write_text(patched_content, encoding="utf-8")

    # Gera resumo do diff
    diff_summary = _generate_diff_summary(original_content, patched_content)

    return PatchResult(
        success=True,
        file_path=str(file_path),
        before=original_content,
        after=patched_content,
        diff_summary=diff_summary,
    )


def apply_config_patch(
    project_path: str,
    config_content: str,
    filename: str = "src/main/resources/application.yml",
) -> PatchResult:
    """
    Cria ou atualiza um arquivo de configuração.

    Usado principalmente para adicionar configurações do HikariCP
    quando o arquivo está vazio ou não existe.
    """
    file_path = Path(project_path) / filename

    original_content = ""
    if file_path.exists():
        original_content = file_path.read_text(encoding="utf-8", errors="replace")
        # Backup do original
        backup_path = file_path.with_suffix(file_path.suffix + ".bak")
        shutil.copy2(file_path, backup_path)

    # Se o arquivo já tem conteúdo, adiciona ao final com separador
    if original_content.strip():
        new_content = original_content + "\n\n# --- Adicionado pelo SentinelCode ---\n" + config_content
    else:
        new_content = config_content

    # Garante que o diretório existe
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(new_content, encoding="utf-8")

    return PatchResult(
        success=True,
        file_path=str(file_path),
        before=original_content,
        after=new_content,
        diff_summary=f"Configuração adicionada em {filename}",
    )


def restore_backup(project_path: str, relative_file_path: str) -> bool:
    """
    Restaura o backup de um arquivo (desfaz o patch).
    Útil quando os testes falham após a correção.
    """
    normalized_path = relative_file_path.replace("\\", "/")
    file_path = Path(project_path) / normalized_path
    backup_path = file_path.with_suffix(file_path.suffix + ".bak")

    if not backup_path.exists():
        return False

    shutil.copy2(backup_path, file_path)
    backup_path.unlink()  # Remove o backup após restaurar
    return True


def _generate_diff_summary(before: str, after: str) -> str:
    """
    Gera um resumo legível das linhas adicionadas e removidas.
    Não usa a lib `difflib` para manter a saída simples e legível.
    """
    before_lines = set(before.splitlines())
    after_lines = set(after.splitlines())

    removed = [l for l in before_lines - after_lines if l.strip()]
    added = [l for l in after_lines - before_lines if l.strip()]

    summary_parts = []
    if removed:
        summary_parts.append(f"{len(removed)} linha(s) removida(s)")
    if added:
        summary_parts.append(f"{len(added)} linha(s) adicionada(s)")

    return " | ".join(summary_parts) if summary_parts else "Sem alterações"