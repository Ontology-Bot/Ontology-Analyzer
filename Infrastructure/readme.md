# Infrastructure Setup and Usage Guide

- Read each folder's readme for instructions on how to set up and use the services. Each folder corresponds to a different component of the infrastructure, such as OpenWebUI, pipelines, and graph database.
- Don't forget to set up the license for GraphDB and populate the ontology files as described in the respective readme.
- For OpenWebUI, make sure to get the API key from the uni ollama instance and configure it in the OpenWebUI settings as described in the readme.

### RUNNING THE INFRASTRUCTURE
- You can run the entire infrastructure by running `docker compose up` from the root directory. This will start all the services defined in the docker-compose files across the different folders.
- If you want to run only specific services, navigate to the respective folder and run `docker compose up --env-file ../.env` there. For example, to run only OpenWebUI, go to the `openwebui/` folder and run `docker compose up --env-file ../.env` from there.
- Make sure to follow the specific instructions in each readme for any additional setup steps required for that service, such as configuring API keys or populating ontology files.
- After starting the services, you can access them as seen in docker compose files and readmes. Or better yet, We configured a reverse proxy in `traefik/` folder, so you can access all services through a hostname like `http://service-name.localhost`. 
```bash
# GRAPHDB_HOST=graphdb.localhost
# NEO4J_HOST=neo4j.localhost
# OPENWEBUI_HOST=webui.localhost
```

- Stop the infrastructure with `docker compose down`.