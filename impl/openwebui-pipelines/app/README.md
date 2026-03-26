# Prototypes Project

## Utils
Before implementing your own logic, look at `prototypes/utils` folder. It may have what you need!
- `sparql/common.py` along some small stuff provides `run_query` - generator, which does batching and preprocessing, spitting out processed dictionaries. Use `for row in run_query(...):`
- (add your here)

## Available prototypes

### StupidRAG
- Pipeline: `app/pipelines/stupidrag.py`
- Type: `manifold`
- Prototype: `app/prototypes/stupidrag/stupidrag.py`
- Approach: extract context blocks (includes node label, descr, connections & attributes). Converts block to sentences, and embeds them (with a link to the whole block). Retrieval happens as top_k sentences similar to query are extracted, and their context blocks are given to an LLM as context.
- Strengths:
  - Really good at information questions (about a term or a node).
  - Works with weak models
- Known Weaknesses: 
  - If user asks a list query, it bumps into top_k. Increasing top_k, the risk for excessive information and pollution of context window
  - Quite limited 
- Valves:
  - `top_k` - how many blocks go into context
  - `LLM_PROVIDER` (`openai_compat` or `ollama`)
  - `LLM_BASE_URL` - for RAG chat completions
  - `LLM_API_KEY` 
  - `SPARQL_BASE_URL` - sparql endpoint

### ToolAssist
- Pipeline: `app/pipelines/toolassist.py`
- Type: `filter`
- Prototype: `app/prototypes/toolassist/sparql_tools.py`
- Approach: user questions are grouped into intent categories. Then for each category, a tool is made. 
- Tools:
  - get_node_context(node_label_or_guid) - extracts context Block for selected label (see `app/prototypes/utils/sparql/block.py`)
  - get_definition(term) - checks term using dictionary. Returns exact match or candidates (fuzzy search)
  - get_list(term) - first checks term using dictionary. If exact match found - performs full list extraction. Otherwise returns term candidates or nothing
  - get_path(node_label_or_guid, node_label_or_guid) **planned**
  - check_plant_integrity() **planned**
- Strengths:
  - High accuracy at the preset tasks
  - Testability & Traceability (white box tool code)
  - Extendability: modular approach
  - Can combine strengths of multiple approaches
- Known Weaknesses: 
  - Requires a strong model to operate the tools
  - If model misses tool selection, output will be empty
- Valves:
  - `TASK_MODEL` - for tool usage decision
  - `LLM_PROVIDER` (`openai_compat` or `ollama`)
  - `LLM_BASE_URL` - where task model available
  - `LLM_API_KEY` 
  - `TEMPLATE` - system prompt for answering model (retrieved context get pasted in it)
  - `SPARQL_BASE_URL` - sparql endpoint

### SelfQueryLLM
- Pipeline: `app/pipelines/selfquery_llm.py`
- Prototype: `app/prototypes/selfquery_llm/selfquery_llm.py`
- Approach:
	1. collect ontology schema metadata from SPARQL endpoint,
	2. ask LLM to generate multiple SPARQL candidates,
	3. validate and execute SPARQL read queries (write/update operations are rejected),
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

Notes:
- No `LIMIT` is injected by default into generated candidate queries.
- Setting `max_rows` or `max_triples` to a value <= `0` disables internal truncation.

## Data assumptions

- TTL files are imported into GraphDB before querying.
- Prototype queries all available graphs together (no explicit graph scoping).
- Endpoint must support SPARQL query operations.