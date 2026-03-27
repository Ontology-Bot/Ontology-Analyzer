from sentence_transformers import SentenceTransformer
from SPARQLWrapper import SPARQLWrapper, JSON
import chromadb

import logging

from prototypes.rag.hypergraph_model import HyperGraphDB
from prototypes.rag.embedding_model import get_model
from prototypes.utils.sparql.common import add_postfix, run_query
from prototypes.utils.sparql.block import Block

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

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

        blocks: dict[str, Block] = {}

        for row in run_query(sparql, QUERY, queries_limit):
            block_id = row["s"]
            block = blocks.get(block_id)
            if block is None:
                # new block
                block = Block(**row)
                blocks[block_id] = block
            block.add_attr(**row)
            block.add_connection(**row)

        #
        logger.info(f"finished sparql queries; start embedding of {len(blocks)} blocks...")
        # 
        for i, (k, block) in enumerate(blocks.items()):
            if (i+1) % 500 == 0:
                logger.info(f"finished embedding of {i} blocks...")
            
            texts, ids = block.to_sentences()
            # save block to db
            self.db.add_hyperedge(edge_key=k, node_map={id: text for id, text in zip(ids, texts)})
            # embed & store
            self._embed_and_store(ids, texts)
        #
        logger.info("ingestion completed successfully!")

    def _ingest_ontology_1(self):
        sparql = SPARQLWrapper(self.endpoint)
        sparql.setReturnFormat(JSON)

        # as ontology is very much sophisticated just to push
        QUERY = """
        SELECT ?class ?description {
            ?class rdfs:subClassOf ?p .
            ?class rdfs:comment ?description .
            
            VALUES ?p {
                lib:MaterialFlow_Thing
                lib:MaterialFlow_InterfaceClass
            }
        }
        """

        sentences = []
        ids = []
        for row in run_query(sparql, QUERY):
            sentence = ""
            # build sentence
            sentence = " ".join(row.values())
            sentences.append(sentence)
            ids.append(row["class"])

        # embed & store
        embeddings = self.model.encode(sentences).tolist()
        self.collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=sentences
        )

        logger.info("Ingestion complete.")