import re
from typing import List
from models.issue import Issue, Severity, IssueCategory


# =============================================================================
# DETECTOR 1 — N+1 Query
# =============================================================================

def detect_n_plus_one(java_files: List[dict]) -> List[Issue]:
    """
    Detecta padrão N+1: chamadas a repositórios JPA dentro de loops.

    Estratégia:
    1. Para cada arquivo, analisa a AST (se disponível) procurando
       MethodInvocation dentro de ForStatement / EnhancedForStatement.
    2. Fallback: busca textual por padrões comuns quando a AST falhou.

    Sinais de N+1 no código Java:
    - loop (for/forEach) com chamada a método que termina em
      Repository, Service, DAO, ou nomes como findBy*, getBy*, load*
    - @Transactional ausente em métodos que iteram entidades com lazy relations
    """
    issues = []

    for file in java_files:
        content = file["content"]
        tree = file["tree"]

        # --- Estratégia 1: análise via AST ---
        if tree is not None:
            ast_issues = _detect_n1_via_ast(tree, file["path"], content)
            issues.extend(ast_issues)
            if ast_issues:
                continue  # Já encontrou via AST, não precisa do fallback

        # --- Estratégia 2: análise textual (fallback) ---
        text_issues = _detect_n1_via_text(content, file["path"])
        issues.extend(text_issues)

    return issues


def _detect_n1_via_ast(tree, file_path: str, content: str) -> List[Issue]:
    """
    Navega a AST procurando chamadas a repositórios dentro de loops.
    """
    import javalang
    issues = []
    lines = content.splitlines()

    try:
        for _, loop_node in tree.filter(javalang.tree.ForStatement):
            repo_calls = _find_repo_calls_in_node(loop_node)
            for call in repo_calls:
                # Tenta encontrar a linha aproximada pelo nome do método
                line_num = _find_line(lines, call)
                issues.append(Issue(
                    category=IssueCategory.N_PLUS_ONE,
                    severity=Severity.CRITICAL,
                    file_path=file_path,
                    line=line_num,
                    root_cause=(
                        f"Chamada a '{call}' encontrada dentro de um loop for. "
                        "Isso gera uma query ao banco para cada iteração (N+1)."
                    ),
                    evidence=f"Chamada: {call}(...) dentro de for loop",
                    suggestion=(
                        "Use JOIN FETCH na query JPQL ou @EntityGraph na entidade "
                        "para carregar os dados relacionados em uma única query."
                    ),
                ))

        # Também verifica forEach (lambda)
        for _, method_node in tree.filter(javalang.tree.MethodInvocation):
            if method_node.member == "forEach":
                # Verifica se o corpo do forEach tem chamadas de repositório
                # Isso é uma heurística — falsos positivos são possíveis
                pass  # Expansão futura

    except Exception:
        pass  # AST incompleta ou inválida, o fallback textual cobre

    return issues


def _find_repo_calls_in_node(node) -> List[str]:
    """
    Recursivamente procura MethodInvocations dentro de um nó da AST
    que pareçam chamadas a repositórios JPA.
    """
    import javalang
    repo_patterns = re.compile(
        r"(find|get|load|fetch|query|select|count|exists)",
        re.IGNORECASE
    )
    calls = []

    try:
        for _, child in node.filter(javalang.tree.MethodInvocation):
            if child.member and repo_patterns.search(child.member):
                calls.append(child.member)
    except Exception:
        pass

    return calls


def _detect_n1_via_text(content: str, file_path: str) -> List[Issue]:
    """
    Fallback textual: procura padrões de N+1 quando a AST não está disponível.
    Menos preciso, mas cobre mais casos de código não-standard.
    """
    issues = []
    lines = content.splitlines()

    # Detecta blocos: for(...) { ... repository.find*(...) }
    in_loop = False
    loop_depth = 0
    loop_start_line = 0

    for i, line in enumerate(lines, start=1):
        stripped = line.strip()

        # Entrada em loop
        if re.search(r'\bfor\s*\(', stripped) or re.search(r'\.forEach\s*\(', stripped):
            in_loop = True
            loop_depth = 0
            loop_start_line = i

        if in_loop:
            loop_depth += stripped.count("{") - stripped.count("}")

            # Procura chamada a repositório/service dentro do loop
            if re.search(
                r'\.(find|get|load|fetch|query|count|exists)\w*\s*\(',
                stripped,
                re.IGNORECASE
            ):
                issues.append(Issue(
                    category=IssueCategory.N_PLUS_ONE,
                    severity=Severity.CRITICAL,
                    file_path=file_path,
                    line=i,
                    root_cause=(
                        "Chamada a método de busca encontrada dentro de loop. "
                        "Provável N+1: uma query por iteração."
                    ),
                    evidence=stripped[:120],
                    suggestion=(
                        "Colete os IDs antes do loop e use findAllById() ou "
                        "reescreva a query com JOIN FETCH."
                    ),
                ))

            # Sai do loop quando a profundidade volta a 0
            if loop_depth <= 0 and i > loop_start_line:
                in_loop = False

    return issues


# =============================================================================
# DETECTOR 2 — Cache Ausente
# =============================================================================

