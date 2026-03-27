from SPARQLWrapper import SPARQLWrapper
from string import Template

import re

import logging
logger = logging.getLogger(__name__)

PREFIX = """
PREFIX : <http://www.semanticweb.org/AutomationML/ontologies/structure#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX lib: <http://www.semanticweb.org/AutomationML/ontologies/structure/libraries#>
PREFIX inst: <http://www.semanticweb.org/AutomationML/ontologies/structure/instances#>
"""

def make_query(body: str, header: str, limit: int, offset: int = 0):
        return f"{header}\n{body} LIMIT {limit} OFFSET {offset}"

def run_query(sparql: SPARQLWrapper, template: str, queries_limit=None, **kwargs):
    template = Template(template).substitute(**kwargs)
    # logger.info(f"query: {template}")

    limit = 500 if (queries_limit is None or queries_limit > 500) else queries_limit
    offset = 0
    while True:
        query = make_query(template, PREFIX, limit, offset)
        offset += limit

        logger.info(f"querying next {limit} entries (total: {offset})...")
        logger.info(query)

        sparql.setQuery(query)
        try:
            results = sparql.queryAndConvert()
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

def preprocess_str(s: str):
    # remove prefix:
    s = s.removeprefix("MaterialFlow_")
    # reverse camel case
    s = split_camel_case(s)
    return s