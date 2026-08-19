"""Application settings loaded from environment / .env."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
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
    LLM_MODEL_GROQ: str = "llama-3.1-8b-instant"
    LLM_MODEL_GEMINI: str = "gemini-2.5-flash"

    ENVIRONMENT: str = "development"


settings = Settings()
