import time
import requests


def test_get_products_regression_health_check_ausente(base_url):
    """
    Regressão: Regressão: fix Health Check Ausente em k8s\deployment.yaml
    Fix aplicado: Health Check Ausente em k8s\deployment.yaml
    Valida que o endpoint responde corretamente após a correção.
    """
    start    = time.time()
    response = requests.get(f"{base_url}/products")
    elapsed  = (time.time() - start) * 1000

    assert response.status_code == 200, (
        f"Endpoint retornou {response.status_code} após fix de Health Check Ausente"
    )
    assert elapsed < 2000, (
        f"Tempo excessivo: {elapsed:.0f}ms — possível regressão após fix"
    )
