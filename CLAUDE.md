# CLAUDE.md — SentinelCode

Arquivo de contexto persistente. Leia este arquivo no início de cada sessão
antes de implementar qualquer coisa no projeto.

---

## 🎯 O que é o SentinelCode

Sistema multi-agente em Python que analisa, diagnostica e corrige
automaticamente problemas de performance em:
- Aplicações Java/Spring Boot (código-fonte)
- Infraestrutura como Código (Terraform, K8s)

Gera relatório HTML com causa raiz, severidade, diffs antes/depois,
testes automatizados e métricas de ganho de performance.

---

## 🏗️ Arquitetura

### Framework
**LangGraph** — grafos de estado com fluxos condicionais e ciclos.
Cada agente é um `StateGraph` com nós independentes e testáveis.

### Estado compartilhado
`models/state.py` — `AgentState` (TypedDict) circula entre todos os agentes.
Campos com `Annotated[List, operator.add]` são acumulativos entre nós.

**REGRA CRÍTICA:** campos temporários entre nós NUNCA podem ter prefixo `_`.
O LangGraph não persiste campos desconhecidos no TypedDict entre nós.
Todo campo que precisa ser passado entre nós deve estar declarado no AgentState.

### LLM
- Principal: `gpt-4o` via `langchain-openai`
- Temperature: sempre `0` (respostas determinísticas)
- Configurado em `config.py` via `pydantic-settings` lendo `.env`

---

## 📁 Estrutura de Diretórios

```
sentinel-code/
├── main.py                      # CLI entry point (Typer)
├── config.py                    # Settings via pydantic-settings
├── CLAUDE.md                    # Este arquivo
│
├── agents/
│   ├── orchestrator.py          # Pipeline completo (flags: dry_run, with_iac, with_benchmark, with_tests)
│   ├── code_analyzer.py         # Analisa Java/Spring Boot
│   ├── fix_agent.py             # Aplica correções no código
│   ├── reporter.py              # Gera relatório HTML
│   ├── iac_analyzer.py          # Analisa Terraform/K8s
│   ├── iac_patcher.py           # Corrige IaC
│   ├── benchmark.py             # Locust antes/depois
│   └── test_agent.py            # Gera testes funcionais
│
├── models/
│   ├── state.py                 # AgentState — estado global
│   ├── issue.py                 # Issue, Severity, IssueCategory
│   └── infra_gap.py             # InfraGap, InfraGapCategory
│
├── tools/
│   ├── java/
│   │   ├── file_reader.py       # Lê .java e configs
│   │   ├── issue_detectors.py   # Detectores estáticos
│   │   └── code_patcher.py      # Aplica patches em arquivos
│   ├── iac/
│   │   ├── file_reader.py       # Lê .tf, .yaml, .yml
│   │   ├── gap_detectors.py     # Detectores de gaps de infra
│   │   └── iac_patcher.py       # Aplica patches em IaC
│   ├── benchmark/
│   │   ├── models.py            # BenchmarkReport dataclass
│   │   ├── comparator.py        # calculate_delta, validate_slas, compare_benchmarks
│   │   ├── script_generator.py  # Gera script Locust
│   │   └── runner.py            # check_url_available, run_benchmark
│   └── test_gen/
│       ├── planner.py           # plan_tests, extract_endpoints
│       └── code_generator.py    # generate_test_code, generate_conftest
│
├── specs/                       # Spec Driven Development
│   ├── agents/
│   │   ├── iac_analyzer.md
│   │   ├── iac_patcher.md
│   │   ├── benchmark.md
│   │   └── test_agent.md
│   └── tools/
│       └── detectors.md
│
├── tests/unit/
│   ├── test_iac_detectors.py    # 24 testes
│   ├── test_iac_file_reader.py  # 16 testes
│   ├── test_iac_analyzer_agent.py # 10 testes
│   ├── test_iac_patcher.py      # 17 testes
│   ├── test_benchmark.py        # 22 testes
│   └── test_test_agent.py       # 20 testes (+ ~15 Fase 1)
│
├── sample_project/              # Projeto Java de exemplo para testes
└── outputs/                     # Relatórios gerados (gitignored)
```

---

## ✅ Status de implementação

### Agentes
| Agente | Arquivo | Nós | Status |
|--------|---------|-----|--------|
| Code Analyzer | `agents/code_analyzer.py` | read_files → detect_issues → enrich_with_llm | ✅ |
| Fix Agent | `agents/fix_agent.py` | plan_fixes → apply_fixes → validate_fixes | ✅ |
| Reporter | `agents/reporter.py` | build_report_data → render_report | ✅ |
| IaC Analyzer | `agents/iac_analyzer.py` | read_iac_files → detect_infra_gaps → enrich_iac_with_llm | ✅ |
| IaC Patcher | `agents/iac_patcher.py` | plan_iac_patches → apply_iac_patches → validate_iac_patches | ✅ |
| Benchmark Agent | `agents/benchmark.py` | setup_benchmark → run_before → run_after → compare_benchmarks | ✅ |
| Test Agent | `agents/test_agent.py` | plan_tests → generate_tests → run_tests | ✅ |
| Orchestrator | `agents/orchestrator.py` | pipeline dinâmico com 4 flags | ✅ |

### Detectores Java (`tools/java/issue_detectors.py`)
| Detector | Método | Status |
|----------|--------|--------|
| N+1 Query | AST + fallback textual | ✅ |
| Cache Ausente | Heurística @GetMapping | ✅ |
| Connection Pool | Parse application.properties/yml | ✅ |

### Detectores IaC (`tools/iac/gap_detectors.py`)
| Detector | Recurso | Status |
|----------|---------|--------|
| Missing Autoscaling | ECS / K8s Deployment | ✅ |
| Single AZ | RDS multi_az=false | ✅ |
| Undersized Instance | instance_type vs max_rps | ✅ |

