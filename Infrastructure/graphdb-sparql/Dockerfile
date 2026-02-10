FROM ontotext/graphdb:11.2.0

USER root
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy license into the image (build fails if missing)
COPY graphdb.license  license/graphdb.license

# Bake .ttl ontology data into the image so it doesn't need to be mounted
COPY _secret/*.ttl data/

COPY init/graphdb.ttl .
COPY init/entrypoint.sh .
RUN chmod +x entrypoint.sh

ENTRYPOINT ["/app/entrypoint.sh"]