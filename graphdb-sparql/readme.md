# Info
It should auto-create sparql endpoint and web-ui for debugging
It should auto-populate ontology from `./_secret`

# Prepare:
1. Get your .license here: `https://www.ontotext.com/products/graphdb/#:~:text=Request%20GraphDB%20License` (will sent file to email)
2. Rename it to `graphdb.license` and put into into the folder besides `Dockerfile` and `docker-compose.yml`
3. Put ontology files into `./_secret`

# Launch:
1. Run `docker compose up`
2. Access web ui at `http://localhost:7200/` 
3. Run sparql queries to `http://localhost:7200/repositories/ontobot`
```bash
curl -s -G "http://localhost:7200/repositories/ontobot" --data-urlencode 'query=ASK { ?s ?p ?o }'
```

# More:
- Change `GRAPHDB_URL` or `REPO_ID` in `docker-compose.yml`
- Creates additional container `graphdb-init` to bootstrap Repository (load Ontology files)