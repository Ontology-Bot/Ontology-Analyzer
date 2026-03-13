# Ontology QA Prototype – AutomationML Plant Model

## Overview

This prototype demonstrates how an **AutomationML plant model** can be queried using **natural language**.  
Instead of manually exploring AutomationML files or writing SPARQL queries, users can ask questions and receive answers grounded in the plant data.

The system combines:

- AutomationML (plant model)
- RDF / ontology representation
- GraphDB (SPARQL endpoint)
- SPARQL-based knowledge extraction
- Automatically generated wiki documentation
- OpenWebUI + LLM for natural language question answering

The result is a **Retrieval-Augmented Question Answering (RAG) system over a plant ontology**.

---

# Architecture

```
AutomationML Plant Model (.aml)
            ↓
AML → RDF Conversion
            ↓
GraphDB (Ontology + Plant Data)
            ↓
SPARQL Queries
            ↓
Automatic Wiki Generation
            ↓
Markdown Knowledge Base
            ↓
OpenWebUI + LLM (RAG)
            ↓
Natural Language Question Answering
```

---

# How the System Works

## 1. Plant Model Ingestion

The AutomationML plant model is converted into **RDF triples**.

This creates a **graph representation of the plant**, including:

- stations
- components
- interfaces
- attributes
- connections between elements

The RDF data is stored in **GraphDB**, where it can be queried using SPARQL.

---

## 2. Structured Knowledge Extraction

Predefined **SPARQL queries** extract relevant knowledge from the ontology, such as:

- list of plant stations
- components installed in specific stations
- conveyor types
- attributes like availability
- connections between components

---

## 3. Automatic Wiki Generation

The SPARQL query results are automatically converted into **Markdown documentation pages**.

Examples of generated pages:

```
stations.md
components_ST101.md
attributes_availability.md
conveyor_types.md
```

These pages form a **machine-readable knowledge base** derived from the ontology.

---

## 4. Retrieval-Augmented Question Answering

The generated wiki pages are uploaded into **OpenWebUI as a Knowledge Collection**.

When a user asks a question:

1. OpenWebUI retrieves relevant wiki pages.
2. The LLM reads the retrieved documents.
3. The answer is generated using only the retrieved content.

This ensures answers remain **grounded in the plant data** and reduces hallucination.

---

# Example Query

### User Question

```
Which components are installed in station ST101?
```

### System Process

```
Question
   ↓
Retrieve components_ST101.md
   ↓
LLM reads table data
   ↓
Answer generated from document
```

### Example Output

```
TL002
TL003
TL005
TL006
TL007
TL008
TR001
TR004

Sources: components_ST101.md
```

---

# Example Questions

The prototype can answer questions such as:

- What stations exist in the plant?
- Which components are installed in station ST101?
- What conveyor types exist?
- Which elements contain the attribute "availability"?
- What connections exist between conveyors?

---

# Running the Prototype

Start the infrastructure:

```
docker compose up -d
```

Generate the wiki documentation from SPARQL queries:

```
docker compose run --rm wiki-generator
```

This will generate Markdown files in:

```
Infrastructure/wiki-data/
```

Upload these files into **OpenWebUI Knowledge Collection** to enable question answering.

---

# What This Prototype Demonstrates

This prototype demonstrates that:

- AutomationML models can be transformed into **queryable knowledge graphs**
- Ontology data can be **automatically documented**
- LLMs can provide **natural language access to industrial plant data**
- Retrieval-Augmented Generation keeps answers **grounded and explainable**

---

# Current Limitations

The current system answers questions **only based on the generated wiki pages**.

More advanced systems could allow the LLM to **generate SPARQL queries dynamically**, enabling flexible querying directly over the ontology.

---

# Future Work

Possible extensions include:

- dynamic SPARQL generation by the LLM
- automatic station-specific knowledge pages
- plant topology analysis
- anomaly detection in plant structures
- graph traversal queries for material flow paths

---

# Summary

This prototype enables **natural-language interaction with a structured AutomationML plant model** by combining:

```
AutomationML → RDF → GraphDB → SPARQL → Wiki → OpenWebUI + LLM (RAG)
```

It demonstrates how industrial knowledge graphs can be made **accessible, explainable, and searchable using modern AI techniques**.