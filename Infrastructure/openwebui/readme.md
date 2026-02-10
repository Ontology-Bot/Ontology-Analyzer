# OpenWebUI 

## How to use?

This setup is intended to use on your machine locally
By default, it uses uni API for ollama

### Beforehand
1. Docker compose here is designed to use pipelines! Read what are pipes and pipelines below, and if you need only pipes, remove `pipelines` in `docker-compose.yml` completely.
1. If you are using uni ollama (found at uni `https://genai-01.uni-hildesheim.de/`), proceed. Otherwise change url in `docker-compose.yml` first
2. Get hands on API key (found at `https://genai-01.uni-hildesheim.de/` > bottom left corner, user > settings > API keys).
3. (More configs at https://docs.openwebui.com/getting-started/quick-start/ https://docs.openwebui.com/getting-started/env-configuration)

### First start
1. run `docker compose up`
2. Wait several minutes until image is downloaded and container runs
3. Go to http://localhost:3000/ > Bottom left corner, User > Admin Panel > Settings > Connections > Ollama API (cog icon): add your API key there
4. Now you can use their models through your instance of OpenWebUI!

### Simple Pipes
1. We create pipe to inject our own behavior for the chat. A pipe is a simple wrapper for some remote call (to our prototype)
2. it has to be enabled first, Go to http://localhost:3000/ > Bottom left corner, User > Admin Panel > Settings >  
3. More docs at https://docs.openwebui.com/features/plugin/functions/pipe
4. Pipe is only a wrapper, heavy stuff must be hosted in a separate container for example. A nicer way is to use pipelines (below)

### Pipelines
1. Helper from OpenWebUI to containerize logic. We will add our prototypes as pipelines to isolate its logic
2. To use, main pipeline detection file goes to `./pipelines`. 
3. Then, run `docker compose up`
4. On first setup, go to http://localhost:3000/ > Bottom left corner, User > Admin Panel > Settings > Connections > Manage OpenAI API Connections > Plus Icon. 
As URL, enter `http://pipelines:9099`; as API key, enter API key specified in `docker-compose.yml` (PIPELINES_API_KEY). Now your pipeline must be available as model(s)
5. To update, `docker compose up -d --force-recreate pipelines`

### Other Materials:
1. Pipelines repo + examples - https://github.com/open-webui/pipelines/tree/main
2. Pipelines tutuorial: https://zohaib.me/extending-openwebui-using-pipelines/
