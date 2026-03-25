from SPARQLWrapper import SPARQLWrapper, JSON
from string import Template
import chromadb
import json

import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

from prototypes.utils.embedding_model import get_model
from prototypes.rag.stupidrag import Block, split_camel_case, to_camel, extract_guid

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


    def _make_query(self, body: str, header: str, limit: int, offset: int = 0):
        return f"{header}\n{body} LIMIT {limit} OFFSET {offset}"

    def _run_query(self, template: str, queries_limit=None, **kwargs):
        template = Template(template).substitute(**kwargs)
        # logger.info(f"query: {template}")

        limit = 500 if (queries_limit is None or queries_limit > 500) else queries_limit
        offset = 0
        while True:
            query = self._make_query(template, PREFIX, limit, offset)
            offset += limit

            logger.warning(f"querying next {limit} entries (total: {offset})...")

            self.sparql.setQuery(query)
            logger.info(query)
            try:
                results = self.sparql.queryAndConvert()
                bindings: list[dict[str, str]] = results["results"]["bindings"] # type: ignore
                if not bindings:
                    return
                
                # process results
                for i, row in enumerate(bindings):
                    row_vals: dict[str, str] = {}
                    # build sentence
                    for k, v in row.items():
                        # clean URIs
                        v = v['value'].split('/')[-1].split('#')[-1]  # type: ignore
                        v = v.removeprefix("MaterialFlow_")
                        row_vals[k] = v
                    # return row by row for further processing
                    yield row_vals

                # test exit 
                if len(bindings) < limit or (queries_limit is not None and ((limit + offset) > queries_limit)):
                    break
            
            except Exception as e:
                logger.error(f"SparqlTools: Error during SPARQL query: {e}")
                return

    def get_node_context(self, node_label_or_guid: str):
        ''' Performs exact match by laber or guid string using sparql query
        Returns list of sentences describing object under that label or guid
        Or None if not found
        '''
        query = None
        params = {}
        if extract_guid(node_label_or_guid) is None:
            # a label
            query = GET_NODE_CONTEXT
            params = {"label": node_label_or_guid}
        else:
            # a guid
            query = GET_NODE_CONTEXT_BY_GUID
            params = {"s": node_label_or_guid}

        block = None
        for row in self._run_query(query, node_label=node_label_or_guid):
            if block is None:
                # new block
                block = Block(**row, **params)
            block.add_attr(**row)
            block.add_connection(**row)
        return block
    

    def _test_exact_term_match(self, term: str, metas: list[chromadb.Metadata]):
        normalized_term = self._normalize_term(term) # to compare camel case with camel case
        for m in metas:
            t: str = m["term"] # type: ignore
            if normalized_term.lower() == t.lower():
                # exact match
                return normalized_term, m
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
        exact_match, _, _, metas = self.get_definition(term)
        print(exact_match)
        if metas is None or len(metas) < 1:
            return exact_match, None
        
        # test for exact match
        if exact_match is None:
            # not found - spit out 10 closest terms
            return exact_match, metas[0:10]

        result = []
        for row in self._run_query(GET_LIST, term=self._normalize_term(term)):
            result.append(row)
        
        return exact_match, result


    def get_definition(self, term: str):
        ''' Checks term using dictionary

        Return tuple[exact_match, texts, distances, metadatas]
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

        print(metadatas)
        print(distances)

        cutoff_index = next((idx for idx, d in enumerate(distances) if d > cutoff), len(distances))
        answers = answers[0:cutoff_index]
        distances = distances[0:cutoff_index]
        metadatas = metadatas[0:cutoff_index]

        exact_match, exact_match_meta = self._test_exact_term_match(term, metadatas)

        return exact_match_meta, answers, distances, metadatas, 


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

        for row in self._run_query(GET_DEFINITION):
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


GET_DEFINITION = """
SELECT ?class ?description ?child ?parent {
    ?class rdfs:subClassOf ?p .
    ?class rdfs:comment ?description .
    
    OPTIONAL {
        { ?child rdfs:subClassOf ?class }
        UNION
        { 
            ?class rdfs:subClassOf ?parent .
            FILTER NOT EXISTS {
                ?class rdfs:subClassOf ?mid .
                ?mid rdfs:subClassOf ?parent .
            }
        }
    }
    
    VALUES ?p {
        lib:MaterialFlow_Thing
        lib:MaterialFlow_InterfaceClass
    }
}
"""


GET_LIST = """
select ?s ?label ?description where {
    ?s rdfs:label ?label .
    ?s rdf:type lib:MaterialFlow_${term} .
    ?s rdfs:comment ?description .
}
"""


GET_NODE_CONTEXT = """
select ?s ?type ?description ?attrLabel ?attrComment ?rootAttr ?attr ?attrValue ?attrUnit ?attrType ?lnk ?lnkType ?lnkLabel where {
    ?s rdfs:label "${node_label}" .
    ?s rdf:type ?type .
    ?s rdfs:comment ?description .
    OPTIONAL {
        { 
            ?s :hasAttribute ?rootAttr .
            ?rootAttr :hasSubAttribute* ?attr .
            ?attr rdfs:label ?attrLabel .
            ?attr rdfs:comment ?attrComment .

            OPTIONAL { 
                ?attr :hasValue ?attrValue .
                ?attr :hasUnit ?attrUnit .
                ?attr :hasDataType ?attrType
            }
        }
        UNION
        {
            VALUES ?lnkType {
                :contains
                :containedIn
            }
            ?s ?lnkType ?lnk .
            ?lnk rdfs:label ?lnkLabel .
        }
    }
    
    
    FILTER(STRSTARTS(STR(?type), STR(lib:MaterialFlow_))) .
    FILTER(?type NOT IN (lib:MaterialFlow_InterfaceClass, lib:MaterialFlow_Thing))
}
"""

GET_NODE_CONTEXT_BY_GUID = """
select ?label ?type ?description ?attrLabel ?attrComment ?rootAttr ?attr ?attrValue ?attrUnit ?attrType ?lnk ?lnkType ?lnkLabel where {
    ?s rdfs:label ?label .
    ?s rdf:type ?type .
    ?s rdfs:comment ?description .
    OPTIONAL {
        { 
            ?s :hasAttribute ?rootAttr .
            ?rootAttr :hasSubAttribute* ?attr .
            ?attr rdfs:label ?attrLabel .
            ?attr rdfs:comment ?attrComment .

            OPTIONAL { 
                ?attr :hasValue ?attrValue .
                ?attr :hasUnit ?attrUnit .
                ?attr :hasDataType ?attrType
            }
        }
        UNION
        {
            VALUES ?lnkType {
                :contains
                :containedIn
            }
            ?s ?lnkType ?lnk .
            ?lnk rdfs:label ?lnkLabel .
        }
    }
    VALUES ?s {
        inst:${node_label}
    }
    
    
    FILTER(STRSTARTS(STR(?type), STR(lib:MaterialFlow_))) .
    FILTER(?type NOT IN (lib:MaterialFlow_InterfaceClass, lib:MaterialFlow_Thing))
}
"""

PREFIX = """
PREFIX : <http://www.semanticweb.org/AutomationML/ontologies/structure#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX lib: <http://www.semanticweb.org/AutomationML/ontologies/structure/libraries#>
PREFIX inst: <http://www.semanticweb.org/AutomationML/ontologies/structure/instances#>
"""