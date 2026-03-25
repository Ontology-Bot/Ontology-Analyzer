from sentence_transformers import SentenceTransformer
from SPARQLWrapper import SPARQLWrapper, JSON
import chromadb
import os

import logging

from prototypes.rag.hypergraph_model import HyperGraphDB
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

MODEL_NAME = 'BAAI/bge-small-en-v1.5'

PREFIX = """
    PREFIX : <http://www.semanticweb.org/AutomationML/ontologies/structure#>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
    PREFIX lib: <http://www.semanticweb.org/AutomationML/ontologies/structure/libraries#>
    """

import re

def extract_guid(s: str):
    pattern = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
    match = re.search(pattern, s)
    return match.group() if match else None

def split_camel_case(text: str):
    # Find uppercase letters and prepend a space
    result = re.sub(r'([A-Z])', r' \1', text)
    # Lowercase everything and strip leading/trailing whitespace
    return result.strip() # .lower()

def to_camel(text: str):
    # its fake camel because it starts with capital letter
    parts = text.split()
    if len(parts) == 0:
        return ""
    words = [p.capitalize() for p in parts]
    return "".join(words)

def add_postfix(texts: list[str], ids: list[str] | None = None, line_ending="\r\n"):
    for i, item in enumerate(texts):
        if ids is not None:
            yield f"{ids[i]}\t{item}{line_ending}"
        else:
            yield f"{item}{line_ending}"

def get_model(model_path):
    try:
        # 1. Try to load from local cache folder ONLY
        print(f"Checking for cached model at {model_path}...")
        return SentenceTransformer(MODEL_NAME, cache_folder=model_path, local_files_only=True)
    except (OSError, Exception):
        # 2. If it fails, download it
        print("Model not found locally. Downloading from Hugging Face...")
        return SentenceTransformer(MODEL_NAME, cache_folder=model_path, local_files_only=False)


def preprocess_str(s: str):
    # remove prefix:
    s = s.removeprefix("MaterialFlow_")
    # reverse camel case
    s = split_camel_case(s)
    return s

class BlockAttribute:
    def __init__(self, attrLabel: str, attrComment: str, attrValue: str = "", attrUnit: str = "", attrType: str = "", **kwargs) -> None:
        self.label = attrLabel
        self.descr = attrComment
        self.value = attrValue
        self.unit = attrUnit
        self.type = attrType
        self.subattrs: dict[str, BlockAttribute] = {}


class Connection:
    def __init__(self, lnk: str, lnkType: str, lnkLabel: str, **kwargs) -> None:
        self.type = split_camel_case(lnkType)
        self.guid = lnk
        self.label = lnkLabel

class Block:
    def __init__(self, s: str, label: str, description: str, type: str, **kwargs) -> None:
        self.guid = s
        self.label = label
        self.descr = description
        self.type = preprocess_str(type)
        self.attrs: dict[str, BlockAttribute] = {}
        self.connections: list[Connection] = []

    def add_attr(self, **kwargs) -> None:
        rootAttr = kwargs.get("rootAttr")
        attr = kwargs.get("attr")
        if rootAttr is None or attr is None: # ignore empty args
            return 
        # assume max 2 levels deep
        if rootAttr == attr: 
            self.attrs[rootAttr] = BlockAttribute(**kwargs)
        else: 
            self.attrs[rootAttr].subattrs[attr] = BlockAttribute(**kwargs)
    
    def add_connection(self, **kwargs) -> None:
        if kwargs.get("lnkLabel") is None: # ignore empty args
            return
        self.connections.append(Connection(**kwargs))

    def to_sentences(self) -> tuple[list[str], list[str]]:
        """ tuple[sentences, ids]
        """
        res = [f"Instance `{self.label}` [`{self.guid}`]", f"`{self.label}` is {self.type}", f"`{self.label}` is described as {self.descr}"]
        for a in self.attrs.values():
            if a.value: 
                res.append(f"`{self.label}` has `{a.label}` with value `{a.value} {a.unit}` described as {a.descr}")
            else:
                res.append(f"`{self.label}` has `{a.label}` described as {a.descr}")
            for sa in a.subattrs.values():
                if sa.value: 
                    res.append(f"`{self.label}` has `{a.label}` with `{sa.label}` equal `{sa.value} {sa.unit}`")
                else:
                    res.append(f"`{self.label}` has `{a.label}` with `{sa.label}`")
        for c in self.connections:
            res.append(f"`{self.label}` {c.type} `{c.label}` [`{c.guid}`]")
        return res, [f"{self.guid}:{i}" for i in range(len(res))]
    
    def __repr__(self) -> str:
        s, _ = self.to_sentences()
        return f"{s}"


