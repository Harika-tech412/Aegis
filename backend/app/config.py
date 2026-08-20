"""Application settings loaded from environment / .env."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve the project-root .env regardless of the working directory. Inside
# the container this path doesn't exist and settings come from injected env
# vars (docker-compose `env_file`), which take precedence anyway.
_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    DATABASE_URL: str = "postgresql+psycopg2://aegis:aegis_dev_pw@db:5432/aegis"

    GROQ_API_KEY: str = ""
    GEMINI_API_KEY: str = ""

    JWT_SECRET: str = "change_me_to_a_random_string"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRY_MINUTES: int = 60

    LLM_PROVIDER: str = "groq"
    LLM_MODEL_GROQ: str = "openai/gpt-oss-20b"
    LLM_MODEL_GEMINI: str = "gemini-2.5-flash"

    # Shared network membership key. Hashes are only meaningful to institutions
    # holding this salt — it is the cryptographic equivalent of network
    # membership. Rotating it invalidates every previously published signal.
    NETWORK_HASH_SALT: str = "aegis_network_dev_salt"

    ENVIRONMENT: str = "development"


settings = Settings()
