"""
Testes do módulo de observabilidade LangSmith — Spec Driven.

Rode com: pytest tests/unit/test_tracer.py -v
"""

import os
import pytest


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture(autouse=True)
def clean_env():
    """Limpa variáveis de ambiente do LangSmith antes de cada teste."""
    vars_to_clean = [
        "LANGCHAIN_TRACING_V2",
        "LANGCHAIN_API_KEY",
        "LANGCHAIN_PROJECT",
        "LANGCHAIN_ENDPOINT",
    ]
    original = {k: os.environ.get(k) for k in vars_to_clean}
    for k in vars_to_clean:
        os.environ.pop(k, None)
    yield
    for k, v in original.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


@pytest.fixture
def settings_disabled():
    from config import Settings
    return Settings(
        openai_api_key="sk-fake",
        langchain_tracing_v2=False,
        langchain_api_key="",
        langchain_project="sentinel-code",
    )


@pytest.fixture
def settings_enabled():
    from config import Settings
    return Settings(
        openai_api_key="sk-fake",
        langchain_tracing_v2=True,
        langchain_api_key="ls__fake_key_for_testing",
        langchain_project="sentinel-code",
    )


@pytest.fixture
def settings_no_key():
    from config import Settings
    return Settings(
        openai_api_key="sk-fake",
        langchain_tracing_v2=True,
        langchain_api_key="",
        langchain_project="sentinel-code",
    )


@pytest.fixture
def base_state():
    return {
        "project_path":                "/tmp/my-project",
        "project_type":                "java-spring",
        "non_functional_requirements": {"target_url": "http://localhost:8080"},
        "java_files":                  [],
        "issues":                      [],
        "iac_files":                   [],
        "infra_gaps":                  [],
        "applied_fixes":               [],
        "test_plan":                   [],
        "generated_tests":             [],
        "test_results":                None,
        "final_report":                None,
        "messages":                    [],
    }


# =============================================================================
# TESTES — setup_tracing
# =============================================================================

class TestSetupTracing:

    def test_setup_tracing_returns_false_when_disabled(self, settings_disabled):
        from tools.observability.tracer import setup_tracing
        result = setup_tracing(settings_disabled)
        assert result is False

    def test_setup_tracing_returns_false_when_no_api_key(self, settings_no_key):
        from tools.observability.tracer import setup_tracing
        result = setup_tracing(settings_no_key)
        assert result is False

    def test_setup_tracing_returns_true_when_configured(self, settings_enabled):
        from tools.observability.tracer import setup_tracing
        result = setup_tracing(settings_enabled)
        assert result is True

    def test_setup_tracing_sets_env_vars(self, settings_enabled):
        from tools.observability.tracer import setup_tracing
        setup_tracing(settings_enabled)
        assert os.environ.get("LANGCHAIN_TRACING_V2") == "true"
        assert os.environ.get("LANGCHAIN_API_KEY") == "ls__fake_key_for_testing"
        assert os.environ.get("LANGCHAIN_PROJECT") == "sentinel-code"

    def test_setup_tracing_does_not_set_env_when_disabled(self, settings_disabled):
        from tools.observability.tracer import setup_tracing
        setup_tracing(settings_disabled)
        assert os.environ.get("LANGCHAIN_TRACING_V2") != "true"

    def test_setup_tracing_does_not_set_env_when_no_key(self, settings_no_key):
        from tools.observability.tracer import setup_tracing
        setup_tracing(settings_no_key)
        assert os.environ.get("LANGCHAIN_TRACING_V2") != "true"


# =============================================================================
# TESTES — is_tracing_enabled
# =============================================================================

class TestIsTracingEnabled:

    def test_is_tracing_enabled_false_by_default(self):
        from tools.observability.tracer import is_tracing_enabled
        assert is_tracing_enabled() is False

    def test_is_tracing_enabled_true_when_env_set(self):
        from tools.observability.tracer import is_tracing_enabled
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        assert is_tracing_enabled() is True

    def test_is_tracing_enabled_false_when_env_false(self):
        from tools.observability.tracer import is_tracing_enabled
        os.environ["LANGCHAIN_TRACING_V2"] = "false"
        assert is_tracing_enabled() is False


