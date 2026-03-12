# Spec: Fix Agent com LLM para PAGINATION, LAZY_LOADING e MISSING_INDEX

## Status
Fase 4 — [ ] Pendente

## Contexto
O Fix Agent atual aplica correções determinísticas (sem LLM) para categorias onde
a solução é previsível: `@Cacheable` para `MISSING_CACHE`, configuração HikariCP
para `CONNECTION_POOL`, e JOIN FETCH para `N_PLUS_ONE`.

As categorias `PAGINATION`, `LAZY_LOADING` e `MISSING_INDEX` são detectadas e enriquecidas
pelo LLM no Code Analyzer, mas o Fix Agent as ignora (`FIXABLE_CATEGORIES` não as inclui).
Isso ocorre porque suas correções dependem do código específico e não são previsíveis:
paginação requer refatorar assinatura de método; lazy loading requer entender relacionamentos
JPA; índices requerem conhecer os campos de busca da entidade.

O LLM (GPT-4o) é capaz de gerar essas correções com alta qualidade quando fornecido com
o trecho de código e contexto suficiente.

## Objetivo
Estender o Fix Agent para aplicar correções via LLM nas categorias
`PAGINATION`, `LAZY_LOADING` e `MISSING_INDEX`, com validação de brace balance
e rollback automático em caso de falha — mantendo os mesmos contratos do Fix Agent atual.

## Escopo

### Inclui
- Geração de patch via LLM para as 3 categorias
- Validação do patch gerado (brace balance, compilabilidade básica)
- Rollback automático se o patch introduz regressão
- Diff antes/depois no `AppliedFix` para o relatório
- Prompt engineering específico por categoria

### Não inclui
- Refatoração de múltiplos arquivos em uma única correção (patch cirúrgico em 1 arquivo)
- Execução de testes Java para validar a correção (sem JDK obrigatório)
- Suporte a outros frameworks além de Spring Data JPA

## Arquitetura

Extensão do `Fix Agent` existente (`agents/fix_agent.py`). O nó `apply_fixes_node`
já tem lógica de dispatch por categoria — adicionar um branch `_apply_llm_fix(issue, file_content)`
chamado para as 3 novas categorias.

```
plan_fixes_node
  → classifica fixes por estratégia: cirúrgico vs llm

apply_fixes_node
  → para PAGINATION / LAZY_LOADING / MISSING_INDEX:
      → _apply_llm_fix(issue, file_content)
          → build_prompt(category, code_snippet, issue)
          → llm.invoke(prompt)
          → parse_llm_response() → (before, after, explanation)
          → validate_patch(before, after)
          → apply or rollback
```

## Mudanças no AgentState (`models/state.py`)
Nenhuma. `applied_fixes: Annotated[List[dict], operator.add]` já suporta o resultado.

## Novos arquivos

| Arquivo | Responsabilidade |
|---------|-----------------|
| `tools/java/llm_fix_prompts.py` | Templates de prompt por categoria: `PAGINATION_PROMPT`, `LAZY_LOADING_PROMPT`, `MISSING_INDEX_PROMPT`. Cada prompt instrui o LLM a retornar bloco `<before>` e `<after>` delimitados |
| `tests/unit/test_llm_fixes.py` | Testes com LLM mockado (mínimo 12 testes) |

## Arquivos existentes a modificar

| Arquivo | O que muda |
|---------|-----------|
| `agents/fix_agent.py` | Adicionar `PAGINATION`, `LAZY_LOADING`, `MISSING_INDEX` em `FIXABLE_CATEGORIES`. Adicionar `_apply_llm_fix()` e `_build_fix_prompt()`. Modificar `apply_fixes_node` para fazer dispatch |
| `tools/java/code_patcher.py` | Adicionar `apply_llm_patch(file_path, before_code, after_code) -> bool` com backup/restore |

## Fluxo de dados

```python
# Prompt estruturado por categoria — exemplo PAGINATION:
PAGINATION_PROMPT = """
Você é um especialista em Spring Data JPA. O método abaixo retorna uma lista completa
sem paginação, causando problemas de performance.

Arquivo: {file_path}
Issue: {root_cause}
Código atual:
```java
{code_snippet}
```

Retorne SOMENTE o patch no formato:
<before>
[código exato a ser substituído — deve ser substring do código atual]
</before>
<after>
[código corrigido com Pageable/Page<T>]
</after>
<explanation>
[explicação em 1 frase]
</explanation>

Regras:
- O bloco <before> deve ser encontrado exatamente no arquivo
- Não altere imports, anotações ou métodos não relacionados
- Adicione imports necessários no topo se ausentes
"""

# Validação do patch
def validate_llm_patch(original: str, patched: str) -> bool:
    # Regra existente: brace_balance(patched) >= brace_balance(original)
    return brace_balance(patched) >= brace_balance(original)
```

## Decisões técnicas

- **Temperatura**: `0` (determinístico, igual ao restante do sistema)
- **Parsing da resposta**: regex para extrair `<before>`, `<after>`, `<explanation>` — falha silenciosa se formato inválido
- **Idempotência**: verificar se `before_code` está presente no arquivo antes de aplicar
- **Fallback**: se o LLM retornar patch inválido (before não encontrado no arquivo), registrar `status: "failed"` e continuar — nunca crashar o pipeline
- **Limite de tokens**: truncar `code_snippet` a 150 linhas ao redor da linha do issue para evitar context overflow

## Critérios de aceitação

- [ ] Issue `PAGINATION` em repositório sem `Pageable` recebe fix via LLM
- [ ] Issue `LAZY_LOADING` em `@OneToMany` recebe fix via LLM
- [ ] Issue `MISSING_INDEX` em `findBy*` recebe `@Index` via LLM
- [ ] Patch inválido (before não encontrado) registra `status: "failed"` sem crashar
- [ ] Brace balance é validado após o patch
- [ ] Rollback é executado quando brace balance cai
- [ ] `applied_fixes` contém `before_code` e `after_code` para o relatório
- [ ] `pytest tests/unit/test_llm_fixes.py` passa com LLM mockado

## Testes

```python
# tests/unit/test_llm_fixes.py
# - test_pagination_fix_applied_via_llm (mock LLM)
# - test_lazy_loading_fix_applied_via_llm
# - test_missing_index_fix_applied_via_llm
# - test_llm_returns_invalid_format_fix_fails_gracefully
# - test_before_code_not_found_fix_fails
# - test_brace_balance_regression_triggers_rollback
# - test_backup_file_removed_on_success
# - test_backup_file_restored_on_failure
# - test_applied_fix_contains_before_after_diff
# - test_fixable_categories_includes_pagination
# - test_fixable_categories_includes_lazy_loading
# - test_fixable_categories_includes_missing_index
```
