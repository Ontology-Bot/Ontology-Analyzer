# OpenWebUI 

## How to use?

This setup is intended to use on your machine locally
By default, it uses uni API for ollama

### Beforehand
1. If you are using uni ollama (found at uni `https://genai-01.uni-hildesheim.de/`), proceed. Otherwise change url in `docker-compose.yml` first
2. Get hands on API key (found at `https://genai-01.uni-hildesheim.de/` > bottom left corner, user > settings > API keys).
3. (More configs at https://docs.openwebui.com/getting-started/quick-start/ https://docs.openwebui.com/getting-started/env-configuration)

### First start
1. run `docker compose up` from this directory

> ```bash
> docker compose --env-file ../.env up 
> ```
2. Wait several minutes until image is downloaded and container runs
3. Go to http://localhost:3000/ > Bottom left corner, User > Admin Panel > Settings > Connections > Ollama API (cog icon): add your API key there
4. Now you can use their models through your instance of OpenWebUI!

### Simple Pipes
1. We create pipe to inject our own behavior for the chat. A pipe is a simple wrapper for some remote call (to our prototype)
2. it has to be enabled first, Go to http://localhost:3000/ > Bottom left corner, User > Admin Panel > Settings >  
3. More docs at https://docs.openwebui.com/features/plugin/functions/pipe
4. Pipe is only a wrapper, heavy stuff must be hosted in a separate container for example. A nicer way is to use pipelines (below)

### Pipelines
- See `Infrastructure/openwebui-pipelines/` for more details on pipelines, which are a more powerful way to extend OpenWebUI with custom Python code. Pipelines run in a separate container and can be accessed by OpenWebUI via an internal API.

### Other Materials:
1. Pipelines repo + examples - https://github.com/open-webui/pipelines/tree/main
2. Pipelines tutuorial: https://zohaib.me/extending-openwebui-using-pipelines/
