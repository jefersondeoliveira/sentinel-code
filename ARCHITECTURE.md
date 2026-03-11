# 🤖 SentinelCode — Agentic Performance & Infrastructure Analyzer

## Visão Geral

Sistema multi-agente em Python que analisa, diagnostica e corrige automaticamente problemas de performance em aplicações Java/Spring Boot e infraestrutura como código (IaC), com benchmarks antes/depois, relatórios de severidade e geração de testes.

---

## 🧠 Framework Escolhido: LangGraph

### Por quê LangGraph e não CrewAI ou LangChain simples?

| Critério | LangGraph | CrewAI | LangChain Chains |
|---|---|---|---|
| Controle de fluxo condicional | ✅ Nativo (grafos) | ⚠️ Limitado | ❌ Manual |
| Estado compartilhado entre agentes | ✅ StateGraph | ⚠️ Parcial | ❌ Não |
| Ciclos / retry logic | ✅ Nativo | ❌ Não | ❌ Não |
| Supervisão de agentes | ✅ Supervisor pattern | ✅ | ❌ |
| Adequado para prod | ✅ | ⚠️ | ⚠️ |
| Debugging / observabilidade | ✅ LangSmith | ⚠️ | ⚠️ |

**LangGraph** oferece grafos de estado que permitem fluxos como: analisar → decidir → corrigir → testar → se falhou → reanalisar. Isso é essencial para um produto de qualidade de produção.

---

## 🏗️ Arquitetura de Agentes

```
┌─────────────────────────────────────────────────────────┐
│                    ORCHESTRATOR AGENT                   │
│              (LangGraph Supervisor Node)                │
│     Recebe input → distribui tarefas → consolida        │
└──────┬──────────┬──────────┬──────────┬────────────────┘
       │          │          │          │
       ▼          ▼          ▼          ▼
┌──────────┐ ┌────────┐ ┌────────┐ ┌──────────────┐
│   CODE   │ │  IAC   │ │ BENCH  │ │   REPORTER   │
│ ANALYZER │ │ANALYZER│ │ AGENT  │ │    AGENT     │
│  AGENT   │ │ AGENT  │ │        │ │              │
└────┬─────┘ └───┬────┘ └───┬────┘ └──────┬───────┘
     │           │          │             │
     ▼           ▼          ▼             ▼
┌──────────┐ ┌────────┐ ┌────────┐ ┌──────────────┐
│   FIX    │ │  IaC   │ │ TEST   │ │   DOCUMENT   │
│  AGENT   │ │PATCHER │ │ AGENT  │ │    AGENT     │
└──────────┘ └────────┘ └────────┘ └──────────────┘
```

### Agentes Detalhados

#### 1. 🎯 Orchestrator Agent
- **Responsabilidade:** Coordena todo o fluxo, decide qual agente acionar, agrega resultados
- **Tecnologia:** LangGraph `StateGraph` com nó supervisor
- **Input:** Path do projeto (Java ou IaC) + requisitos não funcionais (ex: "suporte 10k RPS, latência < 200ms")

#### 2. 🔍 Code Analyzer Agent
- **Responsabilidade:** Analisa código Java/Spring Boot e identifica problemas reais
- **Ferramentas (tools):**
  - `read_java_files` — lê todos os `.java` do projeto
  - `parse_pom_xml` — analisa dependências Maven/Gradle
  - `detect_n_plus_one` — detecta N+1 queries via padrão de código
  - `detect_missing_indexes` — analisa queries JPA/JPQL vs entidades
  - `detect_thread_blocking` — identifica chamadas bloqueantes em contextos reativos
  - `detect_missing_cache` — identifica endpoints sem cache em dados estáticos
  - `detect_connection_pool` — valida configuração de pool (HikariCP)
  - `detect_pagination_issues` — detecta `findAll()` sem paginação
  - `detect_serialization_issues` — lazy loading em serializações JSON
- **Output:** Lista estruturada de `Issue(category, severity, location, root_cause, evidence)`

#### 3. 🏗️ IaC Analyzer Agent
- **Responsabilidade:** Analisa Terraform (e outros) contra requisitos não funcionais
- **Ferramentas:**
  - `parse_terraform_hcl` — usa `python-hcl2` para parsear `.tf`
  - `parse_cloudformation_yaml` — suporte a CloudFormation
  - `parse_k8s_manifests` — suporte a Kubernetes YAML
  - `detect_undersized_instances` — valida tamanho de instâncias vs carga esperada
  - `detect_missing_autoscaling` — identifica ausência de ASG/HPA
  - `detect_single_az` — identifica falta de multi-AZ
  - `detect_missing_cdn` — identifica falta de CDN para assets estáticos
  - `simulate_cost` — estima custo mensal (AWS Pricing API)
  - `suggest_reserved_instances` — analisa oportunidade de Reserved vs On-demand
