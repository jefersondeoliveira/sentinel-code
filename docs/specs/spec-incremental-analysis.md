# Spec: Análise Incremental (só arquivos modificados no diff/PR)

## Status
Fase 5 — [ ] Pendente

## Contexto
Em repositórios grandes (centenas de arquivos Java), o SentinelCode analisa todo o
projeto a cada execução. Isso resulta em tempos de análise longos (10–60s dependendo
do projeto) e muitos issues de arquivos não relacionados ao PR em questão.

Análise incremental limita o escopo aos arquivos modificados no diff do PR/branch,
reduzindo tempo de execução e focando os resultados no que o desenvolvedor realmente mudou.

## Objetivo
Suportar flag `--diff` que aceita um branch ou commit SHA de referência e analisa
somente os arquivos Java/IaC modificados entre esse ponto e o HEAD atual.

## Escopo

### Inclui
- Flag `--diff <ref>` no CLI (ex: `--diff main`, `--diff HEAD~1`, `--diff abc1234`)
- Integração com `git diff --name-only <ref>...HEAD` para obter arquivos modificados
- Filtragem de `java_files` e `iac_files` para incluir somente os modificados
- Nota no relatório HTML indicando que a análise foi incremental e quais arquivos foram incluídos
- Compatibilidade com modo `--dry-run` e todos os agentes existentes

### Não inclui
- Análise de arquivos deletados (somente adicionados e modificados)
- Suporte a SVN ou Mercurial (somente git)
- Cache de análise anterior para reutilização (análise completa dos arquivos filtrados)
- Análise de dependências transitivas (se A modifica B, B não é incluído automaticamente)

## Arquitetura

A filtragem ocorre no nó `read_files_node` do Code Analyzer e no `read_iac_files_node`
do IaC Analyzer. O AgentState recebe um campo `diff_files` com a lista de arquivos
modificados; os readers filtram com base nessa lista.

```
main.py → resolve diff_files via git diff
         → passa diff_files no AgentState inicial

read_files_node
  → lê todos os arquivos (como antes)
  → se diff_files não vazio: filtra java_files para interseção com diff_files

read_iac_files_node
  → lê todos os arquivos IaC
  → se diff_files não vazio: filtra iac_files
```

## Mudanças no AgentState (`models/state.py`)

Adicionar campo:
```python
diff_files: List[str]  # paths relativos dos arquivos no diff; vazio = análise completa
```

## Novos arquivos

| Arquivo | Responsabilidade |
|---------|-----------------|
| `tools/git/diff_resolver.py` | `get_diff_files(project_path, ref) -> List[str]` — executa `git diff --name-only <ref>...HEAD` e retorna paths relativos |
| `tests/unit/test_diff_resolver.py` | Testes com mock de subprocess (mínimo 8 testes) |

## Arquivos existentes a modificar

| Arquivo | O que muda |
|---------|-----------|
| `main.py` | Flag `--diff TEXT` (default `""`) → resolve diff_files e adiciona ao initial_state |
| `models/state.py` | Adicionar `diff_files: List[str]` |
| `agents/code_analyzer.py` | `read_files_node` filtra `java_files` se `state["diff_files"]` não vazio |
| `agents/iac_analyzer.py` | `read_iac_files_node` filtra `iac_files` se `state["diff_files"]` não vazio |
| `agents/reporter.py` | Inclui nota de "análise incremental" e lista de arquivos analisados quando `diff_files` não vazio |

## Fluxo de dados

```bash
# Uso em PR — analisa só o que mudou em relação ao main
python main.py --path ./meu-projeto --diff main --dry-run

# Uso local — analisa só o último commit
python main.py --path ./meu-projeto --diff HEAD~1
```

```python
# tools/git/diff_resolver.py
def get_diff_files(project_path: str, ref: str) -> List[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{ref}...HEAD"],
        cwd=project_path,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode != 0:
        logger.warning(f"git diff falhou: {result.stderr}")
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]

# agents/code_analyzer.py — filtragem
def read_files_node(state: AgentState) -> dict:
    all_files = read_java_files(state["project_path"])
    diff_files = state.get("diff_files", [])

    if diff_files:
        diff_set = set(diff_files)
        filtered = [f for f in all_files if any(d in f["path"] for d in diff_set)]
        logger.info(f"Análise incremental: {len(filtered)}/{len(all_files)} arquivos")
        return {"java_files": filtered, "messages": [f"Incremental: {len(filtered)} arquivos"]}

    return {"java_files": all_files, ...}
```

## Decisões técnicas

- **`git diff --name-only <ref>...HEAD`**: os três pontos (`...`) comparam a ponta do branch com o ancestral comum — comportamento correto para PR diffs
- **Fallback gracioso**: se `git` não estiver disponível ou `ref` inválida, análise completa é executada com warning
- **Paths relativos**: `git diff` retorna paths relativos à raiz do repositório; comparação normalizada com `/` em todos os sistemas
- **Cross-file detectors**: detectores que operam em múltiplos arquivos (MISSING_INDEX faz dois passes) podem perder correlações — documentar como limitação conhecida

## Critérios de aceitação

- [ ] `--diff main` analisa somente arquivos modificados em relação ao main
- [ ] `--diff HEAD~1` analisa somente arquivos do último commit
- [ ] Análise sem `--diff` continua analisando todos os arquivos
- [ ] Relatório HTML indica "Análise incremental — N arquivos analisados"
- [ ] `git` indisponível ou ref inválida executa análise completa com warning
- [ ] IaC files também são filtrados pelo diff
- [ ] `pytest tests/unit/test_diff_resolver.py` passa

## Testes

```python
# tests/unit/test_diff_resolver.py
# - test_get_diff_files_returns_changed_files (mock subprocess)
# - test_get_diff_files_empty_on_no_changes
# - test_git_not_available_returns_empty_list
# - test_invalid_ref_returns_empty_list
# - test_paths_are_normalized
# - test_only_java_files_in_diff
# - test_only_iac_files_in_diff
# - test_mixed_files_in_diff
```
