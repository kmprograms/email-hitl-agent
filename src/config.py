from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        frozen=True,
    )

    openai_api_key: SecretStr
    openai_model_name: str = "gpt-4.1-mini"
    model_temperature: float = 0.3

    max_revisions: int = 3
    sent_dir: str = "sent"


settings = Settings()  # type: ignore[call-arg]