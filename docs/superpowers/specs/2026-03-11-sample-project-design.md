# Design: sample_project — E-commerce com problemas intencionais

**Data:** 2026-03-11
**Objetivo:** Criar `sample_project/` com um projeto Java fictício de loja online que acione **todos os 7 detectores Java** e **todos os 5 detectores IaC** do SentinelCode, servindo como demo e suite de teste manual.

---

## Abordagem

E-commerce mínimo com `User`, `Order`, `Product`. Arquivos Java simples (não compiláveis, sem build tool), config yml, Terraform e K8s. Código propositalmente quebrado, com comentários `# PROBLEMA:` explicando cada issue intencional.

---

## Estrutura de arquivos

```
sample_project/
├── src/main/java/com/example/store/
│   ├── model/
│   │   ├── User.java       — LAZY_LOADING, base para MISSING_INDEX
│   │   ├── Order.java      — LAZY_LOADING (2º caso)
│   │   └── Product.java    — base para MISSING_INDEX
│   ├── repository/
│   │   ├── UserRepository.java    — MISSING_INDEX, PAGINATION
│   │   ├── OrderRepository.java   — PAGINATION, MISSING_INDEX
│   │   └── ProductRepository.java — MISSING_INDEX
│   └── service/
│       ├── OrderService.java   — N+1, THREAD_BLOCKING
│       ├── ProductService.java — MISSING_CACHE (2 endpoints)
│       └── UserService.java    — THREAD_BLOCKING (sleep + block)
├── src/main/resources/
│   └── application.yml     — CONNECTION_POOL (pool-size=5)
├── terraform/
│   ├── main.tf             — SINGLE_AZ, MISSING_AUTOSCALING, UNDERSIZED_INSTANCE
│   └── variables.tf
└── k8s/
    └── deployment.yaml     — K8S_MISSING_RESOURCE_LIMITS, K8S_MISSING_PROBES, MISSING_AUTOSCALING
```

---

## Mapeamento detector → arquivo → padrão exato

| Detector | Arquivo | Padrão que aciona |
|---|---|---|
| N+1 | `OrderService.java` | `for (Order o : orders) { itemRepo.findByOrder(o); }` |
| MISSING_CACHE | `ProductService.java` | `@GetMapping("/products")` + `getAllProducts()` sem `@Cacheable` |
| CONNECTION_POOL | `application.yml` | `maximum-pool-size: 5` |
| PAGINATION | `UserRepository.java`, `OrderRepository.java` | declaração de interface `List<X> findAll();` sem `Pageable` (detector exige `@Repository`/`JpaRepository` no arquivo) |
| LAZY_LOADING | `User.java`, `Order.java` | `@OneToMany` / `@ManyToMany` sem EAGER e sem @Json* |
| THREAD_BLOCKING | `OrderService.java`, `UserService.java` | `future.get()`, `Thread.sleep()`, `.block()` |
| MISSING_INDEX | `UserRepository.java`, `OrderRepository.java`, `ProductRepository.java` | `findByEmail`, `findByStatus`, `findByCategory` — entidades `User.java`/`Product.java` NÃO devem conter `@Index` ou `@Table(indexes=...)` para `email`, `status`, `category` |
| SINGLE_AZ | `terraform/main.tf` | `multi_az = false` em `aws_db_instance` |
| MISSING_AUTOSCALING | `terraform/main.tf` | `aws_ecs_service` sem `aws_appautoscaling_target` |
| UNDERSIZED_INSTANCE | `terraform/main.tf` | `aws_instance "app"` com `instance_type = "t3.small"` (verificar com `--nfr '{"max_rps":2000}'`) |
| K8S_MISSING_RESOURCE_LIMITS | `k8s/deployment.yaml` | containers sem `resources` block |
| K8S_MISSING_PROBES | `k8s/deployment.yaml` | containers sem `livenessProbe`/`readinessProbe` |

---

## Verificação

```bash
# Só Java (7 issues)
python main.py --path ./sample_project/ --dry-run --no-iac

# Tudo incluindo IaC (13 issues: 7 Java + 6 IaC)
# UNDERSIZED_INSTANCE requer max_rps > 1000 (capacidade do t3.small)
python main.py --path ./sample_project/ --dry-run --nfr '{"max_rps": 2000}'
```

Resultado esperado: relatório HTML com **13 issues** (7 Java + 6 IaC):
- Java: N+1, MISSING_CACHE, CONNECTION_POOL, PAGINATION, LAZY_LOADING, THREAD_BLOCKING, MISSING_INDEX
- IaC: SINGLE_AZ, MISSING_AUTOSCALING (ECS), MISSING_AUTOSCALING (K8s Deployment sem HPA), UNDERSIZED_INSTANCE, K8S_MISSING_RESOURCE_LIMITS, K8S_MISSING_PROBES

> `variables.tf`: arquivo auxiliar sem requisitos de detecção, contém apenas variáveis de região e nome do projeto.
