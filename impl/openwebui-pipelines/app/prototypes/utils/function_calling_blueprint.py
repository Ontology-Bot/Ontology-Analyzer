from typing import List, Optional
from pydantic import BaseModel
import os
import requests
import json

import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


from utils.pipelines.main import (
    get_last_user_message,
    add_or_update_system_message,
    get_tools_specs,
)
from prototypes.utils.llm_adapter import build_llm_adapter, LLMAdapter

# System prompt for function calling
DEFAULT_SYSTEM_PROMPT = (
            """Tools: {}

If a function tool doesn't match the query, return an empty string. Else, pick a
function tool, fill in the parameters from the function tool's schema, and
return it in the format {{ "name": \"functionName\", "parameters": {{ "key":
"value" }} }}. Only pick a function if the user asks.  Only return the object. Do not return any other text."
"""
        )

class Pipeline:
    class Valves(BaseModel):
        # List target pipeline ids (models) that this filter will be connected to.
        # If you want to connect this filter to all pipelines, you can set pipelines to ["*"]
        pipelines: List[str] = []

        # Assign a priority level to the filter pipeline.
        # The priority level determines the order in which the filter pipelines are executed.
        # The lower the number, the higher the priority.
        priority: int = 0

        # Valves for function calling
        LLM_PROVIDER: str
        LLM_BASE_URL: str
        LLM_API_KEY: str
        TASK_MODEL: str
        TEMPLATE: str

    def __init__(self, prompt: str | None = None) -> None:
        # Pipeline filters are only compatible with Open WebUI
        # You can think of filter pipeline as a middleware that can be used to edit the form data before it is sent to the OpenAI API.
        self.type = "filter"

        # Optionally, you can set the id and name of the pipeline.
        # Best practice is to not specify the id so that it can be automatically inferred from the filename, so that users can install multiple versions of the same pipeline.
        # The identifier must be unique across all pipelines.
        # The identifier must be an alphanumeric string that can include underscores or hyphens. It cannot contain spaces, special characters, slashes, or backslashes.
        # self.id = "function_calling_blueprint"
        self.name = "Function Calling Blueprint"
        self.prompt = prompt or DEFAULT_SYSTEM_PROMPT
        self.tools: object = None

        self.client: LLMAdapter | None = None

        # Initialize valves
        self.valves = self.Valves(
            **{
                "pipelines": ["*"],  # Connect to all pipelines
                "LLM_PROVIDER": os.getenv(
                    "LLM_PROVIDER", "openai"
                ),
                "LLM_BASE_URL": os.getenv(
                    "LLM_BASE_URL", "https://api.openai.com/v1"
                ),
                "LLM_API_KEY": os.getenv("LLM_API_KEY", "YOUR_API_KEY"),
                "TASK_MODEL": os.getenv("LLM_DEFAULT_MODEL", "gpt-3.5-turbo"),
                "TEMPLATE": """Use the following context as your learned knowledge, inside <context></context> XML tags.
<context>
    {{CONTEXT}}
</context>

When answer to user:
- Put all labels, terms, and GUIDs in `` quotes.
- If context has a very long list - print top 10 items at first.
- If you don't know, just say that you don't know.
- If you don't know when you are not sure, ask for clarification.
Avoid mentioning that you obtained the information from the context.
And answer according to the language of the user's question.
USE DICTIONARY AS PRIMARY KNOWLEDGE, DO NOT INVENT KNOWLEDGE OUTSIDE OF CONTEXT
""",
            }
        )

    def _update(self) -> None:
        if (self.valves.LLM_BASE_URL == ""):
            logger.error("Empty LLM_BASE_URL")
            return
        self.client = build_llm_adapter(
            provider=self.valves.LLM_PROVIDER,
            base_url=self.valves.LLM_BASE_URL,
            api_key=self.valves.LLM_API_KEY,
        )

    async def on_valves_updated(self):
        logger.info("on_valves_updated:{__name__}")
        self._update()

    async def on_startup(self):
        # This function is called when the server is started.
        logging.info(f"on_startup:{__name__}")
        self._update()

    async def on_shutdown(self):
        # This function is called when the server is stopped.
        logging.info(f"on_shutdown:{__name__}")
        pass

    async def inlet(self, body: dict, user: Optional[dict] = None) -> dict:
        # If title generation is requested, skip the function calling filter
        if body.get("title", False):
            return body

        logging.info(f"pipe:{__name__}")
        logging.info(user)

        # Get the last user message
        user_message = get_last_user_message(body["messages"])

        # Get the tools specs
        tools_specs = get_tools_specs(self.tools)

        # logging.info("---- tool specs -----")
        # logging.info(tools_specs)

        prompt = self.prompt.format(json.dumps(tools_specs, indent=2))
        content = "History:\n" + "\n".join(
                                [
                                    f"{message['role']}: {message['content']}"
                                    for message in body["messages"][::-1][:4]
                                ]
                            ) + f"Query: {user_message}"

        result = self.run_completion(prompt, content)
        logging.info("---- func result -----")
        logging.info(result)
        messages = self.call_function(result, body["messages"])
        logging.info("---- new conversation with system message -----")
        logging.info(messages)

        return {**body, "messages": messages}

    # Call the function
    def call_function(self, result, messages: list[dict]) -> list[dict]:
        if "name" not in result:
            logging.warning(f"LLM used wrong function calling convention {result}")
            return messages

        function = getattr(self.tools, result["name"], None)
        logging.info(f"function: {function}")

        function_result = None
        if not function:
            logging.warning(f"LLM tried to use nonexisting function {result['name']}")
        else:
            try:
                function_result = function(**result["parameters"])
            except Exception as e:
                logging.exception(e)

        logging.info(f"function result: {function_result}")

        # Add the function result to the system prompt
        if not function_result:
            function_result = ""

        system_prompt = self.valves.TEMPLATE.replace(
            "{{CONTEXT}}", function_result
        )

        messages = add_or_update_system_message(
            system_prompt, messages
        )

        # Return the updated messages
        # return messages

        return messages

    def run_completion(self, system_prompt: str, content: str) -> dict:
        if not self.client:
            logger.warning("Run competions failed: model client is not initialized")
            return {}
        try:
            messages = [
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": content,
                },
            ]

            answer = self.client.chat_json(self.valves.TASK_MODEL, messages)
            # Parse the function response
            if answer != "":
                result = json.loads(answer)
                logger.info(result)
                return result

        except Exception as e:
            logger.exception(f"Error: {e}")

        return {}
