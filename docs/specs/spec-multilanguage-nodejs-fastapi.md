# Spec: Multi-linguagem — Node.js/Express e Python/FastAPI

## Status
Fase 4 — [ ] Pendente

## Contexto
O SentinelCode foi projetado exclusivamente para Java/Spring Boot. No entanto, a
arquitetura LangGraph com AgentState genérico e ferramentas modulares permite
extensão para outras linguagens sem reescrever os agentes principais.

Node.js/Express e Python/FastAPI são as stacks mais comuns fora do ecossistema Java
em ambientes que também usam K8s/Terraform. Adicionar suporte a essas linguagens
multiplica o público-alvo do SentinelCode significativamente.

## Objetivo
Detectar padrões de performance comuns em projetos Node.js/Express e Python/FastAPI,
mantendo o mesmo pipeline de agentes e a mesma estrutura de relatório.

## Escopo

### Inclui
**Node.js/Express:**
- Detecção de queries sem índice (Mongoose `.find({})` sem `.limit()`)
- Callbacks síncronos bloqueantes (`fs.readFileSync`, `JSON.parse` em loop)
- Ausência de cache em rotas GET
- `require()` dentro de loops ou funções hot-path

**Python/FastAPI:**
- Queries ORM sem paginação (SQLAlchemy `.all()` sem `.limit()`)
- Endpoints síncronos que deveriam ser `async def`
- Ausência de cache em endpoints `@app.get`
- `time.sleep()` em handlers

### Não inclui
- Análise de projetos Django ou Flask (somente FastAPI)
- Análise de frameworks Node.js além de Express (sem Next.js, NestJS)
- Fixes automáticos (detecta e reporta; fixes requerem LLM — ver `spec-llm-fixes`)
- Suporte simultâneo a múltiplas linguagens no mesmo projeto

## Arquitetura

Introdução do conceito de **Analyzer Strategy** no Code Analyzer:
selecionado automaticamente pelo `project_type` no `AgentState`.

```
project_type = "java-spring"  → JavaAnalyzerStrategy (atual)
project_type = "nodejs-express" → NodejsAnalyzerStrategy (novo)
project_type = "python-fastapi" → FastAPIAnalyzerStrategy (novo)
```

Cada strategy implementa a interface:
- `read_source_files(path) -> List[dict]`
- `detect_issues(files) -> List[Issue]`

O LLM enriquecimento (`enrich_with_llm_node`) é agnóstico de linguagem — usa o
`root_cause` e `evidence` do Issue para gerar contexto.

## Mudanças no AgentState (`models/state.py`)
`project_type: str` já existe. Nenhum novo campo necessário.

## Novos arquivos

| Arquivo | Responsabilidade |
|---------|-----------------|
| `tools/nodejs/file_reader.py` | `read_nodejs_files(path) -> List[dict]` — lê `.js`, `.ts`, `package.json`, `.env` |
| `tools/nodejs/issue_detectors.py` | `detect_missing_limit()`, `detect_sync_blocking()`, `detect_missing_cache_nodejs()`, `detect_require_in_loop()` |
| `tools/python/file_reader.py` | `read_python_files(path) -> List[dict]` — lê `.py`, `requirements.txt`, `pyproject.toml` |
| `tools/python/issue_detectors.py` | `detect_orm_missing_pagination()`, `detect_sync_endpoint()`, `detect_missing_cache_fastapi()`, `detect_time_sleep_in_handler()` |
| `tests/unit/test_nodejs_detectors.py` | Mínimo 12 testes |
| `tests/unit/test_python_detectors.py` | Mínimo 12 testes |

## Arquivos existentes a modificar

| Arquivo | O que muda |
|---------|-----------|
| `agents/code_analyzer.py` | `read_files_node` e `detect_issues_node` fazem dispatch por `state["project_type"]` |
| `main.py` | Valores aceitos para `--type`: `java-spring`, `nodejs-express`, `python-fastapi` |
| `agents/orchestrator.py` | Sem mudança de lógica (já usa `project_type` do estado) |

