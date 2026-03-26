from prototypes.rag.hypergraph_model import HyperGraphDB
from prototypes.toolassist.sparql_tools import SparqlTools
from prototypes.utils.main import get_cache_path

from pipelines.toolassist import Pipeline

from openai import OpenAI

import sys
import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

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

    
if __name__ == "__main__":
    main()
