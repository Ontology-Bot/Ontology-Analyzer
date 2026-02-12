from prototypes.rag.hypergraph_model import HyperGraphDB
from prototypes.rag.stupidrag import StupidRAG
from prototypes.utils.main import get_cache_path

def main():
    print("Hello from rag-pipeline!")

    rag = StupidRAG(5, "http://localhost:7200/repositories/ontobot", get_cache_path())
    
    while True:
        q = input("Ask StupidRAG (empty to exit): ")
        if q == "":
            break
        ctx = rag.process(q)
        print("answer context: ")
        print(ctx)



if __name__ == "__main__":
    main()
