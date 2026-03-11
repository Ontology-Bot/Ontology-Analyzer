from SPARQLWrapper import SPARQLWrapper, JSON
from string import Template
import chromadb

import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

from prototypes.utils.embedding_model import get_model

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
        logger.info(f"query: {template}")

        limit = 500 if (queries_limit is None or queries_limit > 500) else queries_limit
        offset = 0
        while True:
            query = self._make_query(template, PREFIX, limit, offset)
            offset += limit

            logger.warning(f"querying next {limit} entries (total: {limit + offset})...")

            self.sparql.setQuery(query)
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

    def get_node_context(self, node_label: str):
        for row in self._run_query(GET_NODE_CONTEXT, node_label=node_label):
            pass

    
    def get_list(self, term: str):
        # fuzzy compare
        opts = self.get_definition(term)
        if opts is None or len(opts) < 1:
            return
        # TODO test top 3 terms
        fterm = opts[0]
        for row in self._run_query(GET_LIST, term=fterm):
            pass

    def get_definition(self, term: str):
        cutoff = 0.8
        top_k = 30
        term_embedding = self.model.encode(term).tolist()

        # 2. Find k closest nodes
        res = self.dict_db.query(
            query_embeddings=[term_embedding],
            n_results=top_k
        )

        answers = res["documents"][0] # type: ignore
        distances = res["distances"][0] # type: ignore
        node_ids = res["ids"][0] # type: ignore

        cutoff_index = next((idx for idx, d in enumerate(distances) if d > cutoff), len(distances))
        answers = answers[0:cutoff_index]
        node_ids = node_ids[0:cutoff_index]

        return answers


    def _ingest_dictionary(self):
        queries = [
            """
            SELECT ?class ?description {
                ?class rdfs:subClassOf lib:MaterialFlow_Thing .
                ?class rdfs:comment ?description .
            }
            """,
            """
            SELECT ?class ?description {
                ?class rdfs:subClassOf lib:MaterialFlow_InterfaceClass .
                ?class rdfs:comment ?description .
            }
            """
        ]
        sentences = []
        ids = []
        for q in queries:
            for row in self._run_query(q):
                sentences.append(" ".join(row.values()))
                ids.append(row["class"])
        if len(sentences) == 0:
            logger.error("SparqlTools: failed to fetch definitions")
            return
        # 
        embeddings = self.model.encode(sentences).tolist()
        self.dict_db.add(
            ids=ids,
            embeddings=embeddings,
            documents=sentences,
            metadatas=[{"type": "definition"}] # Optional: for filtering later
        )



GET_LIST = """
select ?s ?label ?description where {
    ?s rdfs:label ? .
    ?s rdf:type lib:MaterialFlow_${term} .
    ?s rdfs:comment ?description .
}
"""


GET_NODE_CONTEXT = """
select ?s ?label ?type ?description ?attrLabel ?attrComment ?rootAttr ?attr ?attrValue ?attrUnit ?attrType ?lnkType ?lnkLabel where {
    ?s rdfs:label ${node_label} .
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

PREFIX = """
PREFIX : <http://www.semanticweb.org/AutomationML/ontologies/structure#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX lib: <http://www.semanticweb.org/AutomationML/ontologies/structure/libraries#>
"""