- **Output:** Lista de `InfraGap(resource, gap_type, severity, current_config, recommended_config, cost_impact)`

#### 4. ⚡ Benchmark Agent
- **Responsabilidade:** Executa testes de carga antes e depois das correções
- **Ferramentas:**
  - `run_locust_test` — executa Locust programaticamente
  - `run_k6_test` — alternativa com k6 via subprocess
  - `collect_jvm_metrics` — coleta métricas JVM via JMX/Actuator
  - `collect_db_metrics` — coleta slow queries, connections, throughput
  - `compare_benchmarks` — calcula delta % entre before/after
- **Output:** `BenchmarkReport(p50, p95, p99, rps, error_rate, before_vs_after)`

#### 5. 🛠️ Fix Agent
- **Responsabilidade:** Aplica as correções no código Java
- **Ferramentas:**
  - `apply_cache_annotation` — adiciona `@Cacheable`, configura Redis
  - `add_pagination` — refatora `findAll()` para `findAll(Pageable)`
  - `fix_n_plus_one` — reescreve queries com `JOIN FETCH` ou `@EntityGraph`
  - `add_connection_pool_config` — injeta configuração HikariCP otimizada
  - `add_async_annotation` — converte chamadas síncronas para `@Async`
  - `add_index_migration` — gera migration Flyway/Liquibase com índices
  - `generate_unit_tests` — gera testes JUnit para cada correção aplicada
- **Constraint:** Cada fix gera um diff claro (before/after) e é reversível

#### 6. 🏗️ IaC Patcher Agent
- **Responsabilidade:** Aplica alterações justificadas no código IaC
- **Ferramentas:**
  - `patch_terraform_resource` — modifica blocos HCL com justificativa inline
  - `add_autoscaling_group` — adiciona ASG ao Terraform
  - `add_hpa_manifest` — adiciona HorizontalPodAutoscaler ao K8s
  - `upgrade_instance_type` — ajusta tipo de instância com comparativo de custo
  - `add_elasticache` — provisiona Redis/Memcached para caching
- **Output:** Diffs dos arquivos `.tf` / `.yaml` + justificativa para cada mudança

#### 7. 🧪 Test Agent
- **Responsabilidade:** Gera e executa testes automatizados
- **Ferramentas:**
  - `generate_performance_tests` — cria scripts Locust baseados nos endpoints detectados
  - `generate_functional_tests` — cria testes de contrato com RestAssured ou TestContainers
  - `run_maven_tests` — executa `mvn test` e captura resultado
  - `validate_sla` — verifica se métricas atendem aos SLAs definidos
- **Output:** Relatório de cobertura, resultado dos testes, status de SLA

#### 8. 📊 Reporter Agent
- **Responsabilidade:** Consolida todos os resultados em relatório executivo e técnico
- **Ferramentas:**
  - `generate_markdown_report` — relatório técnico detalhado
  - `generate_executive_summary` — resumo executivo com impacto de negócio
  - `render_before_after_diff` — diff visual colorido das mudanças
  - `create_metrics_chart` — gráfico de melhoria de performance
- **Output:** Relatório HTML/PDF + changelogs

---

## 📁 Estrutura de Diretórios

