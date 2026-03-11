import pytest
import requests


@pytest.fixture(scope="session")
def base_url():
    """URL base da aplicação. Configurar via NFR target_url."""
    return "http://localhost:8080"


@pytest.fixture(scope="session")
def http_session():
    session = requests.Session()
    yield session
    session.close()
