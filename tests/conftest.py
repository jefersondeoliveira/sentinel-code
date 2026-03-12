"""
conftest.py — Fixtures compartilhadas entre todos os testes do SentinelCode.

reset_agent_ui: reseta o _ui global de cada módulo de agente após cada teste,
evitando que um set_ui() vazado afete testes subsequentes na mesma sessão pytest.
"""

import pytest

import agents.code_analyzer as _code_analyzer
import agents.fix_agent as _fix_agent
import agents.iac_analyzer as _iac_analyzer
import agents.iac_patcher as _iac_patcher
import agents.benchmark as _benchmark
import agents.test_agent as _test_agent
import agents.reporter as _reporter

_AGENT_MODULES = [
    _code_analyzer,
    _fix_agent,
    _iac_analyzer,
    _iac_patcher,
    _benchmark,
    _test_agent,
    _reporter,
]


@pytest.fixture(autouse=True)
def reset_agent_ui():
    """Garante que _ui global dos agentes está None antes e após cada teste."""
    for mod in _AGENT_MODULES:
        if hasattr(mod, "set_ui"):
            mod.set_ui(None)
    yield
    for mod in _AGENT_MODULES:
        if hasattr(mod, "set_ui"):
            mod.set_ui(None)
