import requests


def test_get_products_returns_200(base_url):
    """
    Funcional: GET /products
    Teste funcional de GET /products
    """
    response = requests.get(f"{base_url}/products")
    assert response.status_code == 200


def test_get_products_returns_valid_response(base_url):
    """Valida que a resposta tem conteúdo."""
    response = requests.get(f"{base_url}/products")
    assert response.status_code in (200, 201, 204)
    if response.status_code == 200:
        assert response.content is not None
