from deepeval.models.base_model import DeepEvalBaseLLM
from app.llm_adapter import LLMAdapter

class OpenAIBaseLLM(DeepEvalBaseLLM):
    def __init__(
        self,
        model_name: str,
        client: LLMAdapter,
        invalidate_cache: bool
    ):
        self.model_name = model_name
        self.client = client
        self.invalidate_cache = invalidate_cache

    def load_model(self):
        return self

    def generate(self, prompt: str) -> str:
        res, _ = self.client.chat_text(self.model_name, prompt, self.invalidate_cache)
        return res

    async def a_generate(self, prompt: str) -> str:
        res, _ = await self.client.a_chat_text(self.model_name, prompt, self.invalidate_cache)
        return res

    def get_model_name(self):
        return self.model_name
    

class StubLLM(DeepEvalBaseLLM):
    def __init__(self, response: str):
        self.response = response

    def load_model(self):
        return self

    def generate(self, prompt: str) -> str:
        return self.response

    async def a_generate(self, prompt: str) -> str:
        return self.response

    def get_model_name(self):
        return "stub-model"