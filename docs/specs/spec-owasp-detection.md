# Spec: Detecção de Vulnerabilidades OWASP Top 10 em Código Java

## Status
Fase 4 — [ ] Pendente

## Contexto
O SentinelCode foca hoje em performance, mas segurança e performance estão fortemente
relacionados: SQL Injection causa full table scans, log injection polui observabilidade,
e deserialização insegura pode ser explorada para DoS. O OWASP Top 10 é o padrão
da indústria para vulnerabilidades críticas em aplicações web.

Adicionar detecção OWASP expande o valor do SentinelCode de "analisador de performance"
para "analisador de qualidade de aplicações Spring Boot", sem mudar a arquitetura.

## Objetivo
Detectar os padrões OWASP Top 10 mais relevantes em código Java/Spring Boot
via análise estática (regex + AST), gerando `Issue` com severidade adequada.

## Escopo

### Inclui (subconjunto acionável via análise estática)
- **A01 Broken Access Control**: `@PreAuthorize` ausente em endpoints `@PostMapping`/`@DeleteMapping`/`@PutMapping`
- **A02 Cryptographic Failures**: uso de `MD5` ou `SHA1` (algoritmos fracos); `Random` em vez de `SecureRandom` para tokens
- **A03 Injection**: concatenação de string em queries SQL (`String sql = "SELECT * FROM " + input`); uso de `Runtime.exec()` com input do usuário
- **A05 Security Misconfiguration**: CORS `allowedOrigins("*")` sem restrição; `@CrossOrigin` sem parâmetros
- **A09 Security Logging Failures**: captura de exceção com `e.printStackTrace()` em vez de logger; log de senha ou token (`log.info("password: " + password)`)

### Não inclui
- A04 Insecure Design (análise arquitetural — fora de escopo de análise estática)
- A06 Vulnerable Components (requer análise de dependências — ver `spec-gradle-support.md`)
- A07 Identification and Authentication Failures (requer análise de configuração de sessão Spring Security completa)
- A08 Software and Data Integrity Failures (requer análise de pipeline CI/CD)
- A10 SSRF (requer análise de fluxo de dados — análise estática limitada)
- Execução de SAST completo (não substitui ferramentas como SpotBugs/SonarQube)

## Arquitetura

Novos detectores em `tools/java/issue_detectors.py` seguindo o padrão existente:
função por categoria, retorna `List[Issue]`, sem LLM, chamados em `detect_issues_node`.

```
detect_issues_node
  → detectores de performance (existentes)
  → detectores OWASP (novos) ← adicionar aqui
  → retorna issues combinados
```

## Mudanças no AgentState (`models/state.py`)
Nenhuma. `issues: Annotated[List[Issue], operator.add]` já suporta novos issues.

## Mudanças nos modelos

### `models/issue.py`
Adicionar categorias OWASP ao enum `IssueCategory`:
```python
class IssueCategory(str, Enum):
    # existentes
    N_PLUS_ONE = "N+1 Query"
    MISSING_CACHE = "Cache Ausente"
    CONNECTION_POOL = "Connection Pool"
    MISSING_INDEX = "Índice Ausente"
    PAGINATION = "Paginação"
    LAZY_LOADING = "Lazy Loading"
    THREAD_BLOCKING = "Thread Bloqueante"
    GENERAL = "Geral"
    # novos
    BROKEN_ACCESS_CONTROL = "Controle de Acesso Quebrado"
    CRYPTO_FAILURE = "Falha Criptográfica"
    INJECTION = "Injeção"
    SECURITY_MISCONFIGURATION = "Má Configuração de Segurança"
    SECURITY_LOGGING = "Logging de Segurança"
```

## Novos arquivos

| Arquivo | Responsabilidade |
|---------|-----------------|
| `tools/java/owasp_detectors.py` | `detect_broken_access_control()`, `detect_crypto_failures()`, `detect_injection()`, `detect_security_misconfiguration()`, `detect_security_logging_failures()` — cada um retorna `List[Issue]` |
| `tests/unit/test_owasp_detectors.py` | Mínimo 20 testes cobrindo true positives e false negatives |

