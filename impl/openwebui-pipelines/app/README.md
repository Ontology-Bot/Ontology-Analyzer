# Prototypes Project

## Available prototypes

### StupidRAG
- Pipeline: `app/pipelines/stupidrag.py`
- Prototype: `app/prototypes/stupidrag/stupidrag.py`
- Approach: embed triples into vector DB and retrieve nearest context.

### SelfQueryLLM
- Pipeline: `app/pipelines/selfquery_llm.py`
- Prototype: `app/prototypes/selfquery_llm/selfquery_llm.py`
- Approach:
	1. collect ontology schema metadata from SPARQL endpoint,
	2. ask LLM to generate multiple SPARQL candidates,
	3. validate and execute SELECT/ASK/CONSTRUCT queries,
	4. rank evidence and synthesize answer with query references.

## Configuration

SelfQueryLLM valves:
- `SPARQL_BASE_URL`
- `LLM_PROVIDER` (`openai_compat` or `ollama`)
- `LLM_BASE_URL`
- `LLM_API_KEY`
- `LLM_DEFAULT_MODEL` (optional, used when no model is selected)
- `top_k`
- `query_candidates`
- `timeout_sec`
- `max_rows`
- `max_triples`

## Data assumptions

- TTL files are imported into GraphDB before querying.
- Prototype queries all available graphs together (no explicit graph scoping).
- Endpoint must support SPARQL query operations.