# =============================================================================
# TESTES — get_run_tags
# =============================================================================

class TestGetRunTags:

    def test_get_run_tags_includes_project_type(self, base_state):
        from tools.observability.tracer import get_run_tags
        tags = get_run_tags(base_state)
        assert "java-spring" in tags

    def test_get_run_tags_includes_dry_run_false_tag(self, base_state):
        from tools.observability.tracer import get_run_tags
        tags = get_run_tags(base_state, dry_run=False)
        assert "dry_run:false" in tags

    def test_get_run_tags_includes_dry_run_true_tag(self, base_state):
        from tools.observability.tracer import get_run_tags
        tags = get_run_tags(base_state, dry_run=True)
        assert "dry_run:true" in tags

    def test_get_run_tags_includes_iac_tag_when_enabled(self, base_state):
        from tools.observability.tracer import get_run_tags
        tags = get_run_tags(base_state, with_iac=True)
        assert "iac:enabled" in tags

    def test_get_run_tags_excludes_iac_tag_when_disabled(self, base_state):
        from tools.observability.tracer import get_run_tags
        tags = get_run_tags(base_state, with_iac=False)
        assert "iac:enabled" not in tags

    def test_get_run_tags_includes_benchmark_tag_when_enabled(self, base_state):
        from tools.observability.tracer import get_run_tags
        tags = get_run_tags(base_state, with_benchmark=True)
        assert "benchmark:enabled" in tags

    def test_get_run_tags_returns_list(self, base_state):
        from tools.observability.tracer import get_run_tags
        tags = get_run_tags(base_state)
        assert isinstance(tags, list)
        assert len(tags) >= 1


# =============================================================================
# TESTES — get_run_metadata
# =============================================================================

class TestGetRunMetadata:

    def test_get_run_metadata_includes_project_path(self, base_state):
        from tools.observability.tracer import get_run_metadata
        meta = get_run_metadata(base_state)
        assert meta["project_path"] == "/tmp/my-project"

    def test_get_run_metadata_includes_project_type(self, base_state):
        from tools.observability.tracer import get_run_metadata
        meta = get_run_metadata(base_state)
        assert meta["project_type"] == "java-spring"

    def test_get_run_metadata_counts_issues(self, base_state):
        from tools.observability.tracer import get_run_metadata
        from models.issue import Issue, Severity, IssueCategory
        base_state["issues"] = [
            Issue(
                category=IssueCategory.N_PLUS_ONE,
                severity=Severity.CRITICAL,
                file_path="Foo.java",
                root_cause="test",
                evidence="test",
                suggestion="test",
            )
        ]
        meta = get_run_metadata(base_state)
        assert meta["issues_count"] == 1

    def test_get_run_metadata_counts_fixes(self, base_state):
        from tools.observability.tracer import get_run_metadata
        base_state["applied_fixes"] = [
            {"category": "N+1 Query", "status": "applied"},
            {"category": "Cache Ausente", "status": "applied"},
        ]
        meta = get_run_metadata(base_state)
        assert meta["fixes_count"] == 2

    def test_get_run_metadata_handles_missing_fields(self):
        from tools.observability.tracer import get_run_metadata
        # State mínimo sem campos opcionais
        minimal_state = {
            "project_path": "/tmp/test",
            "project_type": "java-spring",
        }
        meta = get_run_metadata(minimal_state)
        assert meta["issues_count"] == 0
        assert meta["fixes_count"] == 0
        assert meta["iac_gaps_count"] == 0

    def test_get_run_metadata_returns_dict(self, base_state):
        from tools.observability.tracer import get_run_metadata
        meta = get_run_metadata(base_state)
        assert isinstance(meta, dict)
        assert "project_path" in meta
        assert "project_type" in meta
        assert "issues_count" in meta
        assert "fixes_count" in meta
        assert "iac_gaps_count" in meta