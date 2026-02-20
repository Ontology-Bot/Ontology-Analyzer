from sentence_transformers import SentenceTransformer
from SPARQLWrapper import SPARQLWrapper, JSON
import chromadb
import os

MODEL_NAME = 'BAAI/bge-small-en-v1.5'

def get_model(model_path):
    try:
        # 1. Try to load from local cache folder ONLY
        print(f"Checking for cached model at {model_path}...")
        return SentenceTransformer(MODEL_NAME, cache_folder=model_path, local_files_only=True)
    except (OSError, Exception):
        # 2. If it fails, download it
        print("Model not found locally. Downloading from Hugging Face...")
        return SentenceTransformer(MODEL_NAME, cache_folder=model_path, local_files_only=False)

class StupidRAG:
    def __init__(self, top_k: int, endpoint: str, cachepath: str):
        self.top_k = top_k
        self.endpoint = endpoint

        self.model = get_model(f"{cachepath}/embedding_model_cache")
        
        # chromadb
        self.vector_db = chromadb.PersistentClient(path=f"{cachepath}/chroma_db")
        self.collection = self.vector_db.get_or_create_collection(name="stupidrag")

        # Check if data is already ingested
        if self.collection.count() == 0:
            print("StupidRAG: Ingesting ontology for the first time...")
            self._ingest_ontology()


    def process(self, user_query: str):
        # 1. Embed user query
        query_embedding = self.model.encode(user_query).tolist()
        # 2. Find 2*k closest nodes
        nodes = []
        res = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=self.top_k
        )
        # node ids = res.ids
        answers = res["documents"][0] # type: ignore
        distances = res["distances"][0] # type: ignore

        # print(answers)
        # print(distances)

        for i, d in enumerate(res["distances"][0]): # type: ignore
            if d > 0.5:
                answers = answers[0:i]
                break
        
        return answers


    def clean(self):
        self.collection.delete()

    def _make_query(self, body: str, header: str, limit: int, offset: int = 0):
        return f"{header}\n{body} LIMIT {limit} OFFSET {offset}"

    def _ingest_ontology(self):
        sparql = SPARQLWrapper(self.endpoint)
        sparql.setReturnFormat(JSON)

        limit = 100  # Number of triplets per batch
        offset = 0

        # while True:
        prefix = """
            PREFIX lib: <http://www.semanticweb.org/AutomationML/ontologies/structure/libraries#>
            PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
            """
        # as ontology is very much sophisticated just to push
        queries = [

            """
            SELECT ?s ?p ?o WHERE {
                ?s ?p ?o .
            }
            """
        ]
        query_vars = [["class", "description"]]

        # 1. Fetch triplets in batches
        query = self._make_query(queries[0], prefix, 100)
        vars = query_vars[0]
        sparql.setQuery(query)

        try:
            results = sparql.queryAndConvert()
            bindings = results["results"]["bindings"] # type: ignore
            if not bindings:
                return
            
            sentences = []
            for i, row in enumerate(bindings):
                sentence = ""
                for v in vars:
                    # 2. Clean URIs to make them readable sentences
                    val = row[v]['value'].split('/')[-1].split('#')[-1]  # type: ignore
                    # preprocess:
                    val = val.removeprefix("MaterialFlow_")

                    sentence += f"{val} "

                # Embed & store
                embedding = self.model.encode(sentence).tolist()
                self.collection.add(
                    ids=[f"{i}"],
                    embeddings=[embedding],
                    documents=[sentence],
                    metadatas=[{"type": "node_content"}] # Optional: for filtering later
                )

                # sentences.append(sentence)

        except Exception as e:
            print(f"Error during ingestion: {e}")
            # break
            return

        print("Ingestion complete.")
