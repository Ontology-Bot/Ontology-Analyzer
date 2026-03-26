from prototypes.rag.hypergraph_model import HyperGraphDB
from prototypes.stupidrag.stupidrag import StupidRAG
from prototypes.utils.main import get_cache_path

def main():
    print("Hello from rag-pipeline!")

    rag = StupidRAG("http://localhost:7200/repositories/ontobot", get_cache_path(), clean=True, queries_limit=2_000)
    # rag._ingest_ontology(2000)
    
    while True:
        q = input("Ask StupidRAG (empty to exit): ")
        if q == "":
            break
        ctx = rag.process(q, top_k=5, cutoff=0.5)
        print("answer context: ")
        print(ctx)


if __name__ == "__main__":
    main()