```
SentinelCode/
├── main.py                          # Entry point CLI
├── config.py                        # Configurações (API keys, modelos)
├── requirements.txt
├── .env.example
│
├── agents/
│   ├── __init__.py
│   ├── orchestrator.py              # LangGraph StateGraph principal
│   ├── code_analyzer.py
│   ├── iac_analyzer.py
│   ├── benchmark.py
│   ├── fix_agent.py
│   ├── iac_patcher.py
│   ├── test_agent.py
│   └── reporter.py
│
├── tools/
│   ├── java/
│   │   ├── file_reader.py
│   │   ├── pom_parser.py
│   │   ├── issue_detectors.py       # Detectores de N+1, missing cache, etc
│   │   └── code_patcher.py
│   ├── iac/
│   │   ├── terraform_parser.py
│   │   ├── k8s_parser.py
│   │   ├── cost_simulator.py
│   │   └── iac_patcher.py
│   └── testing/
│       ├── locust_runner.py
│       ├── test_generator.py
│       └── metrics_collector.py
│
├── models/
│   ├── issue.py                     # Dataclasses: Issue, InfraGap, BenchmarkReport
│   ├── state.py                     # LangGraph AgentState
│   └── report.py
│
├── templates/
│   ├── report.html.j2               # Template Jinja2 do relatório
│   └── locust_test.py.j2            # Template de teste de carga
│
├── tests/
│   ├── unit/
│   │   ├── test_detectors.py
│   │   ├── test_iac_parser.py
│   │   └── test_fix_agent.py
│   └── integration/
│       └── test_full_pipeline.py
│
└── docs/
    ├── ARCHITECTURE.md              # Este documento
    ├── AGENTS.md                    # Documentação de cada agente
    ├── TOOLS.md                     # Documentação das tools
    └── CONTRIBUTING.md
```

---

## 🔄 Fluxo de Estado (LangGraph)

```python
# models/state.py
from typing import TypedDict, List, Optional
from models.issue import Issue, InfraGap, BenchmarkReport

class AgentState(TypedDict):
    # Input
    project_path: str
    project_type: str                    # "java-spring" | "terraform" | "k8s" | "mixed"
    non_functional_requirements: dict    # {"max_rps": 10000, "p99_latency_ms": 200}
    
    # Analysis Phase
    issues: List[Issue]
    infra_gaps: List[InfraGap]
    
    # Benchmark Phase  
    benchmark_before: Optional[BenchmarkReport]
    benchmark_after: Optional[BenchmarkReport]
    
    # Fix Phase
    applied_fixes: List[dict]           # {"file": str, "before": str, "after": str}
    applied_iac_changes: List[dict]
    
    # Test Phase
    test_results: dict
    sla_validation: dict
    
    # Report
    final_report: Optional[str]
    messages: List[str]                  # Log de mensagens entre agentes
```

---

## ⚙️ Configuração

### `.env`
```env
# LLM
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o                    # Recomendado para análise de código

# Opcional: LangSmith para observabilidade
LANGCHAIN_API_KEY=ls__...
LANGCHAIN_TRACING_V2=true
LANGCHAIN_PROJECT=SentinelCode

# Opcional: Anthropic como alternativa
ANTHROPIC_API_KEY=sk-ant-...

# AWS (para simulação de custo)
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_DEFAULT_REGION=us-east-1
```

### `config.py`
```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    openai_api_key: str
    openai_model: str = "gpt-4o"
    anthropic_api_key: str | None = None
    langchain_api_key: str | None = None
    langchain_tracing_v2: bool = False
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    aws_default_region: str = "us-east-1"

    class Config:
        env_file = ".env"

settings = Settings()
```

---

## 🚀 Stack Tecnológica

| Camada | Tecnologia | Justificativa |
|---|---|---|
| Orquestração de agentes | **LangGraph 0.2+** | Grafos de estado, flows condicionais, retry |
| LLM principal | **OpenAI GPT-4o** | Melhor raciocínio de código |
| LLM alternativo | **Claude 3.5 Sonnet** | Fallback / análise de contexto longo |
| Parse Java/POM | **javalang**, **xml.etree** | Parse AST de Java |
| Parse Terraform | **python-hcl2** | Parse nativo de HCL |
| Parse K8s | **pyyaml** | Manifests YAML |
| Testes de carga | **Locust** (Python-nativo) | Integração programática simples |
| Execução de testes | **subprocess** + **Maven Wrapper** | Roda testes do projeto analisado |
| Relatórios | **Jinja2** + **WeasyPrint** | HTML → PDF |
| Validação de config | **Pydantic v2** | Type-safe settings |
| Observabilidade | **LangSmith** | Trace de todas as chamadas de agentes |
| CLI | **Typer** | Interface de linha de comando elegante |

---

## 📦 `requirements.txt`

```
# Core
langgraph>=0.2.0
langchain>=0.3.0
langchain-openai>=0.2.0
langchain-anthropic>=0.2.0

# Config
pydantic>=2.0.0
pydantic-settings>=2.0.0
python-dotenv>=1.0.0

# IaC Parsing
python-hcl2>=4.3.0
pyyaml>=6.0.0

# Java Parsing
javalang>=0.13.0

# Testing / Benchmark
locust>=2.20.0

# Reporting
jinja2>=3.1.0
weasyprint>=62.0
markdown>=3.5.0

# CLI
typer>=0.12.0
rich>=13.0.0

# AWS (cost simulation)
boto3>=1.34.0

# Utilities
httpx>=0.27.0
```

