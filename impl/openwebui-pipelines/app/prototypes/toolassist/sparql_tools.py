from SPARQLWrapper import SPARQLWrapper, JSON
from string import Template
import chromadb
import json

import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

from prototypes.rag.embedding_model import get_model
from prototypes.utils.sparql.common import run_query, extract_guid, to_camel, split_camel_case
from prototypes.utils.sparql.sparql_queries import *
from prototypes.utils.sparql.block import Block
from prototypes.toolassist.pathfinding import PathFinder

from typing import List
class SparqlTools:
    def __init__(self, endpoint: str, cachepath: str, clean: bool = False):
        self.endpoint = endpoint
        self.cachepath = cachepath
        
        self.sparql = SPARQLWrapper(self.endpoint)
        self.sparql.setReturnFormat(JSON)

        self.vector_db = chromadb.PersistentClient(path=f"{cachepath}/chroma_db")
        self.dict_db = self.vector_db.get_or_create_collection(name="dictionary")
        self.model = get_model(f"{cachepath}/embedding_model_cache")

        self.pathfinder = PathFinder()
        self._build_path_cache()

        if clean:
            self.clear()

        if self.dict_db.count() == 0:
            logger.warning("SparqlTools: Ingesting dictionary...")
            self._ingest_dictionary()
        

    def clear(self):
        logger.warning("SparqlTools: clearing...")
        self.vector_db.delete_collection(name="dictionary")
        self.dict_db = self.vector_db.create_collection(name="dictionary")
        logger.warning("SparqlTools: cleared!")

    def get_node_context(self, node: str):
        ''' Performs exact match by label or guid string using sparql query

        Returns (True, Block | None)
        Or (False, list of candidate guids) if ambuguous
        '''
        guids = self._label_to_guids(node)
        if len(guids) != 1: # not found
            return False, guids

        block = None
        for row in run_query(self.sparql, GET_NODE_CONTEXT, guid=guids[0]):
            if block is None:
                # new block
                block = Block(**row)
            block.add_attr(**row)
            block.add_connection(**row)
        return True, block
    

    def _test_exact_term_match(self, term: str, metas: list[chromadb.Metadata]) -> tuple[str | None, chromadb.Metadata | None]:
        normalized_term = self._normalize_term(term) # to compare camel case with camel case
        for m in metas:
            t: str = m["term"] # type: ignore
            if normalized_term.lower() == t.lower() and isinstance(m["term"], str):
                # exact match
                return m["term"], m
        return None, None
    
    def _normalize_term(self, term):
        return to_camel(term.strip()) # to compare camel case with camel case

    
    def get_list(self, term: str):
        ''' Checks term using dictionary
        If exact match exists - queries and returns full list of identificators
        If exact match fails - returns list of similar terms

        Return tuple[exact_match, list of ids | list of term metadatas]
        '''

        # get from dict
        exact_match_meta, _, _, metas = self.get_definition(term)
        if metas is None or len(metas) < 1:
            return None, None
        
        # test for exact match
        if exact_match_meta is None:
            # not found - spit out 10 closest terms
            return exact_match_meta, metas[0:10]

        result = []
        for row in run_query(self.sparql, GET_LIST, term=exact_match_meta["term"]):
            result.append(row)
        
        return exact_match_meta, result


    def get_definition(self, term: str):
        ''' Checks term using dictionary

        Return tuple[exact_match_meta ("term", "explanation"), candidates, distances, metadatas]
        '''

        cutoff = 0.6
        top_k = 30
        term_embedding = self.model.encode(term).tolist()

        # 2. Find k closest nodes
        res = self.dict_db.query(
            query_embeddings=[term_embedding],
            n_results=top_k
        )

        if res["documents"] is None or res["distances"] is None or res["metadatas"] is None:
            raise ValueError("get_definition: sparql query returned malformed data")
        answers = res["documents"][0]
        distances = res["distances"][0] 
        metadatas = res["metadatas"][0] 
        # node_ids = res["ids"][0]

        cutoff_index = next((idx for idx, d in enumerate(distances) if d > cutoff), len(distances))
        answers = answers[0:cutoff_index]
        distances = distances[0:cutoff_index]
        metadatas = metadatas[0:cutoff_index]

        exact_match, exact_match_meta = self._test_exact_term_match(term, metadatas) # metadata: term, explanation - see _ingest_dictionary

        return exact_match_meta, answers, distances, metadatas 


    def _ingest_dictionary(self):
        # term dictionary is a tree
        class Node:
            def __init__(self, definition: str, explanation: str) -> None:
                self.definition: str = definition
                self.explanation = explanation
                self.children: List[str] = []
                self.parent: str | None = None

            def set_parent(self, parent: str):
                self.parent = parent

            def add_child(self, child: str):
                self.children.append(child)
    
        terms: dict[str, Node] = {} # key: parent, children, definition

        for row in run_query(self.sparql, GET_DEFINITION):
            id = row["class"]
            term = terms.get(id)
            if term is None:
                term = Node(f"{split_camel_case(row['class'])} {row['description']}", row['description'])
                terms[id] = term
            if "child" in row:
                term.add_child(row["child"])
            if "parent" in row:
                term.set_parent(row["parent"]) 
            
        if len(terms) == 0:
            logger.error("SparqlTools: failed to fetch definitions")
            return
        # 
        sentences = []
        metadatas = []
        ids = []
        terminology = []
        for k, t in terms.items():
            ids.append(k)
            terminology.append(split_camel_case(k))
            sentences.append(t.definition)
            m: chromadb.Metadata = {"term": k, "explanation": t.explanation}
            if t.parent is not None:
                m["parent"] = t.parent 
            if len(t.children) > 0:
                m["children"] = json.dumps(t.children) # it can work with lists, but openwebui uses old version :/ # type: ignore - list[str] is not assignable to list[str | ...] - wtf
            metadatas.append(m)

        # embed terms with explanation
        embeddings = self.model.encode(sentences).tolist()
        self.dict_db.add(
            ids=ids,
            embeddings=embeddings,
            documents=sentences,
            metadatas=metadatas
        )

        # embed terms themselves
        # embeddings = self.model.encode(sentences).tolist()
        # self.dict_db.add(
        #     ids=terminology,
        #     embeddings=embeddings,
        #     documents=terminology,
        #     metadatas=metadatas
        # )

    def _build_path_cache(self):
        for row in run_query(self.sparql, GET_CONNECTIONS):
            # print(row)
            self.pathfinder.add_connection(row)

    def get_path(self, node_a: str, node_b: str):
        """ Returns (True, path | None)
            Or (False, guids node a, guids node b) if labels are ambiguous
        """
        guids_a = self._label_to_guids(node_a)
        guids_b = self._label_to_guids(node_b)

        if len(guids_a) == 1 and len(guids_b) == 1:
            fwd_path = self.pathfinder.get_path(guids_a[0], guids_b[0])
            if fwd_path:
                return True, (True, fwd_path)
            bwd_path = self.pathfinder.get_path(guids_b[0], guids_a[0])
            if bwd_path:
                return True, (False, bwd_path)
            return True, None
        return False, (guids_a, guids_b)
    
    def check_integrity(self):
        return self.pathfinder.get_islands()
                
    def get_guid(self, label: str):
        """ Returns list of matching guids for label
        """
        res: list[str] = []
        for row in run_query(self.sparql, GET_GUID, label=label):
            res.append(row["guid"])
        return res
    
    def _label_to_guids(self, node: str):
        if extract_guid(node): 
            return [node] 
        return self.get_guid(node)

