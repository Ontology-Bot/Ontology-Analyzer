# Neo4j 5 with n10s (Neosemantics)

Auto-configured Neo4j 5 with n10s plugin for RDF/TTL import.

## Prepare

1. Drop your `.ttl` (Turtle) ontology files into `./import/` folder

## Launch

From the `neo4j/` directory:
```bash
docker compose up
```

> ```bash
> docker compose --env-file ../.env up -d
> ```

## Access

- **Browser UI**: http://localhost:7474
- **Bolt**: bolt://localhost:7687
- **Cypher-shell**:
  ```bash
  docker exec -it neo4j cypher-shell -a bolt://localhost:7687
  ```

## How It Works

1. Neo4j starts with n10s + apoc plugins (auto-downloaded)
2. Once healthy, `neo4j-init` container runs
3. Init script:
   - Creates n10s constraint
   - Initializes n10s graph config (`handleVocabUris: SHORTEN`, `keepLangTag: true`)
   - Imports all `.ttl` files from `./import/`
4. Init container exits after import

## Test Import

```cypher
MATCH (n) RETURN count(n) AS nodes;
MATCH (n)-[r]->(m) RETURN n, r, m LIMIT 25;
```

## More

- n10s docs: https://neo4j.com/labs/neosemantics/
- Neo4j Browser: http://localhost:7474
