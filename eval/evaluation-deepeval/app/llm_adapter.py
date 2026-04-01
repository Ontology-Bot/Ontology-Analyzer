from __future__ import annotations

from dataclasses import dataclass
from abc import ABC, abstractmethod
from typing import Awaitable

from openai import AsyncOpenAI, OpenAI
from ollama import Client, AsyncClient

from .llm_cache import LLMCache

import logging
logger = logging.getLogger(__name__)

def test_connection(client: LLMAdapter):
    try:
        client.list_models()
        return True
    except Exception as e:
        return False

class LLMAdapter(ABC):
    def __init__(self, cache: LLMCache | None = None, key_prefix: str = "") -> None:
        super().__init__()
        self.cache = cache
        self.key_prefix = key_prefix

    def _cache_key(self, model: str, message: str) -> str:
        return str((self.key_prefix, model, message))

    def _get_cached(self, model: str, message: str) -> str | None:
        cached = self.cache and self.cache.get(self._cache_key(model, message))
        if cached:
            logger.info(f"used cached input-output pair for model {model}")
        return cached or None

    def _set_cached(self, model: str, message: str, output: str) -> None:
        if self.cache:
            logger.info(f"caching input-output pair for model {model}")
            self.cache.set(self._cache_key(model, message), output)

    @abstractmethod
    def list_models(self) -> list[str]:
        raise NotImplementedError
    
    @abstractmethod
    def chat_text(self, model: str, message: str, invalidate_cache: bool = True, **kwargs) -> str:
        raise NotImplementedError
    
    @abstractmethod
    def a_chat_text(self, model: str, message: str, invalidate_cache: bool = True, **kwargs) -> Awaitable[str]:
        raise NotImplementedError
    
    @abstractmethod
    def test_model(self, model: str) -> str:
        raise NotImplementedError
    

class OpenAICompatAdapter(LLMAdapter):
    def __init__(self, base_url: str, api_key: str, cache: LLMCache | None = None):
        super().__init__(cache, f"openai|{base_url}")
        self.client = OpenAI(base_url=base_url, api_key=api_key)
        self.a_client = AsyncOpenAI(base_url=base_url, api_key=api_key)

    def list_models(self) -> list[str]:
        model_data = self.client.models.list()
        return [model.id for model in model_data.data]

    def chat_text(self, model: str, message: str, invalidate_cache: bool = True, **kwargs) -> str:
        if not invalidate_cache and (cached := self._get_cached(model, message)):
            return cached

        response = self.client.chat.completions.create(
            model=model,
            messages=[
                {"role": "user", "content": message}
            ],
            **kwargs
        )
        output = response.choices[0].message.content or ""
        self._set_cached(model, message, output)
        return output
    
    async def a_chat_text(self, model: str, message: str, invalidate_cache: bool = True, **kwargs) -> str:
        if not invalidate_cache and (cached := self._get_cached(model, message)):
            return cached
        response = await self.a_client.chat.completions.create(
            model=model,
            messages=[
                {"role": "user", "content": message}
            ],
            **kwargs
        )
        output = response.choices[0].message.content or ""
        self._set_cached(model, message, output)
        return output
    
    def test_model(self, model: str) -> str:
        try:
            self.chat_text(model, "hello", invalidate_cache=True, max_tokens=1)
            return ""
        except Exception as e:
            logger.error(f"Model test failed for model '{model}': {e}")
            return str(e)
    

class OllamaAdapter(LLMAdapter):
    def __init__(self, base_url: str, api_key: str | None = None, cache: LLMCache | None = None):
        super().__init__(cache, f"ollama|{base_url}")
        headers = {'Authorization': 'Bearer ' + api_key} if api_key else None
        self.client = Client(host=base_url, headers=headers)
        self.a_client = AsyncClient(host=base_url, headers=headers)

    def list_models(self) -> list[str]:
        return [model.model or "none-model" for model in self.client.list().models]

    def chat_text(self, model: str, message: str, invalidate_cache: bool = True, **kwargs) -> str:
        if not invalidate_cache and (cached := self._get_cached(model, message)):
            return cached

        response = self.client.chat(
            model=model,
            messages=[{"role": "user", "content": message}],
            **kwargs
        )
        output = response.message.content or ""
        self._set_cached(model, message, output)
        return output

    async def a_chat_text(self, model: str, message: str, invalidate_cache: bool = True, **kwargs) -> str:
        if not invalidate_cache and (cached := self._get_cached(model, message)):
            return cached

        response = await self.a_client.chat(
            model=model,
            messages=[{"role": "user", "content": message}],
            **kwargs
        )
        output = response.message.content or ""
        self._set_cached(model, message, output)
        return output
    
    def test_model(self, model: str) -> str:
        try:
            self.chat_text(model, "hello", invalidate_cache=True, options={"num_ctx": 1})
            return ""
        except Exception as e:
            logger.error(f"Model test failed for model '{model}': {e}")
            return str(e)


@dataclass
class LLMAdapterSettings:
    provider: str
    base_url: str
    api_key: str

def build_llm_adapter(settings: LLMAdapterSettings, cache: LLMCache | None = None) -> LLMAdapter:
    normalized = settings.provider.strip().lower()
    if normalized in {"openai", "openai_compat", "openai-compatible", "openai_compatible"}:
        return OpenAICompatAdapter(base_url=settings.base_url, api_key=settings.api_key, cache=cache)
    elif normalized in {"ollama"}:
        return OllamaAdapter(base_url=settings.base_url, api_key=settings.api_key, cache=cache)
    raise ValueError(f"Unsupported LLM_PROVIDER='{settings.provider}'.")
