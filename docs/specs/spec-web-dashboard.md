# Spec: Interface Web com Dashboard de Relatórios Históricos

## Status
Fase 5 — [ ] Pendente

## Contexto
Hoje o SentinelCode gera relatórios HTML/PDF em `outputs/` que são abertos manualmente
no navegador. Sem persistência histórica, é impossível comparar execuções ao longo do
tempo ou compartilhar resultados com o time sem enviar arquivos. Um dashboard web
transforma o SentinelCode de uma ferramenta CLI local em uma plataforma de observabilidade
de qualidade de código.

## Objetivo
Servidor web local (ou hospedável) que lista todas as execuções passadas, exibe o
relatório de cada uma, e oferece visão consolidada de issues recorrentes por projeto.

## Escopo

### Inclui
- Servidor web leve em Python (FastAPI) servindo os relatórios existentes
- Banco de dados SQLite local para persistência de metadados de execuções
- Página de listagem: execuções ordenadas por data, com filtros por projeto e severidade
- Página de detalhe: relatório HTML embutido (iframe ou reprocessado)
- API REST para integração com CI/CD (ver `spec-cicd-integration.md`)
- Comando CLI `sentinel-code serve` para iniciar o dashboard

### Não inclui
- Autenticação/autorização (dashboard local, sem exposição à internet)
- Banco de dados externo (somente SQLite)
- Frontend em React/Vue (Jinja2 + Alpine.js para interatividade mínima)
- Execução de análise pelo dashboard (somente visualização)

## Arquitetura

Novo subcomando `serve` no CLI (Typer). Servidor FastAPI independente do pipeline
LangGraph. O pipeline existente salva metadados em SQLite ao término; o dashboard
lê esse banco.

```
main.py
  ├── analyze (existente) → gera relatório + salva metadados no SQLite
  └── serve (novo) → inicia FastAPI na porta 8501

dashboard/
  ├── app.py              # FastAPI app
  ├── database.py         # SQLite via SQLModel/SQLite3
  ├── models.py           # RunRecord dataclass
  └── templates/
      ├── index.html      # Lista de execuções
      └── run_detail.html # Detalhe de uma execução
```

## Mudanças no AgentState (`models/state.py`)
Nenhuma mudança no AgentState. Metadados são salvos fora do pipeline.

## Novos arquivos

| Arquivo | Responsabilidade |
|---------|-----------------|
| `dashboard/app.py` | FastAPI app com rotas: `GET /` (lista), `GET /runs/{id}` (detalhe), `GET /api/runs` (JSON) |
| `dashboard/database.py` | `save_run(metadata)`, `list_runs(project, limit)`, `get_run(id)` usando SQLite3 |
| `dashboard/models.py` | `RunRecord`: id, project_path, project_name, timestamp, issues_count, gaps_count, fixes_count, report_path, duration_seconds |
| `dashboard/templates/index.html` | Lista de execuções com filtros e métricas agregadas |
| `dashboard/templates/run_detail.html` | Iframe com relatório HTML + metadados laterais |
| `tests/unit/test_dashboard_db.py` | Testes do database layer (mínimo 8 testes) |

## Arquivos existentes a modificar

| Arquivo | O que muda |
|---------|-----------|
| `main.py` | Adicionar subcomando `serve` e chamar `dashboard.database.save_run()` ao término de `analyze` |
| `agents/reporter.py` | Nó `render_report` retorna metadados estruturados (issues_count, gaps_count, duration) além do path do relatório |
| `models/state.py` | Adicionar `run_metadata: dict` (opcional) para capturar metadados da execução |
| `requirements.txt` | Adicionar `fastapi`, `uvicorn`, `jinja2` (jinja2 já pode ser dependência) |

## Fluxo de dados

```
python main.py --path ./meu-projeto
  → pipeline executa
  → render_report() → outputs/report_meu-projeto_20260311_143022.html
  → save_run({
      project_name: "meu-projeto",
      timestamp: "2026-03-11T14:30:22",
      issues_count: 5,
      gaps_count: 2,
      fixes_count: 3,
      report_path: "outputs/report_meu-projeto_20260311_143022.html",
      duration_seconds: 47,
    })

python main.py serve
  → uvicorn dashboard.app:app --port 8501
  → GET http://localhost:8501/ → lista de execuções
  → GET http://localhost:8501/runs/1 → relatório embutido
```

## Decisões técnicas

- **SQLite**: sem dependência de servidor de banco; arquivo em `outputs/.sentinel.db`
- **FastAPI + Uvicorn**: mesma stack do SentinelCode Python; levantamento em < 1s
- **Iframe para relatórios**: reutiliza os HTMLs existentes sem reprocessamento
- **Porta padrão**: 8501 (evitar conflito com 8080/8000 comuns)
- **Sem hot-reload automático**: usuário recarrega a página para ver novas execuções

## Critérios de aceitação

- [ ] `python main.py serve` inicia servidor em `http://localhost:8501`
- [ ] Após execução de análise, o run aparece na lista do dashboard
- [ ] Lista exibe: data, projeto, nº de issues, nº de gaps, nº de fixes
- [ ] Click em uma execução abre o relatório HTML
- [ ] `GET /api/runs` retorna JSON com lista de execuções (para CI/CD)
- [ ] Primeiro uso cria o banco SQLite automaticamente
- [ ] `pytest tests/unit/test_dashboard_db.py` passa

## Testes

```python
# tests/unit/test_dashboard_db.py
# - test_save_run_creates_record
# - test_list_runs_returns_ordered_by_date
# - test_get_run_by_id
# - test_list_runs_filter_by_project
# - test_database_created_on_first_use
# - test_save_run_idempotent_on_same_path_and_timestamp
# - test_list_runs_empty_returns_empty_list
# - test_run_record_fields_match_schema
```
