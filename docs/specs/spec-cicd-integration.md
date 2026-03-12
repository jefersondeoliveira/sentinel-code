# Spec: Integração CI/CD — GitHub Actions e GitLab CI

## Status
Fase 5 — [ ] Pendente

## Contexto
O SentinelCode roda localmente via CLI. Em pipelines de entrega contínua, a análise
de qualidade deve ocorrer automaticamente em cada PR/MR antes do merge, bloqueando
a integração se issues críticos forem encontrados. Sem integração CI/CD, a ferramenta
depende de disciplina individual dos desenvolvedores.

## Objetivo
Disponibilizar o SentinelCode como GitHub Action reutilizável e como template de stage
GitLab CI, com suporte a fail-on-critical (bloqueia merge se issues CRITICAL forem detectados)
e comentário automático no PR com resumo dos issues encontrados.

## Escopo

### Inclui
- GitHub Action (`action.yml`) publicável em `marketplace.github.com`
- Template GitLab CI (`.gitlab-ci.yml` de referência)
- Flag `--exit-code` no CLI: retorna código de saída `1` se houver issues `CRITICAL`
- Output estruturado em JSON (`--output-json`) para parsing pelo CI
- Script de comentário automático no PR via GitHub API (`gh` CLI)
- Documentação de uso em `docs/ci-cd-setup.md`

### Não inclui
- Jenkins, CircleCI, Azure DevOps (somente GitHub Actions e GitLab CI)
- Autenticação OAuth (usa tokens de acesso pessoal/CI tokens)
- Deploy automático do dashboard (somente análise)

## Arquitetura

O pipeline LangGraph existente não muda. A integração CI/CD é uma camada
de wrapper no CLI (`main.py`) e arquivos de configuração de CI.

```
CI/CD Pipeline
  → docker run sentinelcode:latest --path . --exit-code --output-json
  → se exit code 1: falha o stage
  → gh pr comment com JSON processado → comentário no PR
```

## Mudanças no AgentState (`models/state.py`)
Nenhuma.

## Novos arquivos

| Arquivo | Responsabilidade |
|---------|-----------------|
| `action.yml` | GitHub Action definition: inputs (path, exit-on-critical, github-token), steps (setup Python, install deps, run SentinelCode, comment on PR) |
| `.github/workflows/sentinelcode-example.yml` | Workflow de exemplo de uso da Action |
| `ci/gitlab-ci-template.yml` | Template de stage GitLab CI com variáveis configuráveis |
| `tools/ci/github_reporter.py` | `post_pr_comment(token, repo, pr_number, summary)` — formata markdown e chama GitHub API |
| `tools/ci/output_formatter.py` | `to_json_summary(state: AgentState) -> dict` — serializa issues e gaps para JSON consumível por CI |
| `docs/ci-cd-setup.md` | Guia de configuração para GitHub Actions e GitLab CI |
| `tests/unit/test_ci_output.py` | Testes do formatter JSON (mínimo 8 testes) |

## Arquivos existentes a modificar

| Arquivo | O que muda |
|---------|-----------|
| `main.py` | Flags `--exit-code` (sys.exit(1) se issues CRITICAL) e `--output-json PATH` (salva JSON além do HTML) |
| `agents/reporter.py` | `render_report_node` aceita `report_format: "json"` como opção adicional |

## Fluxo de dados

```yaml
# .github/workflows/quality.yml
name: SentinelCode Quality Gate
on: [pull_request]

jobs:
  analyze:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: your-org/sentinelcode-action@v1
        with:
          path: ./src
          exit-on-critical: true
          github-token: ${{ secrets.GITHUB_TOKEN }}
```

```python
# Saída JSON para CI
{
  "project": "meu-projeto",
  "timestamp": "2026-03-11T14:30:22",
  "summary": {
    "critical": 2,
    "high": 3,
    "total_issues": 5,
    "total_gaps": 2,
    "fixes_applied": 0
  },
  "issues": [
    {"category": "N+1 Query", "severity": "CRITICAL", "file": "OrderService.java", "line": 142}
  ],
  "exit_code": 1
}
```

## Decisões técnicas

- **Docker**: a Action usa `python:3.11-slim` com `pip install sentinel-code` (ou build local)
- **Exit code**: `0` = sem issues críticos; `1` = issues críticos encontrados; `2` = erro de execução
- **Comentário no PR**: usa `GITHUB_TOKEN` padrão do Actions (sem token adicional necessário)
- **`--dry-run` no CI**: recomendado por padrão (não modifica arquivos do repositório)
- **Timeout**: a Action define timeout de 10 minutos (análise não deve bloquear CI por mais)

## Critérios de aceitação

- [ ] `python main.py --path . --exit-code` retorna `1` quando há issues CRITICAL
- [ ] `python main.py --path . --exit-code` retorna `0` quando não há issues CRITICAL
- [ ] `python main.py --path . --output-json output.json` gera arquivo JSON válido
- [ ] JSON contém `summary.critical`, `summary.high`, `issues[]` e `exit_code`
- [ ] `action.yml` é válido como GitHub Action
- [ ] Template GitLab CI executa análise em stage separado
- [ ] `pytest tests/unit/test_ci_output.py` passa

## Testes

```python
# tests/unit/test_ci_output.py
# - test_json_output_contains_summary
# - test_json_summary_counts_critical_correctly
# - test_json_output_serializable
# - test_exit_code_1_when_critical_issues
# - test_exit_code_0_when_no_critical_issues
# - test_exit_code_0_when_only_high_issues
# - test_json_file_written_to_path
# - test_json_issues_list_matches_state_issues
```
