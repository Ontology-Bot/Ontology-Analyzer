"""
title: Test Pipeline
author: ontology-bot
date: 2026-02-03
version: 1.0
license: MIT
description: A demo pipeline showing how to create our own stuff.
requirements: llama-index
"""

# in `requirements` all pip install modules for this pipeline are specified

from typing import List, Union, Generator, Iterator
from schemas import OpenAIChatMessage


class Pipeline:
    def __init__(self):
        self.documents = None
        self.index = None

    async def on_startup(self):
        # This function is called when the server is started.
        
        # Set the API key
        # import os
        # os.environ["API_KEY"] = "your-api-key-here"
        pass

    async def on_shutdown(self):
        # This function is called when the server is stopped.
        pass

    def pipe(
        self, user_message: str, model_id: str, messages: List[dict], body: dict
    ) -> Union[str, Generator, Iterator]:
        return f"Hello, World! - query '{user_message}' to '{model_id}'"