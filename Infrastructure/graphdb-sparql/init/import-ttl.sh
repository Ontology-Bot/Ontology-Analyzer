#!/bin/bash
set -e

: "${REPO_ID:=ontobot}"
: "${GRAPHDB_URL:=http://graphdb:7200}"

# --- Create repository if it doesn't exist ---
if curl -s "$GRAPHDB_URL/rest/repositories" | grep -q "\"id\":\"$REPO_ID\""; then
    echo "Repository '$REPO_ID' already exists — skipping creation."
else
    TMP_TTL="/tmp/${REPO_ID}-repo.ttl"
    sed "s/\${REPO_ID}/${REPO_ID}/g" /init/graphdb.ttl > "$TMP_TTL"

    echo "Creating repository '$REPO_ID'..."
    curl --fail-with-body \
         -X POST "$GRAPHDB_URL/rest/repositories" \
         -H 'Content-Type: multipart/form-data' \
         -F "config=@$TMP_TTL"
    echo ""
    echo "Repository '$REPO_ID' created."
fi

# --- Load each .ttl file into its own named graph ---
echo "Importing TTL files..."
for file in /data/*.ttl; do
    [ -f "$file" ] || continue

    filename=$(basename "$file" .ttl)
    # Sanitize filename for safe URI use
    graph_name=$(echo "$filename" | tr ' ' '-' | tr -cd '[:alnum:]-_' | tr '[:upper:]' '[:lower:]')
    if [ -z "$graph_name" ]; then
        graph_name="file-$(date +%s)"
    fi
    graph_uri="http://example.com/${graph_name}-graph"

    echo "  Loading '$filename.ttl' into graph '$graph_uri'..."
    curl --fail-with-body \
         -X POST \
         -H 'Content-Type: application/x-turtle' \
         --data-binary "@$file" \
         "$GRAPHDB_URL/repositories/$REPO_ID/rdf-graphs/service?graph=${graph_uri}"
    echo ""
    echo "  Done: $filename.ttl"
done

echo "All TTL files imported into repository '$REPO_ID'."
