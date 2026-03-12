# Spec: Comparativo Temporal entre Execuções

## Status
Fase 5 — [ ] Pendente

## Contexto
O SentinelCode gera um relatório por execução, mas não há como saber se os problemas
estão melhorando ou piorando entre sprints. Sem histórico comparativo, equipes não
conseguem demonstrar o impacto do trabalho de performance nem identificar regressões
introduzidas por novos commits.

Esta feature depende da persistência de metadados implementada em `spec-web-dashboard.md`.

## Objetivo
Exibir no relatório HTML e no dashboard a evolução de issues entre a execução atual
e execuções anteriores do mesmo projeto: issues resolvidos, issues novos, issues persistentes.

## Escopo

### Inclui
- Comparação da execução atual com a última execução do mesmo projeto (SQLite)
- Classificação de issues: `novo`, `resolvido`, `persistente`
- Seção "Evolução" no relatório HTML com delta (↑↓ nº de issues por categoria)
- API `GET /api/runs/{id}/compare/{prev_id}` no dashboard
- Gráfico de tendência (sparkline simples em HTML/CSS, sem biblioteca JS)

### Não inclui
- Comparação entre branches diferentes (somente mesmo projeto/path)
- Análise de causa raiz de regressão (somente delta quantitativo)
- Alertas automáticos de regressão (ver `spec-notifications.md` para integração futura)

## Arquitetura

Novo módulo `tools/reporting/comparator.py` (diferente do `tools/benchmark/comparator.py`)
que compara dois snapshots de `RunRecord` para produzir um `ComparisonReport`.

O nó `render_report` consulta o banco antes de renderizar e inclui a comparação
quando uma execução anterior existe.

```
render_report_node
  → carrega última execução do mesmo projeto (SQLite)
  → temporal_comparator.compare(current_state, prev_run)
  → inclui ComparisonReport no template HTML
```

## Mudanças no AgentState (`models/state.py`)
Nenhuma. A comparação é calculada durante a renderização, fora do pipeline LangGraph.

## Novos arquivos

| Arquivo | Responsabilidade |
|---------|-----------------|
| `tools/reporting/temporal_comparator.py` | `compare_runs(current: dict, previous: dict) -> ComparisonReport` — calcula delta de issues por categoria e severidade |
| `tools/reporting/models.py` | `ComparisonReport`: `new_issues: List`, `resolved_issues: List`, `persistent_issues: List`, `delta_by_category: dict`, `trend: str` ("melhorando"/"piorando"/"estável") |
| `tests/unit/test_temporal_comparator.py` | Mínimo 10 testes |

## Arquivos existentes a modificar

| Arquivo | O que muda |
|---------|-----------|
| `agents/reporter.py` | `build_report_data_node` consulta `dashboard.database.get_last_run(project_name)` e chama `temporal_comparator.compare()` se execução anterior existir |
| `dashboard/database.py` | `get_last_run(project_name) -> RunRecord | None` — retorna execução anterior mais recente do mesmo projeto |
| `templates/report.html.j2` | Seção "Evolução" com delta por categoria, badges "novo"/"resolvido"/"persistente" por issue |
| `dashboard/app.py` | Rota `GET /api/runs/{id}/compare/{prev_id}` retorna JSON de comparação |

## Fluxo de dados

```python
# tools/reporting/temporal_comparator.py

@dataclass
class ComparisonReport:
    new_issues: List[dict]          # issues na execução atual que não existiam antes
    resolved_issues: List[dict]     # issues da execução anterior que não aparecem mais
    persistent_issues: List[dict]   # issues presentes em ambas as execuções
    delta_by_category: dict         # {"N+1 Query": +1, "Cache Ausente": -2}
    total_delta: int                # positivo = piorou, negativo = melhorou
    trend: str                      # "melhorando" | "piorando" | "estável"

def compare_runs(current_issues: List[dict], previous_issues: List[dict]) -> ComparisonReport:
    # Identidade de issue: (category, file_path, line) — não usa UUID
    current_keys = {(i["category"], i["file_path"], i["line"]) for i in current_issues}
    previous_keys = {(i["category"], i["file_path"], i["line"]) for i in previous_issues}

    new_keys = current_keys - previous_keys
    resolved_keys = previous_keys - current_keys
    persistent_keys = current_keys & previous_keys

    delta = len(current_issues) - len(previous_issues)
    trend = "melhorando" if delta < 0 else ("piorando" if delta > 0 else "estável")

    return ComparisonReport(
        new_issues=[i for i in current_issues if (i["category"], i["file_path"], i["line"]) in new_keys],
        resolved_issues=[i for i in previous_issues if (i["category"], i["file_path"], i["line"]) in resolved_keys],
        persistent_issues=[i for i in current_issues if (i["category"], i["file_path"], i["line"]) in persistent_keys],
        delta_by_category=_delta_by_category(current_issues, previous_issues),
        total_delta=delta,
        trend=trend,
    )
```

## Decisões técnicas

- **Identidade de issue**: `(category, file_path, line)` — aceita falsos positivos quando código muda de linha; alternativa futura usa hash do bloco de código
- **Primeira execução**: sem execução anterior → seção de comparação não aparece no relatório
- **Dependência de `spec-web-dashboard.md`**: requer banco SQLite com histórico; deve ser implementado após o dashboard
- **Dados serializados**: issues são salvos como JSON no campo `issues_json TEXT` do SQLite para reconstrução posterior

## Critérios de aceitação

- [ ] Segunda execução do mesmo projeto exibe seção "Evolução" no relatório
- [ ] Issues novos são marcados com badge "novo"
- [ ] Issues resolvidos aparecem na lista de "Resolvidos desde última análise"
- [ ] Issues persistentes são marcados com badge "persistente"
- [ ] `trend` é "melhorando" quando total de issues diminuiu
- [ ] Primeira execução não exibe seção de comparação (gracioso)
- [ ] `GET /api/runs/{id}/compare/{prev_id}` retorna JSON de comparação
- [ ] `pytest tests/unit/test_temporal_comparator.py` passa

## Testes

```python
# tests/unit/test_temporal_comparator.py
# - test_new_issue_detected_when_not_in_previous
# - test_resolved_issue_detected_when_not_in_current
# - test_persistent_issue_in_both_runs
# - test_trend_melhorando_when_delta_negative
# - test_trend_piorando_when_delta_positive
# - test_trend_estavel_when_no_change
# - test_delta_by_category_calculated_correctly
# - test_empty_previous_all_issues_are_new
# - test_empty_current_all_issues_are_resolved
# - test_identity_based_on_category_file_line
```
