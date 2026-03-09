import os, glob
import requests
from datetime import datetime

GRAPHDB_ENDPOINT = os.getenv("GRAPHDB_ENDPOINT", "http://graphdb:7200/repositories/ontobot")
QUERY_DIR = os.getenv("QUERY_DIR", "/app/queries")
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "/output")

def run_sparql(query: str) -> dict:
    r = requests.post(
        GRAPHDB_ENDPOINT,
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
            f"Endpoint: {GRAPHDB_ENDPOINT}\n"
            f"Response:\n{r.text}\n"
        )

    return r.json()
def to_md_table(sparql_json: dict):
    vars_ = sparql_json.get("head", {}).get("vars", [])
    rows = sparql_json.get("results", {}).get("bindings", [])
    if not vars_:
        return "_No columns returned._\n", 0

    md = "| " + " | ".join(vars_) + " |\n"
    md += "| " + " | ".join(["---"] * len(vars_)) + " |\n"
    for row in rows:
        md += "| " + " | ".join(row.get(v, {}).get("value", "") for v in vars_) + " |\n"
    return md, len(rows)

def title_from_filename(path: str) -> str:
    name = os.path.basename(path).replace(".rq", "")
    return name.replace("_", " ").replace("-", " ").title()

def write_page(md_path: str, title: str, row_count: int, table_md: str, query: str):
    content = []
    content.append(f"# {title}\n")
    content.append(f"Rows: **{row_count}**\n")
    content.append(table_md + "\n")
    content.append("## SPARQL Query\n")
    content.append("```sparql\n" + query.strip() + "\n```\n")
    content.append(f"_Generated: {datetime.utcnow().isoformat()}Z_\n")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(content))

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    query_files = sorted(glob.glob(os.path.join(QUERY_DIR, "*.rq")))
    if not query_files:
        raise SystemExit(f"No .rq files found in {QUERY_DIR}")

    index_lines = ["# Plant Wiki Index\n", f"_Generated: {datetime.utcnow().isoformat()}Z_\n"]

    for qf in query_files:
        with open(qf, "r", encoding="utf-8") as f:
            query = f.read()

        data = run_sparql(query)
        table_md, count = to_md_table(data)

        page_name = os.path.basename(qf).replace(".rq", "") + ".md"
        page_path = os.path.join(OUTPUT_DIR, page_name)
        title = title_from_filename(qf)

        write_page(page_path, title, count, table_md, query)
        index_lines.append(f"- [{title}]({page_name}) — rows: {count}")

    with open(os.path.join(OUTPUT_DIR, "index.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(index_lines) + "\n")

if __name__ == "__main__":
    main()