"""
title: Query Caching
author: ontobot
date: 2026-03-14
version: 1.0
license: MIT
description: Generates Markdown knowledge pages from SPARQL queries and reuses them as cached knowledge.
requirements: requests
"""

from typing import List, Union, Generator, Iterator
from pydantic import BaseModel
import os
import traceback
import logging

try:
    from prototypes.querycaching.querycaching import QueryCaching
except Exception:
    traceback.print_exc()
    raise

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class Pipeline:
    class Valves(BaseModel):
        GRAPHDB_ENDPOINT: str
        QUERY_DIR: str = "/app/prototypes/querycaching/queries"
        OUTPUT_DIR: str = "/app/prototypes/querycaching/output"

    def __init__(self):
        self.type = "pipe"
        self.id = "querycaching"
        self.name = "QueryCaching"
        self.toggle = True

        self.model = None
        self.valves = self.Valves(
            **{
                "GRAPHDB_ENDPOINT": os.getenv("GRAPHDB_ENDPOINT", ""),
                "QUERY_DIR": os.getenv("QUERY_DIR", "/app/prototypes/querycaching/queries"),
                "OUTPUT_DIR": os.getenv("OUTPUT_DIR", "/app/prototypes/querycaching/output"),
            }
        )

    def _update(self):
        self.model = QueryCaching(
            graphdb_endpoint=self.valves.GRAPHDB_ENDPOINT,
            query_dir=self.valves.QUERY_DIR,
            output_dir=self.valves.OUTPUT_DIR,
        )

    async def on_startup(self):
        self._update()

    async def on_valves_updated(self):
        self._update()

    def pipe(
        self, user_message: str, model_id: str, messages: List[dict], body: dict
    ) -> Union[str, Generator, Iterator]:
        if self.model is None:
            self._update()

        result = self.model.process(user_message)

        pages = "\n".join(f"- {page}" for page in result["generated_pages"])
        return f"{result['message']}\n\nGenerated pages:\n{pages}"
