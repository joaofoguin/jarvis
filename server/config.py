from functools import lru_cache
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", ".env.vps"),
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )
    app_name: str = "JARVIS VPS Core"
    app_env: str = "development"
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-flash"
    database_url: str = Field(default="", validation_alias=AliasChoices("DATABASE_URL", "POSTGRES_URL"))
    jarvis_api_token: str = ""
    auto_create_schema: bool = True
    deepseek_timeout_seconds: float = 45.0
    max_tool_rounds: int = 4
    conversation_history_limit: int = 16

@lru_cache
def get_settings() -> Settings:
    return Settings()
