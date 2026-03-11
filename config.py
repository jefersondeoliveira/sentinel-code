from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """
    Configurações do SentinelCode lidas automaticamente do arquivo .env.

    Pydantic valida os tipos e exige os campos obrigatórios na inicialização.
    Se OPENAI_API_KEY não estiver no .env, o programa falha aqui com mensagem clara.
    """

    # --- LLM ---
    openai_api_key: str = Field(..., description="Chave da API OpenAI (obrigatória)")
    openai_model: str = Field(default="gpt-4o", description="Modelo a usar")

    # --- LangSmith (observabilidade, opcional) ---
    langchain_api_key: str | None = Field(default=None)
    langchain_tracing_v2: bool = Field(default=False)
    langchain_project: str = Field(default="sentinelcode")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        env_file_override = True  # .env tem prioridade sobre variáveis do sistema


# Instância global — importada pelos outros módulos
# Exemplo de uso: from config import settings; print(settings.openai_model)
settings = Settings()