## Fluxo de dados

```python
# agents/code_analyzer.py — dispatch por project_type

def read_files_node(state: AgentState) -> dict:
    project_type = state["project_type"]
    project_path = state["project_path"]

    if project_type == "java-spring":
        files = read_java_files(project_path)
    elif project_type == "nodejs-express":
        files = read_nodejs_files(project_path)
    elif project_type == "python-fastapi":
        files = read_python_files(project_path)
    else:
        files = []

    return {"java_files": files, "messages": [f"[{project_type}] {len(files)} arquivos lidos"]}

def detect_issues_node(state: AgentState) -> dict:
    project_type = state["project_type"]
    files = state.get("java_files", [])  # campo compartilhado para todos os tipos

    issues = []
    if project_type == "java-spring":
        issues.extend(detect_n_plus_one(files))
        # ... detectores Java existentes
    elif project_type == "nodejs-express":
        issues.extend(detect_missing_limit(files))
        issues.extend(detect_sync_blocking(files))
    elif project_type == "python-fastapi":
        issues.extend(detect_orm_missing_pagination(files))
        issues.extend(detect_sync_endpoint(files))

    return {"issues": issues}
```

**Nota**: o campo `java_files` no `AgentState` é reutilizado para todos os
tipos de projeto (renomear para `source_files` seria ideal, mas requer
atualização de todos os agentes — deixar como melhoria futura).

## Decisões técnicas

- **Reutilização do campo `java_files`**: evitar mudança de breaking no AgentState; documentar claramente que contém arquivos de qualquer linguagem
- **Análise baseada em regex**: sem AST de JavaScript/Python na primeira versão (mais simples, menos preciso)
- **Extensão por `project_type`**: novo tipo de projeto não requer mudança nos agentes, somente em `file_reader` e `issue_detectors`
- **IaC continua igual**: análise de Terraform/K8s é agnóstica de linguagem da aplicação

## Critérios de aceitação

- [ ] `--type nodejs-express` lê arquivos `.js`/`.ts` e detecta issues Node.js
- [ ] `--type python-fastapi` lê arquivos `.py` e detecta issues FastAPI
- [ ] `--type java-spring` continua funcionando (regressão zero)
- [ ] `detect_orm_missing_pagination` detecta `.all()` sem `.limit()` em SQLAlchemy
- [ ] `detect_sync_endpoint` detecta `def` (síncrono) em vez de `async def` em FastAPI
- [ ] Relatório HTML exibe issues das novas linguagens com categoria correta
- [ ] `pytest tests/unit/test_nodejs_detectors.py tests/unit/test_python_detectors.py` passa

## Testes

```python
# tests/unit/test_nodejs_detectors.py
# - test_detect_mongoose_find_without_limit
# - test_mongoose_find_with_limit_no_issue
# - test_detect_fs_read_file_sync
# - test_detect_json_parse_in_loop
# - test_detect_require_in_function
# - test_require_at_top_level_no_issue
# - test_detect_missing_cache_on_get_route
# - test_multiple_issues_same_file
# - test_empty_file_no_crash
# - test_non_js_file_skipped
# - test_ts_file_detected
# - test_express_router_detected

# tests/unit/test_python_detectors.py
# - test_detect_sqlalchemy_all_without_limit
# - test_sqlalchemy_with_limit_no_issue
# - test_detect_sync_fastapi_endpoint
# - test_async_endpoint_no_issue
# - test_detect_time_sleep_in_handler
# - test_detect_missing_cache_on_get_endpoint
# - test_fastapi_with_cache_no_issue
# - test_multiple_issues_same_file
# - test_empty_file_no_crash
# - test_non_python_file_skipped
# - test_plain_function_not_confused_with_endpoint
# - test_async_sleep_no_issue
```
