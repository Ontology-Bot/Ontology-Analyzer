from openai import OpenAI, AsyncOpenAI, AuthenticationError
import os

_client = OpenAI(
    base_url=os.environ.get("OPENAI_SUBJECT_BASE_URL"),
    api_key=os.environ.get("OPENAI_SUBJECT_API_KEY"),
)
_judge_client = OpenAI(
    base_url=os.environ.get("OPENAI_JUDGE_BASE_URL"),
    api_key=os.environ.get("OPENAI_JUDGE_API_KEY"),
)
_judge_async_client = AsyncOpenAI(
    base_url=os.environ.get("OPENAI_JUDGE_BASE_URL"),
    api_key=os.environ.get("OPENAI_JUDGE_API_KEY"),
)

def get_subject_client():
    return _client

def get_judge_client():
    return _judge_client

def get_judge_async_client():
    return _judge_async_client

def reset_connection():
    global _client
    _client = OpenAI(
        base_url=os.environ.get("OPENAI_SUBJECT_BASE_URL"),
        api_key=os.environ.get("OPENAI_SUBJECT_API_KEY"),
    )
    global _judge_client
    _judge_client = OpenAI(
        base_url=os.environ.get("OPENAI_JUDGE_BASE_URL"),
        api_key=os.environ.get("OPENAI_JUDGE_API_KEY"),
    )
    global _judge_async_client
    _judge_async_client = AsyncOpenAI(
        base_url=os.environ.get("OPENAI_JUDGE_BASE_URL"),
        api_key=os.environ.get("OPENAI_JUDGE_API_KEY"),
    )

def test_connection(client: OpenAI):
    try:
        client.models.list()
        return True
    except AuthenticationError:
        return False
    except Exception as e:
        return False

def test_model(client: OpenAI, model_name: str):
    try:
        # Use a very short request just to check the model is reachable
        client.chat.completions.create(
            model=model_name,  # replace with your model
            messages=[
                {"role": "system", "content": ""},
                {"role": "user", "content": "ping"}
            ],
            max_tokens=1  # minimal token usage
        )
        return True
    except Exception as e:
        return False
