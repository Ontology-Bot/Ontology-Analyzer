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

            :param component_label_or_guid: Material handling component identificator. Can be short label, which consists of uppercase letters and/or numbers. Can be GUID.
            :return: Detailed information about specified component. If component was not found, returns a notification.
            """
            logger.info(f"--- get_materialflow_node_context() {component_label_or_guid} ---")
            res, block = self.sparql_tools.get_node_context(component_label_or_guid)
            if res == False: # component_label is ambiguous
                if len(block) > 0: # type: ignore - idk why typing fails. Here it is a list
                    return f"Label `{component_label_or_guid}` is ambiguous. Use GUID to reference this component"
                else:
                    return f"Label `{component_label_or_guid}` was not found"
            if block is None:
                return f"Instance `{component_label_or_guid}` was not found."
            ss, _ = block.to_sentences() # type: ignore - idk why typing fails. Here it is a Block

            tmp = '\n'.join(ss)
            return f"Information about `{component_label_or_guid}`:\n{tmp}."
        
        def get_list_of(self, material_handling_class: str) -> str:
            """
            Enumerates all material handling instances belonging to the specified class. The class is first compared against known classes, and the closest class is used. 

            :param material_handling_class: Material handling class of which instances are listed.
            :return: Matched class and a list of identificators of instances, as '<label> is <description> [`<guid>`]'. If the class was not found, it returns list of most similar classes.
            """
            logger.info(f"--- get_list_of() {material_handling_class} ---")
            exact_match_meta, res_list = self.sparql_tools.get_list(material_handling_class)

            result = ""
            res_list_len = len(res_list) if res_list is not None else 0
            if exact_match_meta is not None:
                if res_list_len == 0:
                    return f"There are no instances of `{exact_match_meta['term']}`."
                else:
                    result += f"List of instances of `{exact_match_meta['term']}`:\n"
                    result += "\n".join(f"- `{inst['label']}` is {inst['description']} [`{inst['guid']}`]" for inst in res_list) # type: ignore - because 0 len is checked incl None
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
            exact_match_meta, _, _, metas = self.sparql_tools.get_definition(term)

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

            if exact_match_meta is not None:
                return term_to_string(exact_match_meta)
            
            result = f"Exact term `{term}` was not found. The list of most similar terms: \n"
            result += "\n".join(term_to_string(m) for m in metas)

            return result


        def get_path_between_nodes(self, component_a, component_b) -> str:
            """
            Get a path from a material handling component A to B. Performs an exact search by label or GUID string.

            :param component_a: Material handling component A identificator. Can be short label, which consists of uppercase letters and/or numbers. Can be GUID.
            :param component_b: Material handling component B identificator. Can be short label, which consists of uppercase letters and/or numbers. Can be GUID.
            :return: Shortest path from A to B including all intermediate components. If error occured, returns
            """
            res, path = self.sparql_tools.get_path(component_a, component_b)
            if not res:
                err: tuple[list[str], list[str]] = path # type: ignore 
                res = ""
                if len(err[0]) > 1:
                    res += f"Label `{component_a}` is ambiguous. "
                elif len(err[0]) == 0 :
                    res += f"Label `{component_a}` was not found. "
                if len(err[1]) > 1:
                    res += f"Label `{component_b}` is ambiguous. "
                elif len(err[1]) == 0 :
                    res += f"Label `{component_b}` was not found. "
                return res
            if not path:
                return f"Path between `{component_a}` and `{component_b}` does not exist"
            is_fwd, path = path
            res = f"Path between `{component_a}` and `{component_b}` exists{' ' if is_fwd else ' but backward'} and is:\n"
            res += "\n".join([f"- {p.type} `{p.label}` (`{p.guid}`)" for p in path]) # type: ignore
            return res
            
        def check_materialflow_integrity(self):
            """
            Performs a check whether material flow graph has isolated components.

            :return: Success message, or list of isolated components
            """
            islands = self.sparql_tools.check_integrity()
            if len(islands) == 1:
                return "Material flow integrity check passed: no isolated components found."
            res = ""
            for idx, i in enumerate(islands):
                # print(f"island {idx} (size {len(i)}): ")
                res += f"island {idx} (size {len(i)}):\n"
                for c in i:
                    res += f"- {c.label} `{c.guid}`\n"
                    # print(f"\t- {c.label} {c.guid}")
            res = f"Material flow integrity check failed: contains isolated components with {len(islands) - 1} groups:\n{res}"
            # res += "\n".join([f"- {p.type} `{p.label}` (`{p.guid}`)" for p in islands[0]]) # type: ignore
            return res
            
        
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