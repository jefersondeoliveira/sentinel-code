# Spec: Simulação de Custo AWS via Pricing API

## Status
Fase 3 / Fase 4 — [ ] Pendente

## Contexto
O SentinelCode detecta instâncias subdimensionadas e sugere upgrades, mas não quantifica
o impacto financeiro. Sem estimativa de custo, é difícil priorizar mudanças de infraestrutura
ou justificar investimentos para gestão. A AWS Pricing API (endpoint público, sem autenticação)
permite obter preços on-demand de instâncias EC2 e RDS em tempo real.

## Objetivo
Enriquecer os `InfraGap` do tipo `UNDERSIZED_INSTANCE` com estimativa de custo mensal
(atual vs recomendado) e exibir o delta no relatório HTML/PDF.

## Escopo

### Inclui
- Consulta à AWS Pricing API para EC2 e RDS (instâncias on-demand, região us-east-1 como padrão)
- Campo `cost_impact` no `InfraGap` já existe — preencher com valor real em USD/mês
- Exibição do campo `cost_impact` na tabela de gaps do relatório HTML
- Cache local dos preços (arquivo JSON em `outputs/.price_cache.json`) para evitar múltiplas requisições
- Suporte a flag `--region` no CLI para mudar a região de pricing

### Não inclui
- Pricing de outros serviços além de EC2 e RDS
- Instâncias Spot, Reserved ou Savings Plans (somente on-demand)
- Suporte a múltiplas regiões simultâneas
- Integração com AWS Cost Explorer (requer credenciais)

## Arquitetura

Novo módulo `tools/iac/aws_pricing.py` chamado dentro do `IaC Analyzer`
no nó `enrich_iac_with_llm` (após a detecção de gaps), ou como nó separado
`enrich_cost` inserido no pipeline opcionalmente via flag `--with-cost`.

```
detect_infra_gaps → enrich_iac_with_llm → [enrich_cost]  ← novo nó opcional
```

## Mudanças no AgentState (`models/state.py`)

Nenhuma mudança estrutural. O campo `infra_gaps: Annotated[List, operator.add]`
já existe. O nó `enrich_cost` substitui gaps existentes com versões enriquecidas
(retorna `{"infra_gaps": enriched_gaps}`).

**Atenção**: como `infra_gaps` usa `operator.add`, o nó deve retornar apenas
os gaps novos/atualizados, não a lista completa duplicada. Considerar trocar para
campo não-acumulativo `infra_gaps_enriched: List` ou usar lógica de deduplicação
por `resource + category`.

## Novos arquivos

| Arquivo | Responsabilidade |
|---------|-----------------|
| `tools/iac/aws_pricing.py` | `get_ec2_price(instance_type, region) -> float`, `get_rds_price(instance_type, region) -> float`, `estimate_monthly_cost(instance_type, hours=730) -> float`, gerenciamento de cache |
| `tests/unit/test_aws_pricing.py` | Testes com mock HTTP (mínimo 10 testes) |

## Arquivos existentes a modificar

| Arquivo | O que muda |
|---------|-----------|
| `agents/iac_analyzer.py` | Novo nó `enrich_cost_node` que chama `aws_pricing.enrich_gaps_with_cost(gaps)` e atualiza `infra_gaps` |
| `agents/orchestrator.py` | Flag `with_cost: bool = False` em `build_full_pipeline()` adiciona o nó `enrich_cost` entre `enrich_iac_with_llm` e o próximo nó |
| `main.py` | Flag `--cost/--no-cost` passa `with_cost` para `build_full_pipeline()` |
| `templates/report.html.j2` | Coluna `cost_impact` na tabela de InfraGaps, com formatação USD |

## Fluxo de dados

```
InfraGap(category=UNDERSIZED_INSTANCE, resource="aws_db_instance.main",
         current_config={"instance_class": "db.t3.micro"},
         recommended_config={"instance_class": "db.t3.medium"},
         cost_impact=None)

↓ enrich_cost_node

aws_pricing.get_rds_price("db.t3.micro")   → $0.017/hr → $12.41/mês
aws_pricing.get_rds_price("db.t3.medium")  → $0.068/hr → $49.64/mês

InfraGap(cost_impact="Atual: $12/mês → Recomendado: $50/mês (+$38/mês)")
```

## Decisões técnicas

- **AWS Pricing API endpoint**: `https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonEC2/current/index.json` — arquivo enorme; usar endpoint filtrado por região: `https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/{service}/current/{region}/index.json`
- **Biblioteca**: `requests` (já dependência via locust/httpx); fallback gracioso se offline
- **Cache TTL**: 24 horas (timestamp no arquivo de cache)
- **Formato do cost_impact**: string legível: `"Atual: $12/mês → Recomendado: $50/mês (+$38/mês)"`
- **Falha silenciosa**: se a API estiver inacessível, `cost_impact` permanece `None` e o pipeline continua

## Critérios de aceitação

- [ ] `get_ec2_price("t3.micro", "us-east-1")` retorna float > 0
- [ ] `get_rds_price("db.t3.medium", "us-east-1")` retorna float > 0
- [ ] Segunda chamada usa cache (sem requisição HTTP)
- [ ] Gap `UNDERSIZED_INSTANCE` tem `cost_impact` preenchido após `enrich_cost_node`
- [ ] Pipeline sem `--cost` não faz requisições HTTP de pricing
- [ ] Falha na API não interrompe o pipeline (retorna `cost_impact=None`)
- [ ] Relatório HTML exibe coluna de custo quando `cost_impact` não é `None`

## Testes

```python
# tests/unit/test_aws_pricing.py
# - test_get_ec2_price_returns_float (mock requests)
# - test_get_rds_price_returns_float (mock requests)
# - test_cache_prevents_second_http_call
# - test_cache_expired_triggers_new_call
# - test_monthly_cost_calculation (730 horas)
# - test_enrich_gaps_with_cost_fills_cost_impact
# - test_enrich_gaps_skips_non_undersized_gaps
# - test_api_failure_returns_none_gracefully
# - test_offline_mode_uses_cache
# - test_cost_impact_string_format
```
