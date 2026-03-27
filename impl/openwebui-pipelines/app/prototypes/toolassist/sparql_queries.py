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
select ?s ?type ?description ?attrLabel ?attrComment ?rootAttr ?attr ?attrValue ?attrUnit ?attrType ?lnk ?lnkType ?lnkLabel where {
    ?s rdfs:label "${node_label}" .
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
            }
            ?s ?lnkType ?lnk .
            ?lnk rdfs:label ?lnkLabel .
        }
    }
    
    
    FILTER(STRSTARTS(STR(?type), STR(lib:MaterialFlow_))) .
    FILTER(?type NOT IN (lib:MaterialFlow_InterfaceClass, lib:MaterialFlow_Thing))
}
"""

GET_NODE_CONTEXT_BY_GUID = """
select ?label ?type ?description ?attrLabel ?attrComment ?rootAttr ?attr ?attrValue ?attrUnit ?attrType ?lnk ?lnkType ?lnkLabel where {
    ?s rdfs:label ?label .
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
            }
            ?s ?lnkType ?lnk .
            ?lnk rdfs:label ?lnkLabel .
        }
    }
    VALUES ?s {
        inst:${node_label}
    }
    
    
    FILTER(STRSTARTS(STR(?type), STR(lib:MaterialFlow_))) .
    FILTER(?type NOT IN (lib:MaterialFlow_InterfaceClass, lib:MaterialFlow_Thing))
}
"""