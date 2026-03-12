# Spec: Suporte a CloudFormation

## Status
Fase 3 / Fase 4 — [ ] Pendente

## Contexto
O SentinelCode já analisa Terraform (`.tf`) e manifests Kubernetes (`.yaml`/`.yml`).
CloudFormation (CFN) é o serviço nativo de IaC da AWS, amplamente usado em ambientes
corporativos. Sem suporte a CFN, o sistema fica cego para stacks completas de
infraestrutura AWS definidas em templates JSON ou YAML do CloudFormation.

## Objetivo
Detectar gaps de performance e segurança em templates CloudFormation (`.json`, `.yaml`)
com as mesmas categorias do IaC Analyzer existente: autoscaling ausente, single-AZ,
instância subdimensionada, resource limits e health checks.

## Escopo

### Inclui
- Leitura e parsing de templates CFN em JSON e YAML
- Detecção de recursos sem Auto Scaling (`AWS::AutoScaling::AutoScalingGroup` ausente para `AWS::ECS::Service`)
- Detecção de RDS sem Multi-AZ (`AWS::RDS::DBInstance` com `MultiAZ: false`)
- Detecção de instâncias subdimensionadas (`InstanceType` vs NFR `max_rps`)
- Geração de `InfraGap` com categoria, severidade, resource, file_path e sugestão
- Enriquecimento via LLM (mesmo fluxo do `enrich_iac_with_llm`)
- Patches automáticos onde aplicável (modify_attribute para MultiAZ, append_block para autoscaling)

### Não inclui
- Validação completa de sintaxe CFN (não é um linter CFN)
- Suporte a SAM (Serverless Application Model)
- Suporte a CDK (o CDK sintetiza para CFN; o output sintetizado pode ser analisado)
- Deploy ou execução de stacks CFN

## Arquitetura

O suporte a CFN é adicionado como extensão das ferramentas IaC existentes,
sem novo agente LangGraph. O `IaC Analyzer` já chama `read_iac_files` e
`detect_infra_gaps` — ambos precisam reconhecer o formato CFN.

```
read_iac_files → detect_infra_gaps → enrich_iac_with_llm
                     ↑
              [novo: cfn_gap_detectors]
```

## Mudanças no AgentState (`models/state.py`)
Nenhuma mudança. `iac_files` e `infra_gaps` já existem com tipos genéricos.

## Novos arquivos

| Arquivo | Responsabilidade |
|---------|-----------------|
| `tools/iac/cfn_file_reader.py` | Lê templates CFN `.json`/`.yaml`, retorna lista de dicts com `{path, type: "cloudformation", parsed, raw}` |
| `tools/iac/cfn_gap_detectors.py` | Detectores estáticos para recursos CFN: `detect_cfn_missing_autoscaling`, `detect_cfn_single_az`, `detect_cfn_undersized_instance` |
| `tests/unit/test_cfn_detectors.py` | Testes unitários dos detectores CFN (mínimo 12 testes) |
| `tests/unit/test_cfn_file_reader.py` | Testes do file reader CFN (mínimo 8 testes) |

## Arquivos existentes a modificar

| Arquivo | O que muda |
|---------|-----------|
| `tools/iac/file_reader.py` | `read_iac_files()` chama `cfn_file_reader.read_cfn_files()` quando encontra `template.json` ou arquivos com `AWSTemplateFormatVersion` no conteúdo |
| `tools/iac/gap_detectors.py` | `detect_all_gaps()` chama os detectores CFN quando `iac_files` contém entradas `type == "cloudformation"` |
| `tools/iac/iac_patcher.py` | `_resolve_strategy()` e `_generate_attribute_patches()` adicionam suporte ao formato CFN (atributos em `Properties`, não inline HCL) |
| `agents/iac_analyzer.py` | Sem mudança de lógica; o fluxo já passa `iac_files` para os detectores |

## Fluxo de dados

```
project_path/
  ├── infra/
  │   ├── main.tf          → type: "terraform"
  │   ├── template.yaml    → type: "cloudformation"   ← novo
  │   └── k8s/deploy.yaml  → type: "kubernetes"

read_iac_files()
  → cfn_file_reader.read_cfn_files(path)
      → parse YAML/JSON
      → identifica pela chave "AWSTemplateFormatVersion" ou "Resources"
      → retorna [{path, type:"cloudformation", parsed:{Resources:{...}}, raw}]

detect_infra_gaps(iac_files, nfr)
  → cfn_gap_detectors.detect_cfn_missing_autoscaling(cfn_files, nfr)
  → cfn_gap_detectors.detect_cfn_single_az(cfn_files, nfr)
  → cfn_gap_detectors.detect_cfn_undersized_instance(cfn_files, nfr)
  → retorna List[InfraGap]
```

## Decisões técnicas

- **Parser**: `PyYAML` (já dependência) para YAML; `json` stdlib para JSON — sem novas dependências
- **Identificação do tipo CFN**: presença da chave `AWSTemplateFormatVersion` ou `Resources` com recursos `AWS::*`
- **Formato de resource_name no InfraGap**: `"LogicalId/ResourceType"` — ex: `"MyRDSInstance/AWS::RDS::DBInstance"`
- **Patches CFN**: modificar atributo dentro de `Properties` do recurso, não inline HCL; `_resolve_strategy()` deve tratar o prefixo `AWS::` para identificar formato CFN
- **Limitação conhecida**: `yaml.dump()` perde comentários (mesma limitação do K8s patcher atual)

## Critérios de aceitação

- [ ] Arquivos `.json`/`.yaml` com `AWSTemplateFormatVersion` são reconhecidos como CloudFormation
- [ ] `AWS::RDS::DBInstance` com `MultiAZ: false` gera `InfraGap` categoria `SINGLE_AZ`
- [ ] `AWS::ECS::Service` sem `AWS::ApplicationAutoScaling::ScalableTarget` gera gap `MISSING_AUTOSCALING`
- [ ] `AWS::EC2::Instance` com `InstanceType: t2.micro` e NFR `max_rps >= 500` gera gap `UNDERSIZED_INSTANCE`
- [ ] Patch `MultiAZ: false → true` é aplicado corretamente
- [ ] Arquivos Terraform e K8s continuam funcionando normalmente (regressão zero)
- [ ] `pytest tests/unit/test_cfn_detectors.py` passa

## Testes

```python
# tests/unit/test_cfn_detectors.py
# - test_detect_rds_single_az_cfn_yaml
# - test_detect_rds_single_az_cfn_json
# - test_rds_multiaz_true_no_gap
# - test_detect_ecs_missing_autoscaling_cfn
# - test_ecs_with_autoscaling_no_gap
# - test_detect_undersized_ec2_instance_cfn
# - test_ec2_adequate_instance_no_gap
# - test_cfn_identification_by_key
# - test_cfn_identification_by_resources_prefix
# - test_terraform_files_not_confused_with_cfn
# - test_k8s_files_not_confused_with_cfn
# - test_empty_cfn_template_no_crash
```