def detect_missing_cache(java_files: List[dict]) -> List[Issue]:
    """
    Detecta endpoints GET que retornam dados potencialmente cacheáveis
    mas não têm @Cacheable ou qualquer anotação de cache.

    Heurística: métodos com @GetMapping cujo nome sugere dados estáticos
    (getAll, findAll, list, catalog, categories, config, settings...)
    e que não têm @Cacheable, @CacheResult, ou uso de CacheManager.
    """
    issues = []

    # Nomes de métodos que sugerem dados raramente alterados
    cacheable_name_pattern = re.compile(
        r'(getAll|findAll|listAll|list|catalog|categor|config|settings|'
        r'product|menu|reference|lookup|master)',
        re.IGNORECASE
    )

    cache_annotations = {"@Cacheable", "@CacheResult", "@CacheEvict", "CacheManager"}

    for file in java_files:
        content = file["content"]
        lines = content.splitlines()

        i = 0
        while i < len(lines):
            line = lines[i].strip()

            # Encontrou um @GetMapping
            if "@GetMapping" in line or "@RequestMapping" in line:
                # Coleta o bloco do método (próximas ~10 linhas)
                block = "\n".join(lines[i:min(i + 15, len(lines))])

                # Verifica se parece um endpoint de leitura com nome cacheável
                has_cacheable_name = bool(cacheable_name_pattern.search(block))
                has_cache_annotation = any(ann in block for ann in cache_annotations)

                if has_cacheable_name and not has_cache_annotation:
                    # Tenta extrair o nome do método
                    method_match = re.search(r'(?:public|private|protected)\s+\S+\s+(\w+)\s*\(', block)
                    method_name = method_match.group(1) if method_match else "desconhecido"

                    issues.append(Issue(
                        category=IssueCategory.MISSING_CACHE,
                        severity=Severity.HIGH,
                        file_path=file["path"],
                        line=i + 1,
                        root_cause=(
                            f"Método '{method_name}' parece retornar dados de leitura "
                            "mas não tem @Cacheable. Cada chamada gera uma query ao banco."
                        ),
                        evidence=f"@GetMapping sem @Cacheable em: {method_name}()",
                        suggestion=(
                            f"Adicione @Cacheable(value = \"{method_name}\") ao método "
                            "e configure um CacheManager com Redis ou Caffeine no projeto."
                        ),
                    ))
            i += 1

    return issues


# =============================================================================
# DETECTOR 3 — Connection Pool Subdimensionado
# =============================================================================

def detect_connection_pool(app_configs: dict) -> List[Issue]:
    """
    Analisa application.properties / application.yml procurando por
    configurações de HikariCP ausentes ou subdimensionadas.

    Por que isso importa:
    O padrão do HikariCP é maximum-pool-size=10. Em APIs sob carga real,
    threads ficam em fila esperando uma conexão livre, causando timeouts
    e latência alta mesmo com o banco ocioso.

    Configuração recomendada:
    - maximum-pool-size: entre 20-50 (depende do número de CPUs e carga)
    - connection-timeout: 30000ms (padrão é ok)
    - idle-timeout: 600000ms
    - max-lifetime: 1800000ms
    """
    issues = []

    all_config_content = "\n".join(app_configs.values())

    if not all_config_content.strip():
        # Arquivo existe mas está vazio — mesma situação: sem config de pool
        issues.append(Issue(
            category=IssueCategory.CONNECTION_POOL,
            severity=Severity.HIGH,
            file_path="src/main/resources/application.properties",
            root_cause=(
                "Nenhuma configuração de HikariCP encontrada. "
                "O padrão de 10 conexões é insuficiente para APIs sob carga."
            ),
            evidence="application.properties está vazio ou sem spring.datasource.hikari.*",
            suggestion=(
                "Adicione ao application.yml:\n"
                "spring:\n"
                "  datasource:\n"
                "    hikari:\n"
                "      maximum-pool-size: 20\n"
                "      minimum-idle: 5\n"
                "      connection-timeout: 30000\n"
                "      idle-timeout: 600000\n"
                "      max-lifetime: 1800000"
            ),
        ))
        return issues

    # Verifica se há qualquer configuração explícita de pool
    has_pool_config = bool(re.search(
        r'(hikari|maximum-pool-size|minimumIdle|connectionTimeout)',
        all_config_content,
        re.IGNORECASE
    ))

    if not has_pool_config:
        issues.append(Issue(
            category=IssueCategory.CONNECTION_POOL,
            severity=Severity.HIGH,
            file_path="src/main/resources/application.properties",
            root_cause=(
                "Nenhuma configuração de HikariCP encontrada. "
                "O padrão de 10 conexões é insuficiente para APIs sob carga."
            ),
            evidence="Ausência de spring.datasource.hikari.* no application.properties/yml",
            suggestion=(
                "Adicione ao application.yml:\n"
                "spring:\n"
                "  datasource:\n"
                "    hikari:\n"
                "      maximum-pool-size: 20\n"
                "      minimum-idle: 5\n"
                "      connection-timeout: 30000\n"
                "      idle-timeout: 600000\n"
                "      max-lifetime: 1800000"
            ),
        ))
        return issues

    # Se tem config, verifica se o pool-size está baixo demais
    pool_size_match = re.search(
        r'maximum-pool-size[=:\s]+(\d+)',
        all_config_content,
        re.IGNORECASE
    )
    if pool_size_match:
        pool_size = int(pool_size_match.group(1))
        if pool_size < 15:
            issues.append(Issue(
                category=IssueCategory.CONNECTION_POOL,
                severity=Severity.MEDIUM,
                file_path="src/main/resources/application.properties",
                root_cause=(
                    f"maximum-pool-size={pool_size} está abaixo do recomendado. "
                    "Com menos de 15 conexões, picos de tráfego causam fila de threads."
                ),
                evidence=f"maximum-pool-size={pool_size}",
                suggestion=(
                    f"Aumente maximum-pool-size para pelo menos 20. "
                    f"Fórmula base: (número de CPUs * 2) + número de discos."
                ),
            ))

    return issues