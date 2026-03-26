FROM python:3.11-slim

RUN mkdir -p /app

WORKDIR /app

COPY ./app ./app
COPY ./data ./data

RUN pip install uv
RUN uv pip install -r pyproject.toml

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]