---

## 🖥️ Interface CLI

```bash
# Analisar projeto Java
python main.py analyze \
  --path ./meu-projeto-spring \
  --type java-spring \
  --sla "rps=10000,p99=200ms" \
  --apply-fixes \
  --run-benchmarks

# Analisar IaC Terraform
python main.py analyze \
  --path ./terraform/production \
  --type terraform \
  --nfr "availability=99.9%,region=us-east-1,max-cost=5000/month" \
  --apply-fixes

# Apenas relatório, sem aplicar fixes
python main.py analyze \
  --path ./meu-projeto \
  --type mixed \
  --dry-run \
  --output-format pdf
```

---

## 📋 Exemplo de Relatório Gerado

```
=== SentinelCode Report — meu-projeto-spring ===
Data: 2025-01-15 | Duração da análise: 4m 32s

RESUMO EXECUTIVO
────────────────
🔴 Crítico: 3 problemas  🟡 Alto: 7 problemas  🟢 Médio: 4 problemas
Melhoria estimada de P99: -68% (de 850ms → 270ms)
Ganho estimado de throughput: +340% (de 1.200 → 5.300 RPS)

PROBLEMAS IDENTIFICADOS
────────────────────────
[CRÍTICO] N+1 Query — OrderService.java:142
  Root Cause: Loop com chamada a orderItemRepo.findByOrder(order) por pedido
  Fix aplicado: JOIN FETCH na query JPQL + @EntityGraph
  Impacto: -72% queries ao banco por requisição

[CRÍTICO] Missing Index — Product.category + Product.status
  Root Cause: Query com WHERE category=? AND status=? sem índice composto
  Fix aplicado: Migration V5__add_product_index.sql gerado
  Impacto: Full scan → Index scan (100k rows)

[ALTO] Connection Pool subdimensionado — application.yml
  Root Cause: spring.datasource.hikari.maximum-pool-size=5 (padrão)
  Fix aplicado: Ajuste para 20 conexões + timeout configurado
  Impacto: Eliminação de 23% dos timeouts em pico

BENCHMARK ANTES / DEPOIS
─────────────────────────
           ANTES      DEPOIS     DELTA
P50:       145ms  →   48ms      -67%
P95:       620ms  →   185ms     -70%
P99:       850ms  →   270ms     -68%
RPS:       1.200  →   5.300     +342%
Error %:   4.2%   →   0.1%      -97%

INFRAESTRUTURA
──────────────
[ALTO] Ausência de Auto Scaling — ECS Service "api-prod"
  Fix: Auto Scaling Policy adicionada (min=2, max=10, target CPU 70%)
  Custo estimado: +$180/mês em pico vs $1.200/mês em downtime evitado

TESTES
──────
Unit Tests:        47 passando / 0 falhas
Functional Tests:  23 passando / 0 falhas  
SLA Validation:    ✅ P99 < 200ms atingido | ✅ RPS > 5.000 atingido
```

---

## 🗺️ Roadmap de Implementação

### Fase 1 — MVP 
- [x] Setup do projeto, config, CLI básica
- [x] Code Analyzer Agent (N+1, missing cache, connection pool)
- [x] Fix Agent (fixes cirúrgicos + validação + rollback automático)
- [x] Reporter Agent (relatório HTML com diffs visuais antes/depois)
- [x] Orchestrator (pipeline completo integrado)

### Fase 2 — Core 
- [x] IaC Analyzer Agent (Terraform — python-hcl2)
- [x] IaC Patcher Agent (altera .tf com justificativa)
- [x] Benchmark Agent (Locust integrado programaticamente)
- [ ] Test Agent (geração de testes funcionais)

### Fase 3 — Expansão
- [ ] Suporte a K8s manifests
- [ ] Suporte a CloudFormation
- [ ] Simulação de custo AWS
- [ ] Relatório PDF executivo
- [ ] LangSmith observabilidade completa
- [ ] Mais detectores Java (Missing Index, Lazy Loading, Thread Blocking)

---

## 🔐 Segurança

- Nunca commitar `.env` — usar `.env.example`
- Fixes de código sempre em branch separada ou dry-run mode
- Operações destrutivas exigem confirmação explícita (`--confirm`)
- Análise de custo é estimativa, não chamada de API com autorização de gasto
