import os
from prototypes.querycaching.generator import MarkdownGenerator


class QueryCaching:
    def __init__(self, graphdb_endpoint: str, query_dir: str, output_dir: str):
        self.graphdb_endpoint = graphdb_endpoint
        self.query_dir = query_dir
        self.output_dir = output_dir

        self.generator = MarkdownGenerator(
            graphdb_endpoint=graphdb_endpoint,
            query_dir=query_dir,
            output_dir=output_dir,
        )

    def process(self, user_query: str) -> dict:
        generated_pages = self.generator.generate_all()

        return {
            "question": user_query,
            "generated_pages": generated_pages,
            "message": "Markdown knowledge base refreshed successfully.",
        }
