from sentence_transformers import SentenceTransformer
from hypergraph_model import HyperGraphDB
import chromadb
import os


class OGRAG:
    def __init__(self, top_k: int):
        self.top_k = top_k
        self.model = SentenceTransformer('BAAI/bge-small-en-v1.5')

        os.makedirs("./ontology_data", exist_ok=True)
        
        # chromadb
        self.vector_db = chromadb.PersistentClient(path="./ontology_data/chroma_db")
        self.collection_keys = self.vector_db.get_or_create_collection(name="ograg-keys")
        self.collection_values = self.vector_db.get_or_create_collection(name="ograg-values")

        # sqlite
        self.hypergraph_db = HyperGraphDB("/ontology_data/hypergraph.db")

        # Check if data is already ingested
        if self.collection_keys.count() == 0:
            print("Ingesting ontology for the first time...")
            self._ingest_ontology()


    def _ingest_ontology(self):
        pass


    def process(self, user_query: str):
        # 1. Embed user query
        query_embedding = self.model.encode(user_query).tolist()
        # 2. Find 2*k closest nodes
        nodes = []
        nodes.extend(self.collection_keys.query(
            query_embeddings=[query_embedding],
            n_results=self.top_k
        ))
        nodes.extend(self.collection_values.query(
            query_embeddings=[query_embedding],
            n_results=self.top_k
        ))
        
        # 3. Find edges which cover all nodes

        
        # 4. Form context
        