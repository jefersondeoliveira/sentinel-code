# Spec: Suporte a Helm Charts

## Status
Fase 4 — [ ] Pendente

## Contexto
Helm é o gerenciador de pacotes padrão para Kubernetes. Charts Helm são templates Go
que geram manifests K8s em tempo de execução. O SentinelCode já analisa manifests K8s
estáticos (`.yaml`), mas não entende charts Helm — ignorando toda a infraestrutura
K8s gerenciada via Helm em projetos que não commitam os manifests renderizados.

## Objetivo
Renderizar charts Helm locais para manifests K8s estáticos e analisá-los com os
detectores K8s existentes (`detect_k8s_missing_resource_limits`, `detect_k8s_missing_probes`).

## Escopo

### Inclui
- Detecção de diretórios Helm (contém `Chart.yaml`)
- Renderização local via `helm template` (CLI do Helm deve estar instalado)
- Análise dos manifests renderizados pelos detectores K8s existentes
- Identificação do arquivo de origem como `<chart-name>/templates/<file>` no `InfraGap`
- Suporte a `values.yaml` padrão (sem override de values customizados na primeira versão)

### Não inclui
- Download de charts de repositórios Helm remotos (somente charts locais)
- Override de values via `--set` ou `-f values-prod.yaml`
- Análise de hooks Helm (`pre-install`, `post-upgrade`)
- Validação de schema do `values.yaml`

## Arquitetura

Extensão do `IaC File Reader`. Quando `read_iac_files()` encontra um diretório
com `Chart.yaml`, invoca `helm template` e usa a saída como entrada para os
detectores K8s existentes — sem novo agente.

```
read_iac_files()
  → detecta Chart.yaml
  → helm_reader.render_chart(chart_dir) → List[str] (yamls)
  → cada yaml é tratado como iac_file com type="kubernetes"
  → detect_infra_gaps() usa detectores K8s existentes
```

## Mudanças no AgentState (`models/state.py`)
Nenhuma mudança. `iac_files` já suporta qualquer dict com `{path, type, parsed, raw}`.

## Novos arquivos

| Arquivo | Responsabilidade |
|---------|-----------------|
| `tools/iac/helm_reader.py` | `find_helm_charts(path) -> List[Path]`, `render_chart(chart_dir) -> List[dict]` (executa `helm template`, faz parse do output YAML multi-documento) |
| `tests/unit/test_helm_reader.py` | Testes com mock de subprocess e charts de exemplo (mínimo 10 testes) |

## Arquivos existentes a modificar

| Arquivo | O que muda |
|---------|-----------|
| `tools/iac/file_reader.py` | `read_iac_files()` chama `helm_reader.find_helm_charts()` e incorpora os manifests renderizados em `iac_files` |
| `requirements.txt` | Sem nova dependência Python (Helm é CLI externo) |

## Fluxo de dados

```
project_path/
  ├── helm/
  │   ├── Chart.yaml           ← detectado
  │   ├── values.yaml
  │   └── templates/
  │       ├── deployment.yaml  ← template Go
  │       └── service.yaml

helm template ./helm/ → multi-document YAML string

yaml.safe_load_all(output) → [
  {apiVersion: apps/v1, kind: Deployment, ...},
  {apiVersion: v1, kind: Service, ...},
]

iac_files.append({
  "path": "helm/templates/deployment.yaml",
  "type": "kubernetes",
  "parsed": {apiVersion: ..., kind: Deployment, ...},
  "raw": "...",
  "source": "helm_rendered",
})
```

## Decisões técnicas

- **Pré-requisito externo**: `helm` CLI na `PATH`. Se não disponível, o módulo emite warning e retorna lista vazia (sem falha do pipeline)
- **Output multi-documento**: `helm template` retorna múltiplos YAMLs separados por `---`; usar `yaml.safe_load_all()`
- **Identificação do arquivo de origem**: prefixar o path com `[helm:<chart-name>]` para o relatório
- **Segurança**: não executar `helm install` nem `helm upgrade` — apenas `helm template` (operação local, sem acesso à API do cluster)
- **Subprocess**: usar `subprocess.run(["helm", "template", chart_dir], capture_output=True, timeout=30)`

## Critérios de aceitação

- [ ] Diretório com `Chart.yaml` é reconhecido como chart Helm
- [ ] `helm template` é executado e o output é parseado
- [ ] Deployment sem `resources` gera `InfraGap K8s Resource Limits`
- [ ] Deployment sem probes gera `InfraGap K8s Health Check`
- [ ] Ausência do `helm` CLI não interrompe o pipeline
- [ ] Manifests K8s estáticos continuam sendo detectados normalmente
- [ ] `pytest tests/unit/test_helm_reader.py` passa (com mock de subprocess)

## Testes

```python
# tests/unit/test_helm_reader.py
# - test_find_helm_charts_detects_chart_yaml
# - test_find_helm_charts_ignores_non_helm_dirs
# - test_render_chart_returns_parsed_yamls (mock subprocess)
# - test_render_chart_handles_multidoc_yaml
# - test_helm_not_installed_returns_empty_list
# - test_helm_template_error_returns_empty_list
# - test_rendered_charts_have_type_kubernetes
# - test_rendered_charts_source_marked_as_helm
# - test_static_k8s_files_not_affected
# - test_chart_with_empty_templates_no_crash
```
