FROM python:3.11-slim

WORKDIR /app

COPY generator.py /app/generator.py
COPY queries /app/queries

RUN pip install requests

CMD ["python", "generator.py"]
