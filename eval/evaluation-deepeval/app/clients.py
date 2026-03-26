from openai import OpenAI, AsyncOpenAI
import os

client = OpenAI(
    base_url=os.environ.get("OPENAI_SUBJECT_BASE_URL"),
    api_key=os.environ.get("OPENAI_SUBJECT_API_KEY"),
)
judge_client = OpenAI(
    base_url=os.environ.get("OPENAI_JUDGE_BASE_URL"),
    api_key=os.environ.get("OPENAI_JUDGE_API_KEY"),
)
judge_async_client = AsyncOpenAI(
    base_url=os.environ.get("OPENAI_JUDGE_BASE_URL"),
    api_key=os.environ.get("OPENAI_JUDGE_API_KEY"),
)
