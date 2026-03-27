import os
import glob
import time
import requests
from datetime import datetime


class MarkdownGenerator:
    def __init__(self, graphdb_endpoint: str, query_dir: str, output_dir: str):
        self.graphdb_endpoint = graphdb_endpoint
        self.query_dir = query_dir
        self.output_dir = output_dir

    def run_sparql(self, query: str, tries: int = 2, timeout: int = 180) -> dict:
        last_err = None
        for i in range(tries):
            try:
                r = requests.post(
                    self.graphdb_endpoint,
                    data=query.encode("utf-8"),
                    headers={
                        "Accept": "application/sparql-results+json",
                        "Content-Type": "application/sparql-query; charset=utf-8",
                    },
                    timeout=timeout,
                )

                if not r.ok:
                    raise RuntimeError(
                        f"GraphDB SPARQL error {r.status_code}\n"
                        f"Endpoint: {self.graphdb_endpoint}\n"
                        f"Response:\n{r.text}\n"
                    )

                return r.json()
            except Exception as e:
                last_err = e
                print(f"[WARN] Query attempt {i + 1}/{tries} failed: {e}")
                time.sleep(2 * (i + 1))
        raise last_err

    def to_md_table(self, sparql_json: dict):
        vars_ = sparql_json.get("head", {}).get("vars", [])
        rows = sparql_json.get("results", {}).get("bindings", [])

        if not vars_:
            return "_No columns returned._\n", 0

        md = "| " + " | ".join(vars_) + " |\n"
        md += "| " + " | ".join(["---"] * len(vars_)) + " |\n"

        for row in rows:
            values = []
            for v in vars_:
                value = row.get(v, {}).get("value", "")
                value = str(value).replace("|", "\\|").replace("\n", " ")
                values.append(value)
            md += "| " + " | ".join(values) + " |\n"

        return md, len(rows)

    def title_from_filename(self, path: str) -> str:
        name = os.path.basename(path).replace(".rq", "")
        return name.replace("_", " ").replace("-", " ").title()

    def write_page(self, rel_path: str, title: str, row_count: int, table_md: str, query: str):
        full_path = os.path.join(self.output_dir, rel_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)

        content = []
        content.append(f"# {title}\n")
        content.append(f"Rows: **{row_count}**\n")
        content.append(table_md + "\n")
        content.append("## SPARQL Query\n")
        content.append("```sparql\n" + query.strip() + "\n```\n")
        content.append(f"_Generated: {datetime.utcnow().isoformat()}Z_\n")

        with open(full_path, "w", encoding="utf-8") as f:
            f.write("\n".join(content))

    def read_query(self, filename: str) -> str:
        path = os.path.join(self.query_dir, filename)
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def render_template(self, template_str: str, replacements: dict[str, str]) -> str:
        out = template_str
        for key, value in replacements.items():
            out = out.replace(f"{{{{{key}}}}}", value)
        return out

    def run_and_write(self, query: str, out_path: str, title: str):
        print(f"[RUN] {title}")
        data = self.run_sparql(query)
        table_md, count = self.to_md_table(data)
        self.write_page(out_path, title, count, table_md, query)
        return count, data

    def extract_column_values(self, sparql_json: dict, var_name: str) -> list[str]:
        rows = sparql_json.get("results", {}).get("bindings", [])
        values = []
        for row in rows:
            if var_name in row:
                values.append(row[var_name]["value"])
        return values

    def generate_all(self):
        os.makedirs(self.output_dir, exist_ok=True)

        index_lines = [
            "# Plant Wiki Index\n",
            f"_Generated: {datetime.utcnow().isoformat()}Z_\n",
            "## Overview\n",
        ]

        # -----------------------------
        # 1) Fixed overview pages
        # -----------------------------
        fixed_pages = [
            ("conveyors.rq", "overview/conveyors.md", "Conveyors"),
            ("component_types.rq", "overview/component_types.md", "Component Types"),
            ("stations.rq", "overview/stations.md", "Stations"),
            ("open_ends.rq", "validation/open_ends.md", "Open Ends"),
        ]

        discovery_results = {}

        for query_file, out_path, title in fixed_pages:
            query = self.read_query(query_file)
            count, data = self.run_and_write(query, out_path, title)
            index_lines.append(f"- [{title}]({out_path}) — rows: {count}")
            discovery_results[query_file] = data

        # -----------------------------
        # 2) Dynamic station pages
        # -----------------------------
        index_lines.append("\n## Stations\n")
        station_template = self.read_query("station_details.rq")
        stations = self.extract_column_values(discovery_results["stations.rq"], "station")

        for station in stations:
            query = self.render_template(station_template, {"STATION": station})
            out_path = f"stations/{station}.md"
            title = f"Station {station}"
            try:
                count, _ = self.run_and_write(query, out_path, title)
                index_lines.append(f"- [{title}]({out_path}) — rows: {count}")
            except Exception as e:
                print(f"[SKIP] {station}: {e}")

        # -----------------------------
        # 3) Dynamic component pages
        # -----------------------------
        index_lines.append("\n## Components\n")
        component_template = self.read_query("component_details.rq")
        component_types = self.extract_column_values(discovery_results["component_types.rq"], "type")

        for comp_type in component_types:
            safe_name = comp_type.replace("/", "_")
            query = self.render_template(component_template, {"TYPE": comp_type})
            out_path = f"components/{safe_name}.md"
            title = f"Component {comp_type}"
            try:
                count, _ = self.run_and_write(query, out_path, title)
                index_lines.append(f"- [{title}]({out_path}) — rows: {count}")
            except Exception as e:
                print(f"[SKIP] {comp_type}: {e}")

        # -----------------------------
        # 4) Write index
        # -----------------------------
        with open(os.path.join(self.output_dir, "index.md"), "w", encoding="utf-8") as f:
            f.write("\n".join(index_lines) + "\n")


if __name__ == "__main__":
    graphdb_endpoint = os.getenv(
        "GRAPHDB_ENDPOINT",
        "http://host.docker.internal:7200/repositories/ontobot"
    )
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

    generator.generate_all()
    print("Wiki generation complete.")