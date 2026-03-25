from deepeval.models.base_model import DeepEvalBaseLLM
from openai import AsyncOpenAI, OpenAI

class OpenAIBaseLLM(DeepEvalBaseLLM):
    def __init__(
        self,
        model_name: str,
        client: OpenAI,
        a_client: AsyncOpenAI
    ):
        self.model_name = model_name
        self.client = client
        self.a_client = a_client

    def load_model(self):
        return self


    def generate(self, prompt: str) -> str:
        response = self.client.responses.create(
            model=self.model_name,
            input=prompt,
        )
        return response.output_text

    async def a_generate(self, prompt: str) -> str:
        response = await self.a_client.responses.create(
            model=self.model_name, input=prompt
        )
        return response.output_text

    def get_model_name(self):
        return self.model_name