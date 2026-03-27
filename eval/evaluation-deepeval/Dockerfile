FROM python:3.11-slim

RUN mkdir -p /app

WORKDIR /app

COPY . .

RUN pip install uv
RUN uv sync --no-dev --frozen
# activate venv directly is not possible; full path here
ENV PATH="/app/.venv/bin:$PATH"

CMD ["uvicorn", "app.gui:app", "--host", "0.0.0.0", "--port", "8000"]