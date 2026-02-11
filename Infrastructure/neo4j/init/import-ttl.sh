#!/bin/bash
set -e

echo "Waiting for n10s plugin to be available..."
for i in {1..30}; do
  if cypher-shell -a "$NEO4J_URI" "SHOW PROCEDURES YIELD name WHERE name = 'n10s.rdf.import.fetch' RETURN count(*)" 2>/dev/null | grep -q "[1-9]"; then
    echo "n10s plugin ready."
    break
  fi
  echo "  Waiting... ($i/30)"
  sleep 2
done

echo "Creating n10s constraint..."
cypher-shell -a "$NEO4J_URI" \
  "CREATE CONSTRAINT n10s_unique_uri IF NOT EXISTS FOR (r:Resource) REQUIRE r.uri IS UNIQUE"

echo "Initializing n10s graph config..."
cypher-shell -a "$NEO4J_URI" \
  "CALL n10s.graphconfig.init({handleVocabUris: 'SHORTEN', keepLangTag: true})"

echo "Importing TTL files..."
for file in /import/*.ttl; do
  [ -f "$file" ] || continue
  filename=$(basename "$file")
  echo "  Importing $filename..."
  cypher-shell -a "$NEO4J_URI" \
    "CALL n10s.rdf.import.fetch('file:///import/$filename', 'Turtle')"
  echo "  Done: $filename"
done

echo "All TTL files imported."
