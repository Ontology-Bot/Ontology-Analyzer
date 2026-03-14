import os
import glob
import requests
from datetime import datetime


class MarkdownGenerator:
    def __init__(self, graphdb_endpoint: str, query_dir: str, output_dir: str):
        self.graphdb_endpoint = graphdb_endpoint
        self.query_dir = query_dir
        self.output_dir = output_dir

    def run_sparql(self, query: str) -> dict:
        r = requests.post(
            self.graphdb_endpoint,
            data=query.encode("utf-8"),
            headers={
                "Accept": "application/sparql-results+json",
                "Content-Type": "application/sparql-query; charset=utf-8",
            },
            timeout=60,
        )

        if not r.ok:
            raise RuntimeError(
                f"GraphDB SPARQL error {r.status_code}\n"
                f"Endpoint: {self.graphdb_endpoint}\n"
                f"Response:\n{r.text}\n"
            )

        return r.json()

    def to_md_table(self, sparql_json: dict):
        vars_ = sparql_json.get("head", {}).get("vars", [])
        rows = sparql_json.get("results", {}).get("bindings", [])
        if not vars_:
            return "_No columns returned._\n", 0

        md = "| " + " | ".join(vars_) + " |\n"
        md += "| " + " | ".join(["---"] * len(vars_)) + " |\n"
        for row in rows:
            md += "| " + " | ".join(row.get(v, {}).get("value", "") for v in vars_) + " |\n"
        return md, len(rows)

    def title_from_filename(self, path: str) -> str:
        name = os.path.basename(path).replace(".rq", "")
        return name.replace("_", " ").replace("-", " ").title()

    def write_page(self, md_path: str, title: str, row_count: int, table_md: str, query: str):
        content = []
        content.append(f"# {title}\n")
        content.append(f"Rows: **{row_count}**\n")
        content.append(table_md + "\n")
        content.append("## SPARQL Query\n")
        content.append("```sparql\n" + query.strip() + "\n```\n")
        content.append(f"_Generated: {datetime.utcnow().isoformat()}Z_\n")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write("\n".join(content))

    def generate_all(self) -> list[str]:
        os.makedirs(self.output_dir, exist_ok=True)
        query_files = sorted(glob.glob(os.path.join(self.query_dir, "*.rq")))
        if not query_files:
            raise SystemExit(f"No .rq files found in {self.query_dir}")

        generated_pages = []
        index_lines = ["# Plant Wiki Index\n", f"_Generated: {datetime.utcnow().isoformat()}Z_\n"]

        for qf in query_files:
            with open(qf, "r", encoding="utf-8") as f:
                query = f.read()

            data = self.run_sparql(query)
            table_md, count = self.to_md_table(data)

            page_name = os.path.basename(qf).replace(".rq", "") + ".md"
            page_path = os.path.join(self.output_dir, page_name)
            title = self.title_from_filename(qf)

            self.write_page(page_path, title, count, table_md, query)
            index_lines.append(f"- [{title}]({page_name}) — rows: {count}")
            generated_pages.append(page_name)

        with open(os.path.join(self.output_dir, "index.md"), "w", encoding="utf-8") as f:
            f.write("\n".join(index_lines) + "\n")

        generated_pages.append("index.md")
        return generated_pages


if __name__ == "__main__":
    graphdb_endpoint = os.getenv("GRAPHDB_ENDPOINT", "http://host.docker.internal:7200/repositories/ontobot")
    query_dir = os.getenv("QUERY_DIR", "/app/queries")
    output_dir = os.getenv("OUTPUT_DIR", "/app/output")

    print(f"GRAPHDB_ENDPOINT={graphdb_endpoint}")
    print(f"QUERY_DIR={query_dir}")
    print(f"OUTPUT_DIR={output_dir}")

    generator = MarkdownGenerator(
        graphdb_endpoint=graphdb_endpoint,
        query_dir=query_dir,
        output_dir=output_dir,
    )

    generated_pages = generator.generate_all()
    print("Generated pages:")
    for page in generated_pages:
        print(f"- {page}")
