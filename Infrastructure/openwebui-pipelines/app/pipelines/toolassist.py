"""
title: StupidRAG MaterialHandling
author: ontobot
date: 2026-02-11
version: 1.0
license: MIT
description: It takes ontology and embeds triples (converting them to sentences before)
requirements: ollama, sentence_transformers, chromadb, sparqlwrapper, openai
"""

from ollama import Client
import os

import traceback
try:
    from blueprints.function_calling_blueprint import Pipeline as FunctionCallingBlueprint
    from prototypes.rag.sparql_tools import SparqlTools
    from prototypes.utils.main import get_cache_path
except Exception as e:
    traceback.print_exc()
    raise

# Set up logging
import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class Pipeline(FunctionCallingBlueprint):
    class Valves(FunctionCallingBlueprint.Valves):
        SPARQL_BASE_URL: str

    
    class Tools:
        def __init__(self, pipeline, sparql_tools: SparqlTools) -> None:
            self.pipeline = pipeline
            self.sparql_tools = sparql_tools
            
        def get_node_context(self, node_label: str) ->str:
            self.sparql_tools.get_node_context(node_label)

            return ""
        
        def get_list_of(self, term):
            self.sparql_tools.get_list(term)

            return ""
        
        def get_materialflow_term_definition(self, term):
            self.sparql_tools.get_definition(term)

            return ""


        # def get_path_between_nodes(self, node_a_label, node_b_label):
            
        # def check_materialflow_integrity(self):
            
        
    def __init__(self):
        super().__init__()
        self.name = "SPARQL Tools Pipeline"

        self.valves = self.Valves(
            **{ # type: ignore (we do not initialize top_k here)
                **self.valves.model_dump(),
                "pipelines": ["*"],  # Connect to all pipelines
                "SPARQL_BASE_URL": os.getenv("SPARQL_BASE_URL", "")
            }
        )
        sparql_tools = SparqlTools(self.valves.SPARQL_BASE_URL, get_cache_path())
        self.tools = self.Tools(self, sparql_tools)

        logger.info(f"--- {self.name} Initialized ---")


    async def on_startup(self):
        logger.info(f"on_startup triggered for {__name__}")
        

    async def on_shutdown(self):
        logger.info(f"on_shutdown triggered for {__name__}")