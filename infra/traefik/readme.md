# Traefik Reverse Proxy

Reverse proxy providing friendly `*.localhost` URLs for all services.
Uses file-based routing (no Docker socket required) for WSL compatibility.


## Access

| URL                                          | Service           |
| -------------------------------------------- | ----------------- |
| <http://graphdb.localhost>                   | GraphDB SPARQL    |
| <http://neo4j.localhost>                     | Neo4j Browser     |
| <http://webui.localhost>                     | Open WebUI        |
| <http://localhost:${TRAEFIK_DASHBOARD_PORT}> | Traefik Dashboard |

## Configuration

- [traefik.yml](traefik.yml): static config (entrypoints, providers, logging)
- [dynamic.yml](dynamic.yml): routers & services (route rules > backend URLs)

To add a new service, append a router + service block in `dynamic.yml`.