## Arquivos existentes a modificar

| Arquivo | O que muda |
|---------|-----------|
| `agents/code_analyzer.py` | `detect_issues_node` importa e chama detectores OWASP após os de performance |
| `models/issue.py` | Novas categorias no enum `IssueCategory` |
| `templates/report.html.j2` | Seção separada "Vulnerabilidades de Segurança" ou badge OWASP por issue |

## Fluxo de dados

```python
# Exemplo: detect_injection
def detect_injection(java_files: List[dict]) -> List[Issue]:
    issues = []
    sql_concat_pattern = re.compile(
        r'(?:String\s+\w+\s*=\s*|[\w\.]+\s*\+=\s*)"[^"]*"\s*\+\s*\w',
        re.MULTILINE
    )
    exec_pattern = re.compile(r'Runtime\.getRuntime\(\)\.exec\(')

    for file in java_files:
        content = file["content"]
        for i, line in enumerate(content.splitlines(), start=1):
            if sql_concat_pattern.search(line) and any(
                kw in line.upper() for kw in ("SELECT", "INSERT", "UPDATE", "DELETE", "FROM")
            ):
                issues.append(Issue(
                    category=IssueCategory.INJECTION,
                    severity=Severity.CRITICAL,
                    file_path=file["path"],
                    line=i,
                    root_cause="Concatenação de string em query SQL permite SQL Injection",
                    evidence=line.strip(),
                    suggestion="Use PreparedStatement ou @Query com parâmetros nomeados",
                ))
    return issues
```

## Decisões técnicas

- **Severidade padrão**: `CRITICAL` para Injection e Broken Access Control; `HIGH` para Crypto e Misconfiguration; `MEDIUM` para Logging
- **Falsos positivos**: aceitáveis em análise estática — enriquecimento LLM filtra os mais óbvios
- **Sem novos fixes automáticos**: issues OWASP são somente detectados e reportados (requerem revisão humana)
- **`FIXABLE_CATEGORIES`**: não incluir categorias OWASP — mesma abordagem de PAGINATION/LAZY_LOADING

## Critérios de aceitação

- [ ] `@PostMapping` sem `@PreAuthorize` gera issue `BROKEN_ACCESS_CONTROL`
- [ ] `MessageDigest.getInstance("MD5")` gera issue `CRYPTO_FAILURE`
- [ ] `"SELECT * FROM " + userInput` gera issue `INJECTION` com severidade CRITICAL
- [ ] `@CrossOrigin` sem parâmetros gera issue `SECURITY_MISCONFIGURATION`
- [ ] `e.printStackTrace()` em catch gera issue `SECURITY_LOGGING`
- [ ] Relatório HTML exibe issues OWASP com badge de categoria
- [ ] Issues de performance continuam funcionando normalmente (regressão zero)
- [ ] `pytest tests/unit/test_owasp_detectors.py` passa

## Testes

```python
# tests/unit/test_owasp_detectors.py
# - test_detect_missing_preauthorize_on_post
# - test_detect_missing_preauthorize_on_delete
# - test_get_mapping_without_preauthorize_no_issue (GET é público por design)
# - test_detect_md5_usage
# - test_detect_sha1_usage
# - test_sha256_no_issue
# - test_detect_sql_string_concatenation
# - test_detect_runtime_exec
# - test_prepared_statement_no_injection_issue
# - test_detect_cors_wildcard
# - test_crossorigin_with_origins_no_issue
# - test_detect_print_stack_trace
# - test_detect_password_in_log
# - test_proper_logger_no_issue
# - test_multiple_issues_same_file
# - test_empty_file_no_crash
# - test_non_java_file_skipped
# - test_false_positive_md5_in_comment_skipped
# - test_severity_injection_is_critical
# - test_severity_crypto_is_high
```
