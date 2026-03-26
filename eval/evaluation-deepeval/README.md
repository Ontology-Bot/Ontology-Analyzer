# Evaluation with DeepEval

## Overview

This is an `uv` project, meaning you can run it locally for debugging, or you can use it as a part of the infrastructure through Docker container.

### GUI
To run gui, use `uv run uvicorn app.gui:app --reload`. By default, UI is launched at port `8000` *inside container* when it starts. It automatically uses local `.env` file.

### CLI
To launch project as cli, use `uv run -m app.cli <judge_model> <subject_models (comma sep)> <metrics (comma sep)> --env <env file> --testcases <golden-dataset.json>`

- judge model - name of a model, which is going to perform judging *for LLM-based metrics*.
- subject models - model name(s), which are going to be tested
- metrics - metric name(s), which are going to be used for evaluation. see `metrics.py` for names
- testcases - `.json` file with testcases. Format is specified below
- env - env file with API keys and base URLs. Format is specified below

### ENV file
ENV file requires following strings:
- `OPENAI_SUBJECT_BASE_URL` - URL for OpenAI compatible API, where tested models are located. For us its our openwebui `http://<openwebui>:<port>/api`
- `OPENAI_SUBJECT_API_KEY` - API key. For OpenWebUI create in your user account
- `OPENAI_JUDGE_BASE_URL` - URL for OpenAI compatible API, where judge models are located. You may use uni or chatai base url (make sure its OpenAI API).
- `OPENAI_JUDGE_API_KEY` - API key
- `DEEPEVAL_RESULTS_FOLDER` - evaluation results will be saved there

### golden-dataset.json
This file has following structure:
```
{"tests": [{
    "input": "...",
    "expected_output": "..."
}, {
    ...
}]}
```

- `input` and `expected_output` are mandatory.
- You may use `output` field to skip model call. Keep in mind `output` will be used for ALL models specified for the test run - use only when you test ONE model

### Project structure:
- `app`
  - `clients.py` - static OpenAI clients init
  - `metrics.py` - dictionary of available metrics. Register new metrics here, add them to `metrics_impl` folder.
  - `testcase_loader.py` - contains functions to preload dataset
  - `evaluator.py` - core evaluation logic
  - `scheuduler.py` - wrapper for `evaluator.py`, stores and tracks status info
  - `cli.py` - cli wrapper
  - `main.py` - gui wrapper
- `data`: put `golden-dataset.json` here