### Estratégias de patch IaC (`tools/iac/iac_patcher.py`)
| Estratégia | Uso | Status |
|------------|-----|--------|
| append_block | Adiciona bloco HCL (ECS autoscaling) | ✅ |
| modify_attribute | Altera atributo em-linha (multi_az) | ✅ |
| append_file | Cria novo arquivo (K8s HPA yaml) | ✅ |

---

## 🔄 Pipeline completo

```
read_files → detect_issues → enrich_with_llm
  → [plan_fixes → apply_fixes → validate_fixes]        # se não dry_run
  → [read_iac_files → detect_infra_gaps                # se with_iac
     → enrich_iac_with_llm
     → plan_iac_patches → apply_iac_patches             # se não dry_run
     → validate_iac_patches]
  → [setup_benchmark → run_before → run_after          # se with_benchmark
     → compare_benchmarks]
  → [plan_tests → generate_tests → run_tests]          # se with_tests e não dry_run
  → build_report_data → render_report → END
```

Flags do `build_full_pipeline()`:
- `dry_run=False` — pula Fix Agent, IaC Patcher e Test Agent
- `with_iac=True` — inclui IaC Analyzer + Patcher
- `with_benchmark=False` — inclui Benchmark Agent (requer target_url)
- `with_tests=True` — inclui Test Agent

---

## 📐 Decisões técnicas e o porquê

### Fixes cirúrgicos vs LLM
**Regra:** usar LLM apenas quando a correção é não-determinística.
- `@Cacheable` → inserção de 1 linha → sem LLM
- HikariCP config → configuração padrão conhecida → sem LLM
- N+1 refactor → depende do código específico → com LLM

**Motivo:** LLM gera código com imports extras, reescreve indentação,
adiciona comentários — tudo isso quebra o patch por substituição de string.

### Validação de fixes Java
**Regra:** comparar balanço de chaves antes vs depois do patch.
Se `brace_balance(after) >= brace_balance(before)` → fix válido.

**Motivo:** `javalang.parse` é muito estrito e falha em arquivos
Java incompletos (sem package, sem imports).

### python-hcl2 retorna List[dict]
**Bug recorrente:** `python-hcl2` retorna `resource` como `List[dict]`, não `dict`.
`_collect_all_resources()` em `tools/iac/gap_detectors.py` trata ambos os formatos.

### IaC Patcher — formato do resource_name
**Bug recorrente:** `_resolve_strategy()` deve tratar dois formatos:
- `"aws_ecs_service.api"` → split por `.`
- `"Deployment/api"` → split por `/`

### Campos temporários no AgentState
**REGRA CRÍTICA:** NUNCA passar dados entre nós via campos não declarados.
Exemplo de bug: `_test_plan` foi perdido entre `plan_tests_node` e `generate_tests_node`.
Solução: declarar `test_plan: List[dict]` no AgentState.

---

## 🗺️ Roadmap de Implementação

### Fase 1 — MVP ✅ CONCLUÍDA
- [x] Setup do projeto, config, CLI básica
- [x] Code Analyzer Agent (N+1, missing cache, connection pool)
- [x] Fix Agent (fixes cirúrgicos + validação + rollback automático)
- [x] Reporter Agent (relatório HTML com diffs visuais antes/depois)
- [x] Orchestrator (pipeline completo integrado)

### Fase 2 — Core ✅ CONCLUÍDA
- [x] IaC Analyzer Agent (Terraform — python-hcl2)
- [x] IaC Patcher Agent (altera .tf com justificativa)
- [x] Benchmark Agent (Locust integrado programaticamente)
- [x] Test Agent (geração de testes funcionais)

### Fase 3 — Expansão
- [ ] Suporte a K8s manifests
- [ ] Suporte a CloudFormation
- [ ] Simulação de custo AWS
- [ ] Relatório PDF executivo
- [ ] LangSmith observabilidade completa
- [ ] Mais detectores Java (Missing Index, Lazy Loading, Thread Blocking)

---

## 📊 Suite de testes (104 testes passando)

```
tests/unit/test_iac_detectors.py       → 16 testes  ✅
tests/unit/test_iac_file_reader.py     → 16 testes  ✅
tests/unit/test_iac_analyzer_agent.py  → 10 testes  ✅
tests/unit/test_iac_patcher.py         → 17 testes  ✅
tests/unit/test_benchmark.py           → 22 testes  ✅
tests/unit/test_test_agent.py          → 20 testes  ✅
+ testes Fase 1                        →  3 testes  ✅
─────────────────────────────────────────────────────
Total                                  → 104 testes ✅
```

---

## ⚙️ Como rodar

```bash
# Ambiente
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt

# Pipeline completo
python main.py --path .\sample_project\

# Só análise, sem fixes
python main.py --path .\sample_project\ --dry-run

# Sem análise de IaC
python main.py --path .\sample_project\ --no-iac

# Com benchmark + NFRs
python main.py --path .\sample_project\ --benchmark --nfr '{"target_url":"http://localhost:8080","p99_latency_ms":200}'

# Rodar todos os testes
pytest tests/ -v
```

---

## 🔐 Variáveis de ambiente (.env)

```env
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o
LANGCHAIN_TRACING_V2=false
LANGCHAIN_PROJECT=sentinel-code
```

**Atenção Windows:** se `OPENAI_API_KEY` estiver nas variáveis de sistema
do Windows, ela tem prioridade sobre o `.env`. Remover com:
```powershell
[System.Environment]::SetEnvironmentVariable("OPENAI_API_KEY", $null, "User")
[System.Environment]::SetEnvironmentVariable("OPENAI_API_KEY", $null, "Machine")
```