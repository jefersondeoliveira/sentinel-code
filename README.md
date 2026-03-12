# SentinelCode

Sistema multi-agente em Python que analisa, diagnostica e corrige automaticamente problemas de performance em aplicações Java/Spring Boot e infraestrutura como código (IaC).

## O que ele faz

Dado um projeto Java/Spring Boot ou Terraform/K8s, o SentinelCode:

1. **Analisa** o código e detecta problemas de performance (N+1, paginação, lazy loading, thread blocking, índices ausentes, pool subdimensionado, etc.)
2. **Analisa** a infraestrutura (ECS autoscaling, RDS multi-AZ, K8s resource limits, health probes)
3. **Corrige** automaticamente os problemas detectados (fixes cirúrgicos com backup e rollback)
4. **Gera testes** funcionais para os endpoints corrigidos
5. **Executa benchmarks** antes/depois com Locust (opcional)
6. **Gera relatório** HTML (ou PDF) com causa raiz, diffs antes/depois e métricas de ganho

## Pré-requisitos

- Python 3.11+
- Java/Maven (para rodar testes do projeto analisado, opcional)
- Chave de API OpenAI

## Instalação

```bash
git clone https://github.com/jefersondeoliveira/sentinel-code
cd sentinel-code

python -m venv .venv
.venv\Scripts\activate      # Windows
source .venv/bin/activate   # Linux/macOS

pip install -r requirements.txt
```

Crie o arquivo `.env`:

```env
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o

# Opcional — observabilidade via LangSmith
LANGCHAIN_TRACING_V2=false
LANGCHAIN_PROJECT=sentinel-code
LANGCHAIN_API_KEY=ls__...
```

## Uso

```bash
# Análise completa com fixes + testes
python main.py --path ./meu-projeto

# Só análise, sem modificar arquivos
python main.py --path ./meu-projeto --dry-run

# Sem análise de IaC
python main.py --path ./meu-projeto --no-iac

# Com benchmark de carga (requer app rodando)
python main.py --path ./meu-projeto --benchmark \
  --nfr '{"target_url":"http://localhost:8080","p99_latency_ms":200}'

# Gerar relatório em PDF (requer weasyprint instalado)
python main.py --path ./meu-projeto --pdf

# Testar com o projeto de exemplo
python main.py --path ./sample_project --dry-run
```

## Arquitetura

O pipeline é orquestrado com **LangGraph** e composto por 7 agentes independentes:

```
read_files → detect_issues → enrich_with_llm
  → [plan_fixes → apply_fixes → validate_fixes]
  → [read_iac_files → detect_infra_gaps → enrich_iac_with_llm
     → plan_iac_patches → apply_iac_patches → validate_iac_patches]
  → [setup_benchmark → run_before → run_after → compare_benchmarks]
  → [plan_tests → generate_tests → run_tests]
  → build_report_data → render_report → END
```

| Agente | Responsabilidade |
|--------|-----------------|
| Code Analyzer | Detecta issues de performance em Java/Spring Boot |
| Fix Agent | Aplica correções cirúrgicas com rollback automático |
| IaC Analyzer | Detecta gaps em Terraform e manifests K8s |
| IaC Patcher | Aplica correções em arquivos `.tf` e `.yaml` |
| Benchmark Agent | Executa testes de carga Locust antes/depois |
| Test Agent | Gera testes funcionais para os endpoints |
| Reporter | Consolida tudo em relatório HTML/PDF |

## Detectores

### Java (`tools/java/issue_detectors.py`)

| Detector | Severidade | O que detecta |
|----------|-----------|---------------|
| N+1 Query | CRÍTICO | Loop com chamadas a repositório JPA |
| Cache Ausente | ALTO | `@GetMapping` sem `@Cacheable` em dados estáticos |
| Connection Pool | ALTO | HikariCP com pool-size < 15 ou ausente |
| Paginação | ALTO | `findAll()` / `List<T>` sem `Pageable` em `@Repository` |
| Lazy Loading | ALTO | `@OneToMany`/`@ManyToMany` sem `@JsonManagedReference` |
| Thread Blocking | CRÍTICO | `Thread.sleep`, `.get()`, `.block()`, `.join()` |
| Índice Ausente | ALTO | `findBy*` em repositório sem `@Index` na entidade |

### IaC (`tools/iac/gap_detectors.py`)

| Detector | Recurso | O que detecta |
|----------|---------|---------------|
| Missing Autoscaling | ECS / K8s Deployment | Ausência de Auto Scaling / HPA |
| Single AZ | RDS | `multi_az = false` |
| Undersized Instance | EC2/RDS | Instância subdimensionada para o RPS alvo |
| K8s Resource Limits | Deployment / StatefulSet | Containers sem `resources.requests/limits` |
| K8s Health Probes | Deployment / StatefulSet | Containers sem `livenessProbe`/`readinessProbe` |

