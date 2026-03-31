# Only aml:InternalElement have obot:guid
# Successor and Predecessor connectors have guid, but they are ignored as a path endpoints. 
# They are not listed through get ctx block and should never referenced. They cannot be found through GET_GUID and similar guid queries
# Subject to change - fix connections then

PREFIX = """
PREFIX : <http://www.semanticweb.org/AutomationML/ontologies/structure#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX lib: <http://www.semanticweb.org/AutomationML/ontologies/structure/libraries#>
PREFIX inst: <http://www.semanticweb.org/AutomationML/ontologies/structure/instances#>
PREFIX obot: <http://example.com/ontobot_bridge#>
PREFIX aml: <https://w3id.org/hsu-aut/AutomationML#>
"""

GET_DEFINITION = """
SELECT ?class ?description ?child ?parent {
    ?class rdfs:subClassOf ?p .
    ?class rdfs:comment ?description .
    
    OPTIONAL {
        { ?child rdfs:subClassOf ?class }
        UNION
        { 
            ?class rdfs:subClassOf ?parent .
            FILTER NOT EXISTS {
                ?class rdfs:subClassOf ?mid .
                ?mid rdfs:subClassOf ?parent .
            }
        }
    }
    
    VALUES ?p {
        lib:MaterialFlow_Thing
        lib:MaterialFlow_InterfaceClass
    }
}
"""


GET_LIST = """
select ?s ?label ?description where {
    ?s rdfs:label ?label .
    ?s rdf:type lib:MaterialFlow_${term} .
    ?s rdfs:comment ?description .
}
"""


GET_NODE_CONTEXT = """
select ?label ?guid ?type ?description ?attrLabel ?attrComment ?rootAttr ?attr ?attrValue ?attrUnit ?attrType ?lnkGuid ?lnkType ?lnkLabel where {
    ?s rdfs:label ?label .
    ?s obot:guid ?guid .
    ?s rdf:type ?type .
    ?s rdfs:comment ?description .
    OPTIONAL {
        { 
            ?s :hasAttribute ?rootAttr .
            ?rootAttr :hasSubAttribute* ?attr .
            ?attr rdfs:label ?attrLabel .
            ?attr rdfs:comment ?attrComment .

            OPTIONAL { 
                ?attr :hasValue ?attrValue .
                ?attr :hasUnit ?attrUnit .
                ?attr :hasDataType ?attrType
            }
        }
        UNION
        {
            VALUES ?lnkType {
                :contains
                :containedIn
                obot:connectedTo
                obot:connectedFrom
            }
            ?s ?lnkType ?lnk .
            ?lnk rdfs:label ?lnkLabel .
            ?lnk obot:guid ?lnkGuid
        }
    }
    VALUES ?guid { "${guid}" }

    FILTER(STRSTARTS(STR(?type), STR(lib:MaterialFlow_))) .
    FILTER(?type NOT IN (lib:MaterialFlow_InterfaceClass, lib:MaterialFlow_Thing))
}
"""

GET_NODE_LOCATION = """
select ?guid ?node ?label ?attr ?attrValue ?attrUnit ?attrType where {
    ?s obot:guid ?guid .
    ?s rdfs:label ?label .
    ?s :containedIn* ?node .
    ?s rdfs:comment ?_ . # ensure its only old ttl
    
    OPTIONAL {
        ?node :hasAttribute ?rootAttr.
        ?rootAttr rdfs:label "origin" .
        ?rootAttr :hasSubAttribute+ ?attr .
        
        ?attr :hasValue ?attrValue .
        ?attr :hasUnit ?attrUnit .
        ?attr :hasDataType ?attrType
    }
}
"""

GET_CONNECTIONS = """
SELECT ?guid ?label ?type ?lnkType ?guidLnk {
    
    ?s obot:guid ?guid .
    ?s rdf:type ?type .
    ?s rdfs:label ?label .
    ?s rdfs:comment ?description .
    
    OPTIONAL {
        ?s ?lnkType ?lnk .
        ?lnk obot:guid ?guidLnk .

        VALUES ?lnkType {
            :contains
            :containedIn
            obot:connectedTo
            obot:connectedFrom
        }
    }
    FILTER(STRSTARTS(STR(?type), STR(lib:MaterialFlow_))) .
    FILTER(?type NOT IN (lib:MaterialFlow_InterfaceClass, lib:MaterialFlow_Thing))
}
"""

GET_GUID = """
SELECT ?guid {
    ?s obot:guid ?guid .
    ?s aml:hasName "${label}"
}
"""