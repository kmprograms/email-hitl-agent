from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI

from src.config import settings

def create_model(temperature: float | None = None) -> BaseChatModel:
    temp: float = temperature if temperature is not None else settings.model_temperature

    return ChatOpenAI(
        api_key=settings.openai_api_key,
        model=settings.openai_model_name,
        temperature=temp,
        timeout=60.0,
        max_retries=2,
    )