## Estratégias de Patch IaC

| Estratégia | Uso |
|------------|-----|
| `append_block` | Adiciona novo bloco HCL (ex: ECS autoscaling target + policy) |
| `modify_attribute` | Altera atributo inline (ex: `multi_az = false → true`) |
| `append_file` | Cria novo arquivo (ex: `hpa-api.yaml` para K8s) |
| `modify_yaml` | Modifica YAML existente (ex: adiciona resources/probes a Deployment) |

## Testes

```bash
# Todos os testes
pytest tests/ -v

# Por módulo
pytest tests/unit/test_java_detectors.py -v
pytest tests/unit/test_k8s_detectors.py -v
pytest tests/unit/test_iac_patcher.py -v
```

**169 testes unitários** cobrindo detectores, patchers, benchmark e test agent.

## Exemplo de saída

```
📋 Issues Java Encontrados
┌───┬───────────┬───────────────────────┬──────────────────────────────┬───────┐
│ # │ Severidade │ Categoria            │ Arquivo                      │ Linha │
├───┼───────────┼───────────────────────┼──────────────────────────────┼───────┤
│ 1 │ CRÍTICO   │ N+1 Query             │ src/.../OrderService.java    │ 142   │
│ 2 │ ALTO      │ Cache Ausente         │ src/.../ProductController.java│ 28   │
│ 3 │ ALTO      │ Paginação             │ src/.../UserRepository.java  │ 15    │
│ 4 │ ALTO      │ Índice Ausente        │ src/.../UserRepository.java  │ 18    │
│ 5 │ CRÍTICO   │ Thread Bloqueante     │ src/.../UserService.java     │ 34    │
└───┴───────────┴───────────────────────┴──────────────────────────────┴───────┘

🏗️ Gaps de Infraestrutura
┌───┬───────────────────────┬──────────────────────┬───────────┐
│ # │ Categoria             │ Recurso              │ Severidade│
├───┼───────────────────────┼──────────────────────┼───────────┤
│ 1 │ K8s Resource Limits   │ Deployment/api       │ ALTO      │
│ 2 │ K8s Health Check      │ Deployment/api       │ ALTO      │
└───┴───────────────────────┴──────────────────────┴───────────┘

  📄 Relatório: outputs/report_sample_project_20260311_143022.html
  💡 Abra o arquivo HTML no seu navegador
```

## Variáveis de ambiente

| Variável | Obrigatória | Descrição |
|----------|-------------|-----------|
| `OPENAI_API_KEY` | Sim | Chave da API OpenAI |
| `OPENAI_MODEL` | Não (padrão: `gpt-4o`) | Modelo a usar |
| `LANGCHAIN_TRACING_V2` | Não | Habilita tracing LangSmith |
| `LANGCHAIN_API_KEY` | Não | Chave LangSmith |
| `LANGCHAIN_PROJECT` | Não | Nome do projeto no LangSmith |

> **Atenção no Windows:** se `OPENAI_API_KEY` estiver nas variáveis de sistema, ela tem prioridade sobre o `.env`.

## PDF Export

Para exportar o relatório em PDF:

```bash
pip install weasyprint
python main.py --path ./meu-projeto --pdf
```

Dependências de sistema necessárias:
- **Windows:** [GTK3 runtime](https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer)
- **Linux:** `apt install libpango-1.0-0 libharfbuzz0b libpangoft2-1.0-0`
- **macOS:** `brew install pango`

Se o weasyprint não estiver instalado, o pipeline gera HTML automaticamente como fallback.

## Estrutura do projeto

```
sentinel-code/
├── main.py                 # CLI (Typer)
├── config.py               # Settings (pydantic-settings)
├── agents/                 # Agentes LangGraph
│   ├── orchestrator.py
│   ├── code_analyzer.py
│   ├── fix_agent.py
│   ├── iac_analyzer.py
│   ├── iac_patcher.py
│   ├── benchmark.py
│   ├── test_agent.py
│   └── reporter.py
├── tools/
│   ├── java/               # Detectores e patcher Java
│   ├── iac/                # Detectores e patcher IaC
│   ├── benchmark/          # Locust runner e comparador
│   ├── test_gen/           # Gerador de testes funcionais
│   └── observability/      # LangSmith tracer
├── models/                 # AgentState, Issue, InfraGap
├── templates/              # Template Jinja2 do relatório HTML
├── sample_project/         # Projeto Java de exemplo para testes
├── tests/unit/             # 169 testes unitários
└── outputs/                # Relatórios gerados (gitignored)
```
