"""
title: Tool Assist MaterialHandling
author: ontobot
date: 2026-02-11
version: 1.0
license: MIT
description: ***
requirements: sentence_transformers, chromadb, sparqlwrapper, openai
"""
from typing import List, Optional
import os
import json

import traceback
try:
    from prototypes.utils.function_calling_blueprint import Pipeline as FunctionCallingBlueprint
    from prototypes.toolassist.sparql_tools import SparqlTools
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
        SPARQL_BASE_URL: str = ""

    
    class Tools:
        def __init__(self, pipeline, sparql_tools: SparqlTools) -> None: # SparqlTools
            self.pipeline = pipeline
            self.sparql_tools = sparql_tools
            
        def get_materialflow_node_context(self, component_label_or_guid: str) ->str:
            """
            Get a detailed information about a material handling component, including its qualities, parameters, containtments, and close connections. Performs an exact search by label or GUID string.

            :param component_label_or_guid: Material handling component identificator. Can be short label, which consists of uppercase letters and/or numbers. Can be long string, containing GUID.
            :return: Detailed information about specified component. If component was not found, returns a notification.
            """
            logger.info(f"--- get_materialflow_node_context() {component_label_or_guid} ---")
            block = self.sparql_tools.get_node_context(component_label_or_guid)
            if block is None:
                return "Instance `{component_label_or_guid}` was not found."
            ss, _ = block.to_sentences()

            tmp = '\n'.join(ss)
            return f"Information about `{component_label_or_guid}`:\n{tmp}."
        
        def get_list_of(self, material_handling_class: str) -> str:
            """
            Enumerates all material handling instances belonging to the specified class. The class is first compared against known classes, and the closest class is used. 

            :param material_handling_class: Material handling class of which instances are listed.
            :return: Matched class and a list of identificators of instances, as '<label> is <description> [`<guid>`]'. If the class was not found, it returns list of most similar classes.
            """
            logger.info(f"--- get_list_of() {material_handling_class} ---")
            exact_match, res_list = self.sparql_tools.get_list(material_handling_class)

            result = ""
            res_list_len = len(res_list) if res_list is not None else 0
            if exact_match is not None:
                if res_list_len == 0:
                    return f"There are no instances of `{exact_match['term']}`."
                else:
                    result += f"List of instances of `{exact_match['term']}`:\n"
                    result += "\n".join(f"- `{inst['label']}` is {inst['description']} [`{inst['s']}`]" for inst in res_list) # type: ignore - because 0 len is checked incl None
            else:
                if res_list_len == 0:
                    return f"Nothing related to `{material_handling_class}` was found."
                else:
                    result += f"Exact term `{material_handling_class}` was not found. The list of most similar terms: "
                terms_str = ", ".join(f"`{t['term']}`" for t in res_list) # type: ignore - because 0 len is checked incl None
                result += f"{terms_str}."

            return result
        
        def get_materialflow_term_definition(self, term: str) -> str:
            """
            Gives a definition of specified material handling term. Must be used to determine a meaning of material handling term. Performs a fuzzy search.

            :param term: Material handling term to define and explain.
            :return: A list of closest definitions explaining the term in format 'definition. [optional superterm]. [optional subterms]'. If nothing was not found, returns a notification.
            """
            logger.info(f"--- get_materialflow_term_definition() {term} ---")
            exact_match, _, _, metas = self.sparql_tools.get_definition(term)

            def term_to_string(meta):
                res = f"`{meta['term']}` is {meta['explanation']} "
                if 'parent' in meta:
                    res += f"Superordinate term is `{meta['parent']}`. "
                if 'children' in meta:
                    children = json.loads(meta['children']) # unforchunatly openwebui uses old version of chromadb
                    if len(children) > 1:
                        res += f"Subordinate terms are {', '.join(f'`{c}`' for c in children)}. "
                    else:
                        res += f"Subordinate term is `{children[0]}`. "
                return res

            if exact_match is not None:
                return term_to_string(exact_match)
            
            result = f"Exact term `{term}` was not found. The list of most similar terms: \n"
            result += "\n".join(term_to_string(m) for m in metas)

            return result


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
        try:
            sparql_tools = SparqlTools(self.valves.SPARQL_BASE_URL, get_cache_path())
            self.tools = self.Tools(self, sparql_tools)
        except Exception as e:
            traceback.print_exc()
            raise

        logger.info(f"--- {self.name} Initialized ---")


    async def inlet(self, body: dict, user: Optional[dict] = None) -> dict:
        logger.info(f"--- {self.name} Called ---")
        # logger.info(f"{body}")

        res = await super().inlet(body, user)
        logger.info(f"-----------------")
        # logger.info(f"{body}")

        return res