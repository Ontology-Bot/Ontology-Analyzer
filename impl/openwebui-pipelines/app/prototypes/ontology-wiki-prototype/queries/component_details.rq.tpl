PREFIX aml: <https://w3id.org/hsu-aut/AutomationML#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT DISTINCT ?component ?label ?name
WHERE {
  ?component ?p ?o .
  FILTER(CONTAINS(STR(?component), "/{{TYPE}}/"))
  OPTIONAL { ?component rdfs:label ?label }
  OPTIONAL { ?component aml:hasName ?name }
}
LIMIT 200