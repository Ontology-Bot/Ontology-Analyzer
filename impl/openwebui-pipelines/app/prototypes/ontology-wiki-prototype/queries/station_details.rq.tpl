PREFIX aml: <https://w3id.org/hsu-aut/AutomationML#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT DISTINCT ?component ?label ?name
WHERE {
  ?component aml:hasPart* ?x .
  FILTER(CONTAINS(STR(?component), "/{{STATION}}/"))
  OPTIONAL { ?component rdfs:label ?label }
  OPTIONAL { ?component aml:hasName ?name }
}
LIMIT 200