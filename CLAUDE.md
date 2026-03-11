# CLAUDE.md — SentinelCode

Arquivo de contexto persistente. Leia este arquivo no início de cada sessão
antes de implementar qualquer coisa no projeto.

---

## 🎯 O que é o SentinelCode

Sistema multi-agente em Python que analisa, diagnostica e corrige
automaticamente problemas de performance em:
- Aplicações Java/Spring Boot (código-fonte)
- Infraestrutura como Código (Terraform, K8s, CloudFormation)

Gera relatório HTML com causa raiz, severidade, diffs antes/depois
e métricas de ganho de performance.

---

## 🏗️ Arquitetura

### Framework
**LangGraph** — grafos de estado com fluxos condicionais e ciclos.
Cada agente é um `StateGraph` com nós independentes e testáveis.

### Estado compartilhado
`models/state.py` — `AgentState` (TypedDict) circula entre todos os agentes.
Campos com `Annotated[List, operator.add]` são acumulativos entre nós.
Campos com prefixo `_` (ex: `_enriched_issues`) são temporários e NÃO
persistem entre nós do LangGraph — nunca usar para passar dados entre nós.

### LLM
- Principal: `gpt-4o` via `langchain-openai`
- Temperature: sempre `0` (respostas determinísticas)
- Configurado em `config.py` via `pydantic-settings` lendo `.env`

---

## 📁 Estrutura de Diretórios

```
sentinel-code/
├── main.py                  # CLI entry point (Typer)
├── config.py                # Settings via pydantic-settings
├── CLAUDE.md                # Este arquivo
│
├── agents/
│   ├── orchestrator.py      # Pipeline completo
│   ├── code_analyzer.py     # Analisa Java/Spring Boot
│   ├── fix_agent.py         # Aplica correções no código
│   ├── reporter.py          # Gera relatório HTML
│   ├── iac_analyzer.py      # (Fase 2) Analisa Terraform/K8s
│   ├── iac_patcher.py       # (Fase 2) Corrige IaC
│   ├── benchmark.py         # (Fase 2) Locust antes/depois
│   └── test_agent.py        # (Fase 2) Gera testes funcionais
│
├── models/
│   ├── state.py             # AgentState — estado global
│   └── issue.py             # Issue, Severity, IssueCategory
│
├── tools/
│   ├── java/
│   │   ├── file_reader.py       # Lê .java e configs
│   │   ├── issue_detectors.py   # Detectores estáticos
│   │   └── code_patcher.py      # Aplica patches em arquivos
│   └── iac/                     # (Fase 2)
│       ├── terraform_parser.py
│       ├── k8s_parser.py
│       └── iac_patcher.py
│
├── templates/
│   └── report.html.j2       # Template Jinja2 do relatório
│
├── specs/                   # Spec Driven Development
│   ├── agents/
│   │   ├── code_analyzer.md
│   │   ├── fix_agent.md
│   │   ├── iac_analyzer.md  # (Fase 2)
│   │   └── benchmark.md     # (Fase 2)
│   └── tools/
│       ├── detectors.md
│       └── patchers.md
│
├── sample_project/          # Projeto Java de exemplo para testes
└── outputs/                 # Relatórios gerados (gitignored)
```

---

## ✅ O que já foi implementado (Fase 1)

### Agentes
| Agente | Arquivo | Status |
|--------|---------|--------|
| Code Analyzer | `agents/code_analyzer.py` | ✅ |
| Fix Agent | `agents/fix_agent.py` | ✅ |
| Reporter | `agents/reporter.py` | ✅ |
| Orchestrator | `agents/orchestrator.py` | ✅ |

### Detectores Java (`tools/java/issue_detectors.py`)
| Detector | Método | Status |
|----------|--------|--------|
| N+1 Query | AST + fallback textual | ✅ |
| Cache Ausente | Heurística @GetMapping | ✅ |
| Connection Pool | Parse application.properties/yml | ✅ |

### Fixes automáticos (`agents/fix_agent.py`)
| Fix | Estratégia | Status |
|-----|-----------|--------|
| N+1 Query | Extrai snippet por linha + LLM corrige | ✅ |
| Cache Ausente | Insere @Cacheable cirurgicamente (sem LLM) | ✅ |
| Connection Pool | Cria/atualiza application.yml (sem LLM) | ✅ |

---

## 📐 Decisões técnicas e o porquê

### Fixes cirúrgicos vs LLM
**Regra:** usar LLM apenas quando a correção é não-determinística.
- `@Cacheable` → inserção de 1 linha → sem LLM
- HikariCP config → configuração padrão conhecida → sem LLM
- N+1 refactor → depende do código específico → com LLM

**Motivo:** LLM gera código com imports extras, reescreve indentação,
adiciona comentários — tudo isso quebra o patch por substituição de string.

### Validação de fixes
**Regra:** comparar balanço de chaves antes vs depois do patch.
Se `brace_balance(after) >= brace_balance(before)` → fix válido.

**Motivo:** `javalang.parse` é muito estrito e falha em arquivos
Java incompletos (sem package, sem imports). A validação por balanço
de chaves é pragmática e funciona em qualquer arquivo.

### Campos temporários no AgentState
**Regra:** NUNCA passar dados entre nós via campos com prefixo `_`.
O LangGraph não persiste campos desconhecidos no TypedDict entre nós.

**Motivo:** bug recorrente na Fase 1 — `_fixable_issues` e `_report_context`
foram perdidos entre nós e causaram execuções vazias.

**Solução:** ou declarar o campo no `AgentState`, ou fundir os nós
que precisam compartilhar dados temporários (como foi feito no Reporter).

### Snippet original para patches
**Regra:** extrair o snippet DIRETAMENTE do arquivo por número de linha,
nunca via LLM ou via `before_code` do enriquecimento.

**Motivo:** o LLM sempre reescreve levemente o código ao "copiar" —
isso quebra a substituição de string. A extração direta garante
correspondência exata.

---

## 🔄 Pipeline completo (Fase 1)

```
read_files → detect_issues → enrich_with_llm
    → plan_fixes → apply_fixes → validate_fixes
    → generate_report → END
```

Montado dinamicamente em `main.py` usando `StateGraph(AgentState)`.
O `orchestrator.py` tem a versão completa sempre-com-fixes.

---

## 🚀 Próximos passos (Fase 2)

### IaC Analyzer Agent
- Parser Terraform: `python-hcl2`
- Parser K8s: `pyyaml`
- Detectores: ausência de autoscaling, instâncias subdimensionadas,
  single-AZ, falta de CDN, connection limits
- Spec: `specs/agents/iac_analyzer.md`

### IaC Patcher Agent
- Modifica blocos HCL/YAML com justificativa inline
- Gera diffs dos arquivos `.tf` / `.yaml`
- Spec: `specs/agents/iac_patcher.md` (a criar)

### Benchmark Agent
- Locust programático (sem subprocess)
- Coleta métricas antes e depois dos fixes
- Compara P50/P95/P99/RPS/Error Rate
- Spec: `specs/agents/benchmark.md`

### Test Agent
- Gera testes funcionais com RestAssured
- Valida SLAs definidos nos requisitos não funcionais
- Spec: `specs/agents/test_agent.md` (a criar)

---

## ⚙️ Como rodar

```bash
# Ambiente
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt

# Análise completa
python main.py --path .\sample_project\

# Só análise, sem aplicar fixes
python main.py --path .\sample_project\ --dry-run
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