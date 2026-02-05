#!/bin/sh
set -e # exit on fail

echo "Waiting for GraphDB to start..."
# 2. Wait for the REST API to become responsive (Status 200)
until curl --output /dev/null --silent --head --fail "$GRAPHDB_URL/protocol"; do
    printf '.'
    sleep 2
done

if curl -s "$GRAPHDB_URL/rest/repositories" | grep -q "\"id\":\"$REPO_ID\""; then
	echo "Repository '$REPO_ID' already exists"
else
	TMP_TTL="$HOME/repo.ttl"
	sed "s/\${REPO_ID}/${REPO_ID}/g" ./graphdb.ttl > $TMP_TTL
	# 
	echo "Creating '$REPO_ID'..."
	curl --fail-with-body \
		 -X POST "$GRAPHDB_URL/rest/repositories" \
		 -H 'Content-Type: multipart/form-data' \
		 -F "config=@$TMP_TTL"
	echo "Repository '$REPO_ID' created"
	
	# 4. Load all .ttl files there
	echo "Loading ontology data..."
	for file in /data/*.ttl; do
		if [ -f "$file" ]; then
			filename=$(basename "$file")
			echo "Loading $filename..."
			curl --fail-with-body \
			    -X POST \
				-H 'Content-Type: application/x-turtle' \
				--data-binary "@$file" \
				"$GRAPHDB_URL/repositories/$REPO_ID/statements"
			echo "$filename loaded!"
		fi
	done

	echo "Repository 'my-repo' populated successfully."
fi	 
