#!/bin/bash
set -e

: "${REPO_ID:=ontobot}"

# --- Ensure the license is in the conf directory ---
mkdir -p /opt/graphdb/home/conf
cp /app/license/graphdb.license /opt/graphdb/home/conf/graphdb.license
echo "License copied to /opt/graphdb/home/conf/graphdb.license"

# --- Start GraphDB in the background (with the same args as the default CMD) ---
/opt/graphdb/dist/bin/graphdb -Dgraphdb.home=/opt/graphdb/home -Dgraphdb.distribution=docker &
GDB_PID=$!

GRAPHDB_URL="http://localhost:7200"

echo "Waiting for GraphDB to become ready..."
until curl -sf "$GRAPHDB_URL/rest/repositories" > /dev/null 2>&1; do
    printf '.'
    sleep 2
done
echo ""
echo "GraphDB is ready."

# --- Create a single repository ---
if curl -s "$GRAPHDB_URL/rest/repositories" | grep -q "\"id\":\"$REPO_ID\""; then
    echo "Repository '$REPO_ID' already exists — skipping creation."
else
    TMP_TTL="/tmp/${REPO_ID}-repo.ttl"
    sed "s/\${REPO_ID}/${REPO_ID}/g" /app/graphdb.ttl > "$TMP_TTL"

    echo "Creating repository '$REPO_ID'..."
    curl --fail-with-body \
         -X POST "$GRAPHDB_URL/rest/repositories" \
         -H 'Content-Type: multipart/form-data' \
         -F "config=@$TMP_TTL"
    echo "Repository '$REPO_ID' created."
fi

# --- Load each .ttl file into its own named graph ---
for file in /data/*.ttl; do
    [ -f "$file" ] || continue

    filename=$(basename "$file" .ttl)                  # e.g. "new file"
    # Sanitize filename for safe URI use: replace spaces with '-', remove non-alphanumerics except '-' and '_', and lowercase
    graph_name=$(echo "$filename" | tr ' ' '-' | tr -cd '[:alnum:]-_' | tr '[:upper:]' '[:lower:]')
    # Fallback if sanitization removed everything
    if [ -z "$graph_name" ]; then
        graph_name="file-$(date +%s)"
    fi
    graph_uri="http://example.com/${graph_name}-graph"            # e.g. "http://example.com/new-file-graph"

    echo "  Loading '$filename.ttl' into graph '$graph_uri' in repo '$REPO_ID'..."
    curl --fail-with-body \
         -X POST \
         -H 'Content-Type: application/x-turtle' \
         --data-binary "@$file" \
         "$GRAPHDB_URL/repositories/$REPO_ID/rdf-graphs/service?graph=${graph_uri}"
    echo "  Done."
done

echo "All data loaded into repository '$REPO_ID'."

# --- Keep GraphDB in the foreground ---
wait $GDB_PID