class StupidRAG:
    def __init__(self, endpoint: str, cachepath: str, clean: bool = False, queries_limit = None):
        self.endpoint = endpoint

        self.model = get_model(f"{cachepath}/embedding_model_cache")
        self.cachepath = cachepath
        
        # chromadb
        self.vector_db = chromadb.PersistentClient(path=f"{cachepath}/chroma_db")
        self.collection = self.vector_db.get_or_create_collection(name="stupidrag")

        self.db = HyperGraphDB(f"{cachepath}/hypergraph.db")

        if clean:
            self.clear()

        # Check if data is already ingested
        if self.collection.count() == 0:
            logger.warning("StupidRAG: Ingesting ontology for the first time...")
            # clear cache
            with open(f"{self.cachepath}/sentences.txt", "w") as f:
                pass
            #
            self._ingest_ontology_1()
            self._ingest_ontology(queries_limit)


    def process(self, user_query: str, top_k: int = 5, cutoff: float = 0.8) -> list[str]:
        # 1. Embed user query
        query_embedding = self.model.encode(user_query).tolist()
        # 2. Find k closest nodes
        res = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k
        )
        # node ids = res.ids
        
        answers = res["documents"][0] # type: ignore
        distances = res["distances"][0] # type: ignore
        node_ids = res["ids"][0] # type: ignore

        # print(answers)
        # print(distances)
        # cutoff distance > 0.8 (cosine)
        print(f"Distances: {distances}")
        cutoff_index = next((idx for idx, d in enumerate(distances) if d > cutoff), len(distances))
        answers = answers[0:cutoff_index]
        node_ids = node_ids[0:cutoff_index]

        print(f"Filtered answers (cutoff={cutoff}): {answers}")
        # for each answer, fetch corresponding block
        edge_ids = {id.split(":")[0] for id in node_ids} # get edge keys
        hypernodes = self.db.get_hypernodes(list(edge_ids))
        
        return hypernodes


    def clear(self):
        logger.warning("StupidRAG: clearing embeddings...")
        self.db.clear()
        self.vector_db.delete_collection(name="stupidrag")
        self.collection = self.vector_db.create_collection(name="stupidrag")
        logger.warning("StupidRAG: cleared!")

    def _make_query(self, body: str, header: str, limit: int, offset: int = 0):
        return f"{header}\n{body} LIMIT {limit} OFFSET {offset}"
    

    def _embed_and_store(self, ids, texts):
        # logger.warning(text)
        embeddings = self.model.encode(texts).tolist()
        self.collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            # metadatas=[{"type": "node_content"}] # Optional: for filtering later
        )
        #
        # offload sentences to textfile to examine
        with open(f"{self.cachepath}/sentences.txt", "a") as f:
            f.writelines(add_postfix(texts, ids))
    

    def _test_query(self, query, limit):
        sparql = SPARQLWrapper(self.endpoint)
        sparql.setReturnFormat(JSON)

        query = self._make_query(PREFIX + query, "", limit, 0)
        sparql.setQuery(query)

        try:
            results = sparql.queryAndConvert()
            bindings: list[dict[str, str]] = results["results"]["bindings"] # type: ignore
            if not bindings:
                return []
            
            return bindings
        except Exception as e:
            print(f"Error during ingestion: {e}")
            return []


    
    def _process_query(self, bindings: list[dict[str, str]], vars: list[str]):
        # preprocess results
        sentences = []
        for i, row in enumerate(bindings):
            sentence = ""
            # build sentence
            for v in vars:
                # 2. Clean URIs to make them readable sentences
                val = row[v]['value'].split('/')[-1].split('#')[-1]  # type: ignore
                # preprocess:
                val = val.removeprefix("MaterialFlow_")

                sentence += f"{val} "

            sentences.append(sentence)
            # embed & store
            embedding = self.model.encode(sentence).tolist()
            self.collection.add(
                ids=[f"{i}"],
                embeddings=[embedding],
                documents=[sentence],
                metadatas=[{"type": "node_content"}] # Optional: for filtering later
            )
        

    def _ingest_ontology(self, queries_limit: int | None = None):
        QUERY = """
select ?s ?label ?type ?description ?attrLabel ?attrComment ?rootAttr ?attr ?attrValue ?attrUnit ?attrType ?lnk ?lnkType ?lnkLabel where {
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
    
    
    FILTER(STRSTARTS(STR(?type), STR(lib:MaterialFlow_))) .
    FILTER(?type NOT IN (lib:MaterialFlow_InterfaceClass, lib:MaterialFlow_Thing))
}
            """
        sparql = SPARQLWrapper(self.endpoint)
        sparql.setReturnFormat(JSON)

        limit = 500  # Number of triplets per batch
        offset = 0

        blocks: dict[str, Block] = {}

        while True:
            query = self._make_query(QUERY, PREFIX, limit, offset)
            offset += limit

            logger.warning(f"querying next {limit} entries (total: {limit + offset})...")

            sparql.setQuery(query)

            try:
                results = sparql.queryAndConvert()
                bindings: list[dict[str, str]] = results["results"]["bindings"] # type: ignore
                if not bindings:
                    break
                
                # process results
                for i, row in enumerate(bindings):
                    row_vals: dict[str, str] = {}
                    # build sentence
                    for k, v in row.items():
                        # clean URIs
                        row_vals[k] = v['value'].split('/')[-1].split('#')[-1]  # type: ignore
                    #
                    block_id = row_vals["s"]
                    block = blocks.get(block_id)
                    if block is None:
                        # new block
                        block = Block(**row_vals)
                        blocks[block_id] = block
                    block.add_attr(**row_vals)
                    block.add_connection(**row_vals)

                # test exit condition
                if len(bindings) < limit or (queries_limit is not None and ((limit + offset) > queries_limit)):
                    break

            except Exception as e:
                logger.error(f"Error during ingestion: {e}")
                return
        #
        logger.warning(f"finished sparql queries; start embedding of {len(blocks)} blocks...")
        # 
        for i, (k, block) in enumerate(blocks.items()):
            if (i+1) % 500 == 0:
                logger.warning(f"finished embedding of {i} blocks...")
            
            texts, ids = block.to_sentences()
            # save block to db
            self.db.add_hyperedge(edge_key=k, node_map={id: text for id, text in zip(ids, texts)})
            # embed & store
            self._embed_and_store(ids, texts)
        #
        logger.warning("ingestion completed successfully!")

    def _ingest_ontology_1(self):
        sparql = SPARQLWrapper(self.endpoint)
        sparql.setReturnFormat(JSON)

        # as ontology is very much sophisticated just to push
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
        query_vars = [["class", "description"], ["class", "description"]]

        # 1. Fetch triplets in batches
        for q, v in zip(queries, query_vars):
            limit = 500
            offset = 0
            while True:
                query = self._make_query(q, PREFIX, limit, offset)
                offset += limit

                sparql.setQuery(query)

                try:
                    results = sparql.queryAndConvert()
                    bindings: list[dict[str, str]] = results["results"]["bindings"] # type: ignore
                    if not bindings:
                        return
                    
                    # process results
                    self._process_query(bindings, v)

                    if len(bindings) < limit:
                        break

                except Exception as e:
                    logger.error(f"Error during ingestion: {e}")
                    return
        

        logger.warning("Ingestion complete.")