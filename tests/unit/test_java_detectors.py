"""
Testes dos novos detectores Java — Fase 3.

Rode com:
    pytest tests/unit/test_java_detectors.py -v
"""

import pytest
from tools.java.issue_detectors import (
    detect_pagination_issues,
    detect_lazy_loading,
    detect_thread_blocking,
    detect_missing_index,
)
from models.issue import IssueCategory, Severity


def _file(content: str, path: str = "src/main/java/Example.java") -> list:
    """Helper: cria lista de arquivos Java para os detectores."""
    return [{"path": path, "content": content, "tree": None}]


# =============================================================================
# detect_pagination_issues
# =============================================================================

class TestDetectPaginationIssues:

    def test_detects_findall_without_pageable(self):
        content = (
            "@Repository\n"
            "public interface UserRepo extends JpaRepository<User, Long> {\n"
            "    List<User> findAll();\n"
            "}\n"
        )
        issues = detect_pagination_issues(_file(content))
        assert len(issues) >= 1
        assert issues[0].category == IssueCategory.PAGINATION
        assert issues[0].severity == Severity.HIGH

    def test_no_issue_when_page_with_pageable(self):
        content = (
            "@Repository\n"
            "public interface UserRepo extends JpaRepository<User, Long> {\n"
            "    Page<User> findAll(Pageable pageable);\n"
            "}\n"
        )
        issues = detect_pagination_issues(_file(content))
        assert len(issues) == 0

    def test_detects_list_findby_without_pageable(self):
        content = (
            "@Repository\n"
            "public interface UserRepo extends JpaRepository<User, Long> {\n"
            "    List<User> findByStatus(String status);\n"
            "}\n"
        )
        issues = detect_pagination_issues(_file(content))
        assert len(issues) >= 1
        assert issues[0].category == IssueCategory.PAGINATION

    def test_no_issue_on_non_repository_file(self):
        content = (
            "public class UserService {\n"
            "    public void process() { repo.findAll(); }\n"
            "}\n"
        )
        issues = detect_pagination_issues(_file(content))
        assert len(issues) == 0

    def test_no_issue_on_empty_list(self):
        assert detect_pagination_issues([]) == []

    def test_no_issue_when_page_return_type(self):
        content = (
            "@Repository\n"
            "public interface UserRepo extends JpaRepository<User, Long> {\n"
            "    Page<User> findByStatus(String status, Pageable pageable);\n"
            "}\n"
        )
        issues = detect_pagination_issues(_file(content))
        assert len(issues) == 0


# =============================================================================
# detect_lazy_loading
# =============================================================================

class TestDetectLazyLoading:

    def test_detects_onetomany_without_json_annotation(self):
        content = (
            "@Entity\n"
            "public class User {\n"
            "    @OneToMany\n"
            "    private List<Order> orders;\n"
            "}\n"
        )
        issues = detect_lazy_loading(_file(content))
        assert len(issues) >= 1
        assert issues[0].category == IssueCategory.LAZY_LOADING
        assert issues[0].severity == Severity.HIGH

    def test_no_issue_with_json_managed_reference(self):
        content = (
            "@Entity\n"
            "public class User {\n"
            "    @OneToMany\n"
            "    @JsonManagedReference\n"
            "    private List<Order> orders;\n"
            "}\n"
        )
        issues = detect_lazy_loading(_file(content))
        assert len(issues) == 0

    def test_no_issue_with_fetch_eager(self):
        content = (
            "@Entity\n"
            "public class User {\n"
            "    @OneToMany(fetch = FetchType.EAGER)\n"
            "    private List<Order> orders;\n"
            "}\n"
        )
        issues = detect_lazy_loading(_file(content))
        assert len(issues) == 0

    def test_detects_manytomany(self):
        content = (
            "@Entity\n"
            "public class Role {\n"
            "    @ManyToMany\n"
            "    private List<User> users;\n"
            "}\n"
        )
        issues = detect_lazy_loading(_file(content))
        assert len(issues) >= 1
        assert issues[0].category == IssueCategory.LAZY_LOADING

    def test_no_issue_on_non_entity_file(self):
        content = (
            "public class UserService {\n"
            "    @OneToMany\n"
            "    private List<Order> orders;\n"
            "}\n"
        )
        issues = detect_lazy_loading(_file(content))
        assert len(issues) == 0

    def test_no_issue_on_empty_list(self):
        assert detect_lazy_loading([]) == []


