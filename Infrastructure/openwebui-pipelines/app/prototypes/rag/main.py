from prototypes.rag.hypergraph_model import HyperGraphDB
from prototypes.rag.stupidrag import StupidRAG, split_camel_case
from prototypes.rag.sparql_tools import SparqlTools
from prototypes.utils.main import get_cache_path

from pipelines.toolassist import Pipeline

from openai import OpenAI

import sys
import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# def main():
#     API_URL = "https://chat-ai.academiccloud.de/v1"  # replace with your API URL
#     API_KEY = "264c2532514e0ddf975695ffad589653"     # replace with your API key

#     client = OpenAI(
#         api_key = API_KEY,
#         base_url = API_URL
#     )
#     print(client.models.list())

#     chat_completion = client.chat.completions.create(
#         messages=[{"role":"system","content":"You are a helpful assistant"},{"role":"user","content":"How tall is the Eiffel tower?"}],
#         model="meta-llama-3.1-8b-instruct",
#     )
#     print(chat_completion)

    

#     # chat_completion = client.chat.completions.create(
#     #     messages=[{"role":"system","content":"You are a helpful assistant"},{"role":"user","content":"How tall is the Eiffel tower?"}],
#     #     model= client.models.list(),
#     # )
  
#     # Print full response as JSON
#     # print(chat_completion) # You can extract the response text from the JSON object

    

def main():
    print("Hello from sparql tools tester!")

    clean = True
    st = SparqlTools("http://localhost:7200/repositories/ontobot", get_cache_path(), clean=clean)
    # print(st.get_definition("material handling component"))
    # print(st.get_definition("work cell"))
    # print(st.get_definition("DoubleTrack"))
    # print(st.get_definition("roll conveyor"))
    # print(st.get_definition("conveyor"))

    # print(st.get_list("roll conveyor")) # ?

    # print(st.get_list("conveyor")) # ?


    # print(st.get_node_context("TL109"))
    # print(st.get_node_context("TL111"))
    # print(st.get_node_context("Instance_BMW_Group_836f5ffb-8d65-4495-86d4-677081e3142a"))


    # test tools
    tools = Pipeline.Tools(None, st)

    # print(tools.get_materialflow_term_definition("BeltConveyor"))

    print(tools.get_list_of("WorkCell")) # ?
    print(tools.get_list_of("Production line")) # ?
    print(tools.get_list_of("RollConveyor")) # ?


    # print(tools.get_materialflow_term_definition("material handling component"))
    # print(tools.get_materialflow_term_definition("work cell"))
    # print(tools.get_materialflow_term_definition("DoubleTrack"))
    # print(tools.get_materialflow_term_definition("roll conveyor"))
    # print(tools.get_materialflow_term_definition("conveyor"))

    # print(tools.get_list_of("roll conveyor")) # ?

    # print(tools.get_list_of("conveyor")) # ?

    # print(tools.get_materialflow_node_context("TL109"))
    # print(tools.get_materialflow_node_context("TL000"))
    # print(tools.get_materialflow_node_context("Instance_BMW_Group_836f5ffb-8d65-4495-86d4-677081e3142a"))

    



# def main():
#     print("Hello from rag-pipeline!")

#     rag = StupidRAG("http://localhost:7200/repositories/ontobot", get_cache_path(), clean=True, queries_limit=2_000)
#     # rag._ingest_ontology(2000)
    
#     while True:
#         q = input("Ask StupidRAG (empty to exit): ")
#         if q == "":
#             break
#         ctx = rag.process(q, top_k=5, cutoff=0.5)
#         print("answer context: ")
#         print(ctx)


# from SPARQLWrapper import SPARQLWrapper, JSON
# from prototypes.rag.stupidrag import PREFIX
# def test_sparql_query(endpoint, query):
#         sparql = SPARQLWrapper(endpoint)
#         sparql.setReturnFormat(JSON)

#         query = self._make_query(PREFIX + query, "", 100, 0)
#         sparql.setQuery(query)

#         sentences = []
#         try:
#             results = sparql.queryAndConvert()
#             bindings: dict[str, dict[str, str]] = results["results"]["bindings"] # type: ignore
#             if not bindings:
#                 return []
            
#             # process results
#             for i, row in enumerate(bindings):
#                 sentence = ""

#                 for _, v in row:
#                     val = v['value'].split('/')[-1].split('#')[-1]  # type: ignore
#                     sentence += f"{val} "

#                 sentences.append(sentence)
                
#             return sentences
#         except Exception as e:
#             print(f"Error during ingestion: {e}")
#             return []


def main1():
    rag = StupidRAG("http://localhost:7200/repositories/ontobot", get_cache_path())
    res = rag._test_query("""
select * where {
    ?s rdfs:label ?label .
    ?s rdf:type ?type .
    ?s rdfs:comment ?description .
    OPTIONAL { 
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
    
    FILTER(STRSTARTS(STR(?type), STR(lib:MaterialFlow_))) .
}
                    """, 1)
    print(res)


if __name__ == "__main__":
    print(split_camel_case("not camel case str"))
    main()
