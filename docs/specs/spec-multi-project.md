# Spec: Multi-projeto — Monorepos e Múltiplos Serviços em Paralelo

## Status
Fase 5 — [ ] Pendente

## Contexto
O SentinelCode analisa um único projeto por invocação. Em organizações com monorepos
(um repositório com múltiplos serviços) ou arquiteturas de microsserviços, é necessário
analisar dezenas de serviços de forma eficiente. Executar N instâncias do pipeline
sequencialmente pode demorar horas; executar em paralelo multiplica a eficiência.

## Objetivo
Suportar análise de múltiplos projetos (ou sub-diretórios de um monorepo) em paralelo,
com relatório consolidado e relatórios individuais por serviço.

## Escopo

### Inclui
- Flag `--multi` que aceita um diretório raiz e detecta automaticamente subprojetos Java/IaC
- Execução paralela via `asyncio` + `ThreadPoolExecutor` (o pipeline LangGraph é síncrono internamente)
- Relatório consolidado HTML com lista de serviços, issues totais e link para cada relatório individual
- Configuração de concorrência via `--workers N` (default: 4)
- Suporte a arquivo de manifesto `sentinel-projects.yaml` listando projetos explicitamente

### Não inclui
- Correlação de issues entre projetos (cada análise é independente)
- Execução distribuída em múltiplas máquinas
- Análise de dependências entre microsserviços

## Arquitetura

Novo entrypoint `multi_analyze()` em `main.py` que usa `ThreadPoolExecutor`
para executar `N` pipelines LangGraph em paralelo (cada um em thread separada,
já que LangGraph é síncrono).

```
main.py --multi ./services/
  → discover_projects(path) → [./services/auth, ./services/orders, ./services/catalog]
  → ThreadPoolExecutor(max_workers=4)
      → analyze(auth) em paralelo com analyze(orders) e analyze(catalog)
  → consolida resultados
  → gera consolidated_report.html
```

## Mudanças no AgentState (`models/state.py`)
Nenhuma. Cada projeto tem seu próprio AgentState isolado.

## Novos arquivos

| Arquivo | Responsabilidade |
|---------|-----------------|
| `tools/multi/project_discovery.py` | `discover_projects(root_path, manifest_path=None) -> List[ProjectConfig]` — detecta subprojetos por presença de `pom.xml`, `build.gradle`, `Chart.yaml` |
| `tools/multi/parallel_runner.py` | `run_parallel(projects: List[ProjectConfig], max_workers: int) -> List[ProjectResult]` — `ThreadPoolExecutor` wrapper |
| `tools/multi/consolidated_reporter.py` | `generate_consolidated_report(results: List[ProjectResult], output_dir: str) -> str` — HTML com visão agregada |
| `tests/unit/test_project_discovery.py` | Mínimo 8 testes |
| `tests/unit/test_parallel_runner.py` | Testes com mock de pipeline (mínimo 6 testes) |

## Arquivos existentes a modificar

| Arquivo | O que muda |
|---------|-----------|
| `main.py` | Subcomando `multi` (ou flag `--multi PATH`) que chama `parallel_runner.run_parallel()` |
| `agents/reporter.py` | `render_report_node` aceita `output_filename` customizado para evitar colisão de nomes entre projetos |

## Fluxo de dados

```python
# tools/multi/project_discovery.py

@dataclass
class ProjectConfig:
    name: str
    path: str
    project_type: str  # "java-spring", "nodejs-express", etc.

def discover_projects(root_path: str) -> List[ProjectConfig]:
    projects = []
    for entry in Path(root_path).iterdir():
        if not entry.is_dir():
            continue
        if (entry / "pom.xml").exists():
            projects.append(ProjectConfig(entry.name, str(entry), "java-spring"))
        elif (entry / "build.gradle").exists():
            projects.append(ProjectConfig(entry.name, str(entry), "java-spring"))
        elif (entry / "package.json").exists():
            projects.append(ProjectConfig(entry.name, str(entry), "nodejs-express"))
    return projects

# tools/multi/parallel_runner.py

@dataclass
class ProjectResult:
    project: ProjectConfig
    issues_count: int
    gaps_count: int
    fixes_count: int
    report_path: str
    error: str | None = None
    duration_seconds: float = 0.0

def run_parallel(projects: List[ProjectConfig], max_workers: int = 4) -> List[ProjectResult]:
    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_analyze_project, p): p for p in projects}
        for future in as_completed(futures):
            project = futures[future]
            try:
                result = future.result(timeout=300)
                results.append(result)
            except Exception as e:
                results.append(ProjectResult(project=project, ..., error=str(e)))
    return results
```

## Decisões técnicas

- **Threads, não processos**: LangGraph usa objetos Python in-memory; `multiprocessing` requer serialização; `ThreadPool` é suficiente para I/O-bound (leitura de arquivos + chamadas LLM via HTTP)
- **GIL não é problema**: as chamadas LLM são I/O bound (aguardam resposta da API); o GIL é liberado durante I/O
- **Rate limiting OpenAI**: com 4 workers simultâneos e projetos grandes, pode atingir rate limit; `--workers 2` é recomendado para conta free
- **Isolamento de estado**: cada projeto tem `AgentState` independente — sem compartilhamento de memória entre análises
- **Falha isolada**: erro em um projeto não cancela os demais; `ProjectResult.error` captura a exceção
- **`sentinel-projects.yaml`**: permite configurar explicitamente quais subdiretórios analisar e com quais flags individuais

```yaml
# sentinel-projects.yaml (opcional)
projects:
  - name: auth-service
    path: ./services/auth
    type: java-spring
    dry_run: false
  - name: api-gateway
    path: ./services/gateway
    type: nodejs-express
    dry_run: true
```

## Critérios de aceitação

- [ ] `python main.py multi --path ./monorepo` detecta e analisa todos os subprojetos Java
- [ ] Análise de N projetos é executada em paralelo com `--workers N`
- [ ] Relatório consolidado lista todos os projetos com nº de issues e link individual
- [ ] Falha em um projeto não cancela análise dos demais
- [ ] `sentinel-projects.yaml` sobrepõe a descoberta automática
- [ ] Relatórios individuais são gerados em `outputs/<project-name>/`
- [ ] `pytest tests/unit/test_project_discovery.py` passa

## Testes

```python
# tests/unit/test_project_discovery.py
# - test_discover_maven_project
# - test_discover_gradle_project
# - test_discover_nodejs_project
# - test_ignore_non_project_directories
# - test_monorepo_with_multiple_services
# - test_manifest_overrides_discovery
# - test_empty_directory_returns_empty_list
# - test_nested_monorepo_not_double_counted

# tests/unit/test_parallel_runner.py
# - test_runs_projects_in_parallel (mock _analyze_project)
# - test_respects_max_workers_limit
# - test_failed_project_captured_as_error
# - test_all_results_returned_even_on_partial_failure
# - test_result_contains_correct_project_reference
# - test_timeout_per_project_respected
```
