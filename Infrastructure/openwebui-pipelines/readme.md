# OpenWebUI Pipelines Service

Backend service for custom pipeline execution in OpenWebUI. Pipelines extend OpenWebUI functionality with custom Python logic for processing chat messages, integrating external APIs, and implementing specialized workflows.


- **Internal Port**: 9099 (not exposed to host)


## Access

The pipelines service is **internal only** and accessed by OpenWebUI at:
- **URL**: `http://pipelines:9099` (Docker network DNS)
- **API Key**: (configured in docker-compose.yml)

## Connect to OpenWebUI
    
Pipelines must be manually registered in OpenWebUI:

1. Access OpenWebUI at `http://localhost:3000` (or configured port)
2. Navigate to: **Admin Panel > Settings > Connections**
3. Click: **Manage OpenAI API Connections**
4. Add new connection:
   - **URL**: `http://pipelines:9099`
   - **API Key**: (configured in docker-compose.yml)
5. Click **Verify Connection** to test
6. Pipelines will appear as additional "models" in chat interface

## Adding New Pipelines

### File Structure

Pipeline project has the following structure:

```
openwebui-pipelines/
└── app/                              <- uv project root
    ├── pipelines/ 
    │   └── <your_pipeline>.py  
    ├── prototypes/
    │    ├── utils/
    │    └── <your_pipeline_lib>/
	│	    └── <your_pipeline_code>.py
	└── data/
```

- `app/` - is a `uv` project root. You can run `uv` commands there. [What is uv?](https://docs.astral.sh/uv/)
- `app/pipelines/` - place your pipeline definitions there ([Pipeline definition template](#pipeline_template)). **Every** `.py` file from `/pipelines` folder is interpreted as a pipeline, thus **must** have `Pipeline` class defined 
- `app/prototypes/`- place your implementation here. 
  - To import your logic inside pipeline interface, use `from prototypes.<your_pipeline_lib>.<your_pipeline_code> import <>`
  - To test your implementation, run it as a module (to ensure correct pathing): `uv run -m prototypes.<your_pipeline_lib>.<your_pipeline_code>`
  - To add dependencies, do:
    1. `import <dep_name>`
    2. run `uv add <dep_name>`  
	3. Inside your pipeline definition add dependency to requirements list: `requirements: dep1, dep2, <dep_name>`
  - *ALL pipelines share the same environment inside container, and in uv project too*. 
- `app/data/` - intended to store cached data (e.g. embedding model files) to use, create a folder there. NOT mapped between host and container to avoid permissions errors, also to force data recreation inside container as a test

### OpenWebUI test

Once youre ready to run OpenWebUI test of your pipeline, follow these guidelines:
1. Ensure that you start containers with main `docker-compose` (called infrastructure) - OpenWebUI and must be in the same `docker-compose` group together. *Tip. once docker-compose group is set - you do not need all containers running. Keep open-webui, pipelines, graphdb running* 
2. Ensure that the service is connected to OpenWebUI. You should see pipeline valves at **Admin Panel > Settings > Pipelines**. Setup valve values there.
3. If your pipeline is missing (but service is connected):
   - See if your `<your_pipeline.py>` file got moved to `app/pipelines/failed`. If so, then it failed to import dependencies. Ensure that dependencies are specified correctly. *Tip. wrap imports with `import traceback try except traceback.print_exc()` - that will print detailed problem*. Do not forget to move your pipeline back when fixed.
   - Open `pipelines` container log: you can see there error traceback
   - To restart your pipeline, restart `pipelines` docker container.
4. If everything is good, your models should appear under models (but not if you created `filter` pipeline). Select one, try to chat with it

### Info
- `uv` can be used ONLY LOCALLY - inside container there is no uv - do not rely on it.
- if you prefer full isolation of your pipeline code, copy `openwebui-pipelines/` and use it as a template (you need to setup main `docker-compose.yml` yourself). 
- For individual prototypes documentation, look into `readme.md` inside `/app` dir 
- When you test with OpenWebUI, you can restart 
- When you test with OpenWebUI, your pipeline might fail. OpenWebUI moves failed pipelines to `pipelines/failed`! 

### Pipeline Template

```python
"""
title: Pipeline Name
author: ontobot
date: 2026-02-11
version: 1.0
description: Brief description of what this pipeline does.
requirements: package1, package2
"""

from typing import List, Union, Generator, Iterator
from pydantic import BaseModel

# use logger for reliable logging, as you work with async stuff
import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class Pipeline:
	class Valves(BaseModel):  # persistent settings of your pipeline. Some are required! read documentation!         
        OLLAMA_BASE_URL: str  # e.g
        OLLAMA_API_KEY: str   # e.g
		test_number:    int   # e.g

    def __init__(self):
		self.type = "manifold" | "pipe" | "filter" # require different initialization and methods, read documetation!
		self.id = "yourpipeline"                   # must have
        self.name = "YourPipeline/"                # something human readable, for "manifold" its a prefix, not used for "filter"
		# Initialize valves
		self.valves = self.Valves(
            **{
                "OLLAMA_BASE_URL": os.getenv("OLLAMA_BASE_URL", ""), # e.g
                "OLLAMA_API_KEY": os.getenv("OLLAMA_API_KEY", "")    # e.g
            }
        )
		
        # Initialize any other state/variables
        pass

    async def on_startup(self):
        # Called when server starts
        # Set up connections, load models, etc.
        pass

    async def on_shutdown(self):
        # Called when server stops
        # Clean up resources
        pass

    def pipe(
        self, user_message: str, model_id: str, messages: List[dict], body: dict
    ) -> Union[str, Generator, Iterator]:
        # Main processing logic
        # Return string, generator, or iterator
        return f"Processed: {user_message}"
```

## References

- [OpenWebUI Pipelines Documentation](https://docs.openwebui.com/features/pipelines/)
- [OpenWebUI GitHub](https://github.com/open-webui/open-webui)
- [Pipelines GitHub](https://github.com/open-webui/pipelines)
- [Pipelines Examples](https://github.com/open-webui/pipelines/tree/main/examples)