# =============================================================================
# detect_thread_blocking
# =============================================================================

class TestDetectThreadBlocking:

    def test_detects_thread_sleep(self):
        content = (
            "public class Svc {\n"
            "    public void call() throws InterruptedException {\n"
            "        Thread.sleep(1000);\n"
            "    }\n"
            "}\n"
        )
        issues = detect_thread_blocking(_file(content))
        assert len(issues) >= 1
        assert issues[0].category == IssueCategory.THREAD_BLOCKING
        assert issues[0].severity == Severity.CRITICAL

    def test_detects_future_get(self):
        content = (
            "public class Svc {\n"
            "    public String call() throws Exception {\n"
            "        return future.get();\n"
            "    }\n"
            "}\n"
        )
        issues = detect_thread_blocking(_file(content))
        assert len(issues) >= 1
        assert issues[0].category == IssueCategory.THREAD_BLOCKING

    def test_detects_reactive_block(self):
        content = (
            "public class Svc {\n"
            "    public String call() {\n"
            "        return webClient.get().retrieve().bodyToMono(String.class).block();\n"
            "    }\n"
            "}\n"
        )
        issues = detect_thread_blocking(_file(content))
        assert len(issues) >= 1

    def test_detects_future_join(self):
        content = (
            "public class Svc {\n"
            "    public String call() {\n"
            "        return CompletableFuture.supplyAsync(() -> \"x\").join();\n"
            "    }\n"
            "}\n"
        )
        issues = detect_thread_blocking(_file(content))
        assert len(issues) >= 1

    def test_ignores_comment_lines(self):
        content = (
            "public class Svc {\n"
            "    // Thread.sleep(1000); — não usar!\n"
            "    public void call() {}\n"
            "}\n"
        )
        issues = detect_thread_blocking(_file(content))
        assert len(issues) == 0

    def test_no_issue_on_clean_code(self):
        content = (
            "public class Svc {\n"
            "    public void call() {\n"
            "        doSomething();\n"
            "    }\n"
            "}\n"
        )
        issues = detect_thread_blocking(_file(content))
        assert len(issues) == 0

    def test_no_issue_on_empty_list(self):
        assert detect_thread_blocking([]) == []


# =============================================================================
# detect_missing_index
# =============================================================================

class TestDetectMissingIndex:

    def test_detects_findby_without_index(self):
        content = (
            "@Repository\n"
            "public interface UserRepo extends JpaRepository<User, Long> {\n"
            "    List<User> findByEmail(String email);\n"
            "}\n"
        )
        issues = detect_missing_index(_file(content))
        assert len(issues) >= 1
        assert issues[0].category == IssueCategory.MISSING_INDEX
        assert issues[0].severity == Severity.HIGH

    def test_no_issue_when_index_declared(self):
        # Entidade com @Index e repositório com findByEmail — sem issue
        files = [
            {
                "path": "User.java",
                "content": (
                    "@Table(indexes = {@Index(columnList = \"email\")})\n"
                    "@Entity\n"
                    "public class User {}\n"
                ),
                "tree": None,
            },
            {
                "path": "UserRepo.java",
                "content": (
                    "@Repository\n"
                    "public interface UserRepo extends JpaRepository<User, Long> {\n"
                    "    List<User> findByEmail(String email);\n"
                    "}\n"
                ),
                "tree": None,
            },
        ]
        issues = detect_missing_index(files)
        assert len(issues) == 0

    def test_detects_compound_findby(self):
        content = (
            "@Repository\n"
            "public interface UserRepo extends JpaRepository<User, Long> {\n"
            "    List<User> findByUsernameAndStatus(String username, String status);\n"
            "}\n"
        )
        issues = detect_missing_index(_file(content))
        # Detecta 'username' e/ou 'status' sem índice
        assert len(issues) >= 1

    def test_no_issue_on_non_repository_file(self):
        content = (
            "public class UserService {\n"
            "    public List<User> findByEmail(String email) { return null; }\n"
            "}\n"
        )
        issues = detect_missing_index(_file(content))
        assert len(issues) == 0

    def test_no_issue_on_empty_list(self):
        assert detect_missing_index([]) == []
