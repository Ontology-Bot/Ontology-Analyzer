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

Place Python files in `pipelines/` directory:
```
openwebui-pipelines/
├── pipelines/
│   ├── test-pipeline.py
│   ├── my-custom-pipeline.py
│   └── another-pipeline.py
```

> I would recommend to even copy the whole directory with the template and just change the template file for each new pipeline. This way you have all the freedom to add any additional files you need for your pipeline.

### Pipeline Template

```python
"""
title: Pipeline Name
author: your-name
date: 2026-02-11
version: 1.0
description: Brief description of what this pipeline does.
requirements: package1, package2
"""

from typing import List, Union, Generator, Iterator
from schemas import OpenAIChatMessage


class Pipeline:
    def __init__(self):
        # Initialize any state/variables
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
