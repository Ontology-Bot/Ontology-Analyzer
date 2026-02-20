from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Iterator

from ollama import Client as OllamaClient
from openai import OpenAI


class LLMAdapter(ABC):
    @abstractmethod
    def list_models(self) -> list[dict[str, str]]:
        raise NotImplementedError

    @abstractmethod
    def chat_text(self, model: str, messages: list[dict[str, Any]]) -> str:
        raise NotImplementedError

    @abstractmethod
    def stream_text(self, model: str, messages: list[dict[str, Any]]) -> Iterator[str]:
        raise NotImplementedError

    @abstractmethod
    def chat_json(
        self,
        model: str,
        messages: list[dict[str, Any]],
        temperature: float = 0,
        max_tokens: int = -1,
    ) -> str:
        raise NotImplementedError


class OllamaAdapter(LLMAdapter):
    def __init__(self, base_url: str, api_key: str = ""):
        self._client = OllamaClient(
            host=base_url,
            headers={"Authorization": f"Bearer {api_key}"} if api_key else {},
        )

    def list_models(self) -> list[dict[str, str]]:
        model_data = self._client.list()
        return [
            {
                "id": str(item.get("name", "")),
                "name": str(item.get("name", "")),
            }
            for item in model_data.get("models", [])
            if item.get("name")
        ]

    def chat_text(self, model: str, messages: list[dict[str, Any]]) -> str:
        response = self._client.chat(model=model, messages=messages, stream=False)
        return str(response.get("message", {}).get("content", ""))

    def stream_text(self, model: str, messages: list[dict[str, Any]]) -> Iterator[str]:
        for chunk in self._client.chat(model=model, messages=messages, stream=True):
            if "message" in chunk and "content" in chunk["message"]:
                yield str(chunk["message"]["content"])

    def chat_json(
        self,
        model: str,
        messages: list[dict[str, Any]],
        temperature: float = 0,
        max_tokens: int = -1,
    ) -> str:
        options: dict[str, Any] = {"temperature": temperature}
        if max_tokens >= 0:
            options["num_predict"] = max_tokens
        response = self._client.chat(
            model=model,
            messages=messages,
            stream=False,
            format="json",
            options=options,
        )
        return str(response.get("message", {}).get("content", ""))


class OpenAICompatAdapter(LLMAdapter):
    def __init__(self, base_url: str, api_key: str = ""):
        self._client = OpenAI(base_url=base_url, api_key=api_key or "none")

    def list_models(self) -> list[dict[str, str]]:
        models = self._client.models.list()
        return [{"id": model.id, "name": model.id} for model in models.data]

    def chat_text(self, model: str, messages: list[dict[str, Any]]) -> str:
        response = self._client.chat.completions.create(model=model, messages=messages, stream=False)
        message = response.choices[0].message
        return message.content or ""

    def stream_text(self, model: str, messages: list[dict[str, Any]]) -> Iterator[str]:
        stream = self._client.chat.completions.create(model=model, messages=messages, stream=True)
        for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            content = getattr(delta, "content", None)
            if content:
                yield content

    def chat_json(
        self,
        model: str,
        messages: list[dict[str, Any]],
        temperature: float = 0,
        max_tokens: int = -1,
    ) -> str:
        request: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
            "stream": False,
        }
        if max_tokens >= 0:
            request["max_tokens"] = max_tokens
        response = self._client.chat.completions.create(**request)
        message = response.choices[0].message
        return message.content or ""


def build_llm_adapter(provider: str, base_url: str, api_key: str = "") -> LLMAdapter:
    normalized = provider.strip().lower()
    if normalized in {"ollama"}:
        return OllamaAdapter(base_url=base_url, api_key=api_key)
    if normalized in {"openai", "openai_compat", "openai-compatible", "openai_compatible"}:
        return OpenAICompatAdapter(base_url=base_url, api_key=api_key)
    raise ValueError(f"Unsupported LLM_PROVIDER='{provider}'. Use 'ollama' or 'openai_compat'.")
