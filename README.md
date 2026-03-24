# SAP O2C Graph Explorer

A full-stack graph-based query and visualization system for SAP Order-to-Cash (O2C) data. Loads 19 SAP entity types from JSONL files into a unified graph database, renders an interactive force-directed graph, and provides an AI chat interface for natural language querying over the dataset.

![Tech Stack](https://img.shields.io/badge/FastAPI-009688?style=flat&logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React_18-61DAFB?style=flat&logo=react&logoColor=black)
![SQLite](https://img.shields.io/badge/SQLite-003B57?style=flat&logo=sqlite&logoColor=white)
![Groq](https://img.shields.io/badge/Groq_LLM-FF6600?style=flat)

## Table of Contents

- [Project Overview](#project-overview)
- [Architecture Decisions](#architecture-decisions)
- [Graph Modelling Approach](#graph-modelling-approach)
- [LLM Prompting Strategy](#llm-prompting-strategy)
- [Guardrails Implementation](#guardrails-implementation)
- [Tech Stack](#tech-stack)
- [How to Run Locally](#how-to-run-locally)
- [API Reference](#api-reference)

---

## Project Overview

The SAP Order-to-Cash process spans multiple business objects — customers, sales orders, deliveries, billing documents, journal entries, and payments. In traditional SAP systems, tracing a single transaction across these objects requires navigating dozens of tables and transaction codes.

This project transforms flat JSONL exports from SAP S/4HANA APIs into an interconnected graph, making it possible to:

- **Visualize** the entire O2C network as an interactive force-directed graph (1,400+ visible nodes, 2,500+ edges)
- **Explore** individual entities by clicking nodes to see all their properties
- **Query** the dataset in natural language — the AI assistant translates questions into SQL, executes them, and returns human-readable answers
- **Trace** document flows end-to-end (e.g., "trace billing document 90504204" follows the chain from billing → delivery → sales order → customer)

The system auto-loads all 19 JSONL datasets (21,393 entities, 42,306 edges) into SQLite on backend startup. No manual data import required.

---

## Architecture Decisions

### Why SQLite over Neo4j?

A graph database like Neo4j would be the conventional choice for graph data. We chose SQLite with a generic entity-edge schema for several reasons:

| Factor | SQLite | Neo4j |
|--------|--------|-------|
| **Deployment** | Zero config, single file (`o2c.db`) | Requires a separate server process |
| **LLM compatibility** | LLMs are highly proficient at generating SQL; NL-to-Cypher is far less reliable | Would require NL-to-Cypher, which has significantly lower accuracy |
| **Dependencies** | `aiosqlite` (pure Python) | `neo4j` driver + Neo4j server |
| **Portability** | DB file ships with the app, rebuilds from JSONL on startup | Requires persistent storage and database migration |
| **Dataset size** | ~21K entities and ~42K edges — well within SQLite's comfort zone | Neo4j's advantages (index-free adjacency, graph traversals) only materialize at millions of nodes |

The two-table schema (`entities` + `edges`) gives us graph semantics within a relational database. BFS traversal is implemented in application code, and `json_extract()` provides flexible querying over heterogeneous entity data without requiring 19 separate tables.

### Why Groq (Llama 3.3 70B)?

The AI chat feature uses Groq's inference API with the Llama 3.3 70B Versatile model:

- **Speed**: Groq's LPU hardware delivers responses in under 1 second, critical for interactive chat
- **SQL accuracy**: Llama 3.3 70B generates correct SQLite queries with `json_extract()` reliably, including complex multi-join trace queries
- **Cost**: Groq's free tier is generous enough for development and demonstration
- **Open model**: Llama 3.3 is open-weight, avoiding vendor lock-in to any single provider

The system architecture is LLM-agnostic — swapping to a different provider requires changing only the API client and model name in `chat.py`.

---

## Graph Modelling Approach

### Generic Entity-Edge Schema

Rather than creating 19 separate tables (one per SAP entity type), we use a **type-discriminated generic schema**:

```sql
-- Every SAP business object becomes a row here
entities (entity_type TEXT, entity_id TEXT, label TEXT, data JSON)
-- PRIMARY KEY (entity_type, entity_id)

-- Every relationship between objects becomes a row here
edges (source_type, source_id, target_type, target_id, relationship)
```

All entity-specific fields (salesOrder, billingDocument, totalNetAmount, etc.) live inside the `data` JSON column, queryable via `json_extract(data, '$.fieldName')`.

### 19 Node Types

The dataset covers the full O2C lifecycle:

**Master Data (9 types):** Business partners, addresses, customer assignments (company/sales area), products, product descriptions, product plants, product storage locations, plants.

**Transactional (8 types):** Sales orders + items + schedule lines, outbound deliveries + items, billing documents + items + cancellations.

**Accounting (2 types):** Journal entry items (accounts receivable), payments.

### Node ID Format

Each node is identified by `{entity_type}:{composite_pk}`, where composite primary keys are joined with `:`. For example:
- `sales_order:740506` (single-field PK)
- `sales_order_item:740506:10` (composite PK: salesOrder + salesOrderItem)
- `journal_item:1710:2025:5100000774:0000113100` (4-field composite PK)

### 26 Edge Rules

Edges are built during data ingestion based on foreign key relationships defined as 5-tuples:

```python
(source_type, source_fk_fields, target_type, relationship, target_match_field)
```

**Key edge categories:**

| Category | Relationships | Example |
|----------|--------------|---------|
| Customer-facing | `SOLD_TO`, `BILLED_TO`, `PAID_BY` | sales_order → business_partner |
| Document hierarchy | `ITEM_OF` | sales_order_item → sales_order |
| Document flow | `DELIVERS_ORDER`, `BILLS_DELIVERY`, `POSTED_FROM` | delivery_item → sales_order → billing_doc |
| Product references | `FOR_PRODUCT`, `BILLS_PRODUCT` | sales_order_item → product |
| Location | `FROM_PLANT`, `SHIPPED_FROM_PLANT`, `AT_PLANT` | delivery_item → plant |
| Accounting | `PAYMENT_FOR_JOURNAL`, `CLEARS`, `AR_FOR_CUSTOMER` | payment → journal_item |

### Partial Composite Key Matching

A key challenge was matching single foreign keys to composite primary keys. For example, a payment's `accountingDocument` field needs to match a journal item whose PK is `companyCode:fiscalYear:accountingDocument:glAccount`.

The ingestion engine builds **partial indexes** for these cases — mapping each component of a composite PK back to the full entity ID, enabling single FK → composite PK edge resolution without full cross-products.

---

## LLM Prompting Strategy

The NL-to-SQL pipeline uses a **two-call pattern**:

### Call 1: Question → SQL Generation

The system prompt provides:
1. **Complete schema definition** — both tables with column types and all valid `entity_type` / `relationship` values
2. **Field catalog** — key `json_extract` fields for each of the 19 entity types, so the LLM knows which fields exist in the JSON
3. **Edge relationship map** — which entity types connect to which, and through which fields
4. **Strict rules** — SELECT only, use `json_extract()` for data fields, use LIMIT, reference only `entities` and `edges` tables

```
System: You are a SQL assistant for an SAP O2C analytics system.
        [full schema + field catalog + edge map + rules]

User:   "What are the top 5 customers by total billing amount?"
```

The LLM returns SQL in a fenced code block, which is extracted via regex.

### Call 2: SQL Results → Natural Language Summary

After executing the SQL, the raw results are sent back to the LLM with context:

```
The user asked: "What are the top 5 customers by total billing amount?"
The SQL query returned 5 rows with columns: [customer_name, total_amount]
First few results: [{...}]
Provide a concise, helpful natural language answer.
```

This produces a human-readable answer like: "The top 5 customers by billing amount are: Nelson Inc. ($45,230), Smith Corp. ($38,100)..."

### Multi-Statement Support

For complex trace queries, the LLM may generate multiple SQL blocks or CTEs (`WITH ... AS`). The system:
- Extracts all `\`\`\`sql` blocks from the response
- Splits semicolon-separated statements
- Validates and executes each independently
- Merges results into a single response

---

## Guardrails Implementation

Three layers of protection prevent misuse and ensure query safety:

### Layer 1: Off-Topic Detection (Pre-LLM)

Before any LLM call, the user's message is checked against an O2C keyword list (~60 terms covering SAP business objects, operations, and query patterns). Messages with no relevant keywords are rejected immediately — saving an API call and preventing the LLM from being used as a general-purpose assistant.

The system prompt also instructs the LLM to refuse off-topic questions as a second line of defense, catching edge cases where keywords match but intent is unrelated.

```python
O2C_KEYWORDS = ["order", "sales", "delivery", "billing", "payment", "customer", ...]

if not _is_o2c_related(req.message):
    return "This system is designed to answer questions related to the Order-to-Cash dataset only."
```

### Layer 2: SQL Safety Validation (Post-LLM)

Every generated SQL statement is validated before execution:

1. **Start token check**: Must begin with `SELECT` or `WITH` (for CTEs). Blocks any statement that starts with a write operation.
2. **Dangerous keyword scan**: Regex scans the entire query (including subqueries) for `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `CREATE`, `TRUNCATE`, `REPLACE`, `MERGE`, `EXEC`, `GRANT`, `REVOKE`, `ATTACH`, `DETACH`, `PRAGMA`, and `VACUUM`.

```python
DANGEROUS_SQL = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|...)\b", re.IGNORECASE
)
```

### Layer 3: Table Name Validation (Post-LLM)

All table references (after `FROM`, `JOIN`, `INTO`, `UPDATE`, `TABLE` keywords) are extracted and checked against the whitelist `{entities, edges}`. This prevents:
- SQL injection attempts referencing `sqlite_master` or other system tables
- Hallucinated table names that would cause confusing errors

Each guardrail returns a specific, friendly error message to the user rather than a generic failure.

---

## Tech Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Backend framework | **FastAPI** | Async Python API with automatic OpenAPI docs |
| Database | **SQLite** via aiosqlite | Zero-config embedded graph storage |
| LLM inference | **Groq API** (Llama 3.3 70B) | NL-to-SQL generation and result summarization |
| Frontend framework | **React 18** | Component-based UI |
| Build tool | **Vite 6** | Fast dev server with HMR, production builds |
| Graph visualization | **react-force-graph-2d** | Canvas-based force-directed graph rendering |
| HTTP client | **Axios** | API communication from frontend |
| Data format | **Pydantic** | Request/response validation and serialization |
| Environment | **python-dotenv** | API key management from `.env` files |

---

## How to Run Locally

### Prerequisites

- Python 3.11+
- Node.js 18+
- A Groq API key (free at [console.groq.com](https://console.groq.com))

### 1. Clone and set up the backend

```bash
cd backend
python -m venv venv

# Activate virtual environment
# Linux/Mac:
source venv/bin/activate
# Windows PowerShell:
.\venv\Scripts\Activate.ps1

pip install -r requirements.txt
```

### 2. Configure the API key

Create `backend/.env`:
```
GROQ_API_KEY=your_groq_api_key_here
```

### 3. Start the backend

```bash
cd backend
uvicorn app.main:app --reload --port 8001
```

On first startup, the backend automatically:
- Creates the SQLite database (`backend/o2c.db`)
- Loads all 19 JSONL datasets from `sap-o2c-data/` (21,393 entities)
- Builds 42,306 edges based on the 26 relationship rules

Subsequent starts skip data loading if the database already exists.

### 4. Set up and start the frontend

```bash
cd frontend
npm install
npm run dev
```

### 5. Open the app

Navigate to **http://localhost:5173**. The full graph loads automatically.

- **Click** any node to see its properties in a floating card
- **Hover** over nodes to see labels
- **Use the chat panel** (right side) to ask questions in natural language
- **Click Minimize** in the header to zoom back out to the full graph

---

## API Reference

All endpoints are under `/api`:

| Method | Path | Parameters | Description |
|--------|------|-----------|-------------|
| GET | `/api/graph/full` | `exclude_types?` | Full graph (excludes high-volume types by default) |
| GET | `/api/graph/traverse` | `entity_type`, `entity_id`, `depth` (1-5) | BFS subgraph from a starting node |
| GET | `/api/graph/node` | `entity_type`, `entity_id` | Single node details |
| GET | `/api/graph/entity-types` | — | List all entity types |
| GET | `/api/graph/entities` | `entity_type`, `limit?`, `search?` | List entities of a type |
| GET | `/api/graph/stats` | — | Entity and edge counts |
| POST | `/api/chat` | `{"message": "..."}` | Natural language query |
| GET | `/api/health` | — | Health check |
