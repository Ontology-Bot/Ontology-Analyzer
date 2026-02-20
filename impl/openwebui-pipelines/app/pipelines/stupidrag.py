"""
title: StupidRAG MaterialHandling
author: ontobot
date: 2026-02-11
version: 1.0
license: MIT
description: It takes ontology and embeds triples (converting them to sentences before)
requirements: ollama, openai, sentence_transformers, chromadb, sparqlwrapper
"""

from typing import List, Union, Generator, Iterator
from pydantic import BaseModel
import os

import traceback

try:
    from prototypes.stupidrag.stupidrag import StupidRAG
    from prototypes.utils.main import set_last_message, get_cache_path
    from prototypes.utils.llm_adapter import build_llm_adapter
except Exception as e:
    traceback.print_exc()
    raise

# Set up logging
import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class Pipeline:
    class Valves(BaseModel):
        top_k: int = 5
        LLM_PROVIDER: str = "openai_compat"
        LLM_BASE_URL: str = "https://chat-ai.academiccloud.de/v1/"
        LLM_API_KEY: str
        LLM_DEFAULT_MODEL: str = ""
        SPARQL_BASE_URL: str
        
    def __init__(self):
        self.type = "manifold"
        self.id = "stupidrag"
        self.name = "StupidRAG/"
        self.toggle = True 

        self.model = None
        self.client = None

        self.valves = self.Valves(
            **{ # type: ignore (we do not initialize top_k here)
                "LLM_PROVIDER": os.getenv("LLM_PROVIDER", "openai_compat"),
                "LLM_BASE_URL": os.getenv("LLM_BASE_URL", "https://chat-ai.academiccloud.de/v1/"),
                "LLM_API_KEY": os.getenv("LLM_API_KEY", ""),
                "LLM_DEFAULT_MODEL": os.getenv("LLM_DEFAULT_MODEL", ""),
                "SPARQL_BASE_URL": os.getenv("SPARQL_BASE_URL", "")
            }
        )
        logger.info(f"--- {self.name} Initialized ---")

    def _get_models(self) -> List[dict]:
        try:
            if self.client is None:
                self._update()
            if self.client is None:
                raise ValueError("Oops! Forgot to initialize valves!")
            
            return self.client.list_models()
        except Exception as e:
            logger.error(f"Discovery error: {e}")
            fallback = self.valves.LLM_DEFAULT_MODEL or "fallback-model"
            return [{"id": fallback, "name": "StupidRAG (Fallback model)"}]
        
    
    def _update(self) -> None:
        if (self.valves.SPARQL_BASE_URL == "" or self.valves.LLM_BASE_URL == ""):
            logger.error("Empty SPARQL_BASE_URL and LLM_BASE_URL")
            return
        self.model = StupidRAG(self.valves.top_k, self.valves.SPARQL_BASE_URL, cachepath=get_cache_path())
        self.client = build_llm_adapter(
            provider=self.valves.LLM_PROVIDER,
            base_url=self.valves.LLM_BASE_URL,
            api_key=self.valves.LLM_API_KEY,
        )


    def pipelines(self) -> List[dict]:
        return self._get_models()


    async def on_startup(self):
        logger.info(f"on_startup triggered for {__name__}")
        # initialize
        self._update()
        #
        logger.info(f"--- {self.name} Started ---")
        

    async def on_shutdown(self):
        logger.info(f"on_shutdown triggered for {__name__}")
        

    async def on_valves_updated(self):
        logger.info("Valves updated")
        self._update()
        


    def pipe(
        self, user_message: str, model_id: str, messages: List[dict], body: dict
    ) -> Union[str, Generator, Iterator]:
        if self.model is None or self.client is None:
            raise ValueError("Oops! Forgot to initialize valves!")

        # 0. get model id
        model_id = body.get("model", "").split(".", 1)[-1] or self.valves.LLM_DEFAULT_MODEL # Strip pipe prefix
        if not model_id:
            raise ValueError("No model selected and LLM_DEFAULT_MODEL is empty")

        logger.info(f"Inlet:{__name__} model {model_id}")
        logger.info(f"Inlet function called with body: {body}")
        # 1. Get user query
        logger.info(f"UserQuery: {user_message}")

        # 2. Get context
        context = self.model.process(user_message)

        logger.info(f"Extracted context: {context}")
        # 3. Form new query with context
        msg = "Using the ontology-grounded context, answer the user query.\nCONTEXT:\n"
        if len(context) > 0:
            for c in context:
                msg += f"{c}\n\n"
        else:
            msg += "NO RELEVANT CONTEXT FOUND \n\n"
        msg += f"USER QUERY:\n{user_message}\n\nANSWER:\n"

        logger.info(f"Message: {msg}")
        set_last_message("user", messages, msg)

        # 4. Query the llm
        try:
            if body.get("stream", False):
                def stream_generator(client):
                    for chunk in client.stream_text(
                        model=model_id,
                        messages=messages
                    ):
                        yield chunk
                return stream_generator(self.client)
            else:
                response = self.client.chat_text(
                    model=model_id,
                    messages=messages
                )
                return response
        except Exception as e:
            return f"Error calling LLM: {str(e)}"

        