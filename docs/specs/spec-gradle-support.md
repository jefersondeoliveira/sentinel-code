# Spec: Suporte a Gradle além de Maven

## Status
Fase 4 — [ ] Pendente

## Contexto
O `Code Analyzer` atual usa `tools/java/file_reader.py` para ler arquivos Java e
arquivos de configuração (`application.properties`, `application.yml`, `pom.xml`).
Projetos Java modernos frequentemente usam Gradle (`build.gradle`, `build.gradle.kts`)
em vez de Maven. Sem suporte a Gradle, o detector de `CONNECTION_POOL` pode falhar
ao ler configurações de dependências e o relatório não identifica o build system.

## Objetivo
Detectar projetos Gradle, ler `build.gradle`/`build.gradle.kts` para identificar
dependências relevantes (Spring Boot, HikariCP, JPA) e incluir essa informação
no contexto do Code Analyzer.

## Escopo

### Inclui
- Detecção automática do build system (Maven vs Gradle) pelo arquivo presente
- Leitura de `build.gradle` (Groovy DSL) e `build.gradle.kts` (Kotlin DSL)
- Extração de dependências relevantes para performance (Spring Data JPA, HikariCP, cache)
- Campo `build_system` no contexto de análise (para enriquecimento LLM)
- Leitura de `gradle.properties` (equivalente ao `application.properties` para config de build)

### Não inclui
- Execução de tarefas Gradle (sem `gradle build` ou `gradle test`)
- Suporte a multi-módulo Gradle (somente projeto raiz na primeira versão)
- Parse completo de Groovy/Kotlin DSL (análise textual/regex, não AST)

## Arquitetura

Extensão do `tools/java/file_reader.py`. Função `read_java_files()` já retorna
lista de dicts com conteúdo de arquivos. Adicionar leitura de `build.gradle*`
e incluir metadados do build system nos dicts retornados.

```
read_java_files(project_path)
  → detect_build_system(project_path)  ← novo
      → "maven"  se pom.xml presente
      → "gradle" se build.gradle presente
      → "unknown" caso contrário
  → read_build_config(project_path, build_system)  ← novo
      → retorna {build_system, dependencies, plugins}
```

## Mudanças no AgentState (`models/state.py`)

Adicionar campo:
```python
build_system: str  # "maven", "gradle", "unknown" — não acumulativo
```

## Novos arquivos

| Arquivo | Responsabilidade |
|---------|-----------------|
| `tools/java/build_reader.py` | `detect_build_system(path) -> str`, `read_gradle_config(path) -> dict`, `extract_gradle_dependencies(content) -> List[str]` |
| `tests/unit/test_build_reader.py` | Testes com fixtures de build.gradle (mínimo 10 testes) |

## Arquivos existentes a modificar

| Arquivo | O que muda |
|---------|-----------|
| `tools/java/file_reader.py` | `read_java_files()` chama `build_reader.detect_build_system()` e inclui config do Gradle nos arquivos retornados |
| `agents/code_analyzer.py` | Nó `read_files_node` popula `state["build_system"]` com o resultado de `detect_build_system()` |
| `models/state.py` | Adicionar `build_system: str` |
| `agents/reporter.py` | Exibir `build_system` no relatório (seção de metadados do projeto) |

## Fluxo de dados

```
project_path/
  ├── build.gradle          ← detectado
  ├── gradle.properties
  ├── src/main/java/...
  └── src/main/resources/
      └── application.yml

detect_build_system() → "gradle"

read_gradle_config() → {
  "build_system": "gradle",
  "dependencies": [
    "org.springframework.boot:spring-boot-starter-data-jpa",
    "com.zaxxer:HikariCP",
  ],
  "plugins": ["org.springframework.boot", "java"],
  "java_version": "17",
}

# Este contexto é passado ao prompt de enriquecimento LLM
# para que o modelo saiba que é Gradle, não Maven
```

## Decisões técnicas

- **Parser Gradle**: análise textual via regex (não parser Groovy/Kotlin completo)
  - Dependência Groovy: `implementation 'group:artifact:version'`
  - Dependência Kotlin DSL: `implementation("group:artifact:version")`
- **Prioridade**: se ambos `pom.xml` e `build.gradle` existirem, Maven tem prioridade
- **Sem execução**: não rodar `gradle dependencies` — análise estática apenas
- **Encoding**: UTF-8 com fallback latin-1 (igual ao file_reader atual)

## Critérios de aceitação

- [ ] Projeto com `build.gradle` tem `build_system = "gradle"` no AgentState
- [ ] Projeto com `pom.xml` tem `build_system = "maven"` (sem regressão)
- [ ] Dependências Spring Data JPA e HikariCP são extraídas do `build.gradle`
- [ ] Projeto sem nenhum build file tem `build_system = "unknown"`
- [ ] Relatório HTML exibe o build system detectado
- [ ] `pytest tests/unit/test_build_reader.py` passa

## Testes

```python
# tests/unit/test_build_reader.py
# - test_detect_maven_from_pom_xml
# - test_detect_gradle_from_build_gradle
# - test_detect_gradle_kts_from_build_gradle_kts
# - test_detect_unknown_without_build_file
# - test_maven_priority_when_both_present
# - test_extract_groovy_dependencies
# - test_extract_kotlin_dsl_dependencies
# - test_extract_spring_boot_plugin
# - test_gradle_properties_read
# - test_empty_build_gradle_no_crash
```
