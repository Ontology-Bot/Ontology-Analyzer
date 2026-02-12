"""
title: StupidRAG MaterialHandling
author: ontobot
date: 2026-02-11
version: 1.0
license: MIT
description: It takes ontology and embeds triples (converting them to sentences before)
requirements: ollama, sentence_transformers, chromadb, sparqlwrapper
"""

from typing import List, Union, Generator, Iterator
from ollama import Client
from pydantic import BaseModel
import os

import traceback

try:
    from prototypes.rag.stupidrag import StupidRAG
    from prototypes.utils.main import set_last_message, get_cache_path
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
        OLLAMA_BASE_URL: str
        OLLAMA_API_KEY: str
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
                "OLLAMA_BASE_URL": os.getenv("OLLAMA_BASE_URL", ""),
                "OLLAMA_API_KEY": os.getenv("OLLAMA_API_KEY", ""),
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
            
            model_data = self.client.list()
            
            # model_data is {'models': [...]}
            return [
                {
                    "id": m['name'],
                    "name": m['name']
                }
                for m in model_data.get('models', [])
            ]
        except Exception as e:
            logger.error(f"Discovery error: {e}")
            return [{"id": "llama3", "name": "StupidRAG (Fallback model)"}]
        
    
    def _update(self) -> None:
        if (self.valves.SPARQL_BASE_URL == "" or self.valves.OLLAMA_BASE_URL == ""):
            logger.error("Empty SPARQL_BASE_URL and OLLAMA_BASE_URL")
            return
        self.model = StupidRAG(self.valves.top_k, self.valves.SPARQL_BASE_URL, cachepath=get_cache_path())
        self.client = Client(
            host=self.valves.OLLAMA_BASE_URL,
            headers={"Authorization": f"Bearer {self.valves.OLLAMA_API_KEY}"} if self.valves.OLLAMA_API_KEY else {}
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
        model_id = body.get("model", "").split(".", 1)[-1] # Strip pipe prefix

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
                    for chunk in client.chat(
                        model=model_id,
                        messages=messages,
                        stream=True
                    ):
                        if "message" in chunk and "content" in chunk["message"]:
                            yield chunk["message"]["content"]
                return stream_generator(self.client)
            else:
                response = self.client.chat(
                    model=model_id,
                    messages=messages,
                    stream=False
                )
                return response['message']['content']
        except Exception as e:
            return f"Error calling LLM: {str(e)}"

        