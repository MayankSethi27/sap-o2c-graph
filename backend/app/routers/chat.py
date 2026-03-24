"""NL-to-SQL chat endpoint using Groq API with guardrails."""

import json
import os
import re
import aiosqlite
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from groq import Groq

from ..database import get_db, DB_PATH

router = APIRouter(prefix="/api/chat", tags=["chat"])

OFF_TOPIC_MSG = "This system is designed to answer questions related to the Order-to-Cash dataset only."

# Valid tables in our schema
VALID_TABLES = {"entities", "edges"}

# Keywords that signal an O2C-related question
O2C_KEYWORDS = [
    "order", "sales", "delivery", "billing", "invoice", "payment", "customer",
    "product", "plant", "partner", "journal", "document", "item", "material",
    "quantity", "amount", "net", "gross", "currency", "date", "status",
    "shipped", "delivered", "cancelled", "cancellation", "credit", "debit",
    "account", "receivable", "fiscal", "company", "clearing", "posting",
    "schedule", "line", "storage", "location", "description", "address",
    "distribution", "channel", "division", "organization",
    "o2c", "sap", "erp", "entity", "edge", "node", "graph", "connection",
    "relationship", "sold", "billed", "paid", "total", "count", "how many",
    "average", "sum", "max", "min", "top", "bottom", "highest", "lowest",
    "most", "least", "list", "show", "find", "get", "which", "what",
    "revenue", "overdue", "outstanding", "ar", "gl",
]

# Dangerous SQL keywords that should never appear
DANGEROUS_SQL = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|REPLACE|MERGE|EXEC|EXECUTE|GRANT|REVOKE|ATTACH|DETACH|PRAGMA|VACUUM)\b",
    re.IGNORECASE,
)

# Pattern to extract table names from SQL (after FROM/JOIN/INTO keywords)
TABLE_REF_PATTERN = re.compile(
    r"\b(?:FROM|JOIN|INTO|UPDATE|TABLE)\s+(\w+)", re.IGNORECASE
)


def _get_api_key() -> str:
    return os.environ.get("GROQ_API_KEY", "")


def _is_o2c_related(message: str) -> bool:
    """Check if the user message is related to O2C data."""
    msg_lower = message.lower()
    return any(kw in msg_lower for kw in O2C_KEYWORDS)


def _validate_sql_safety(sql: str) -> str | None:
    """Validate SQL is safe to execute. Returns error message or None if safe."""
    sql_stripped = sql.strip()
    sql_upper = sql_stripped.upper()

    # Must start with SELECT or WITH (CTEs like WITH ... AS (SELECT ...))
    if not (sql_upper.startswith("SELECT") or sql_upper.startswith("WITH")):
        return "Only SELECT queries are allowed. Modifications to the database are not permitted."

    # Check for dangerous statements anywhere in the query (including subqueries, CTEs)
    match = DANGEROUS_SQL.search(sql_stripped)
    if match:
        keyword = match.group(1).upper()
        return f"Query blocked: {keyword} statements are not allowed. Only SELECT queries are permitted."

    return None


def _split_sql_statements(sql: str) -> list[str]:
    """Split SQL into individual statements, filtering empty ones."""
    statements = [s.strip().rstrip(";") for s in sql.split(";")]
    return [s for s in statements if s]


def _validate_table_names(sql: str) -> str | None:
    """Check that all referenced table names exist in our schema. Returns error or None."""
    referenced = TABLE_REF_PATTERN.findall(sql)
    invalid = [t for t in referenced if t.lower() not in VALID_TABLES]
    if invalid:
        return f"Query references unknown table(s): {', '.join(set(invalid))}. Only 'entities' and 'edges' tables exist in this database."
    return None


DB_SCHEMA = """
SQLite database with two tables:

TABLE: entities
  - entity_type TEXT (e.g. 'sales_order', 'business_partner', 'product', 'delivery', 'billing_doc', 'payment', 'journal_item', 'plant', 'sales_order_item', 'delivery_item', 'billing_doc_item', 'billing_cancel', 'schedule_line', 'product_desc', 'product_plant', 'product_storage', 'bp_address', 'cust_company', 'cust_sales_area')
  - entity_id TEXT
  - label TEXT
  - data JSON (contains all fields from the original SAP record as a JSON object)
  PRIMARY KEY (entity_type, entity_id)

TABLE: edges
  - id INTEGER PRIMARY KEY
  - source_type TEXT
  - source_id TEXT
  - target_type TEXT
  - target_id TEXT
  - relationship TEXT (e.g. 'SOLD_TO', 'ITEM_OF', 'FOR_PRODUCT', 'FROM_PLANT', 'SCHEDULE_FOR', 'DELIVERS_ORDER', 'SHIPPED_FROM_PLANT', 'BILLED_TO', 'BILLS_PRODUCT', 'BILLS_DELIVERY', 'CANCELS', 'POSTED_FROM', 'AR_FOR_CUSTOMER', 'PAID_BY', 'PAYMENT_FOR_JOURNAL', 'CLEARS', 'ADDRESS_OF', 'COMPANY_ASSIGNMENT', 'SALES_AREA_OF', 'DESCRIBES', 'PRODUCT_AT_PLANT', 'AT_PLANT', 'STORED_PRODUCT', 'STORED_AT_PLANT')

The 'data' column in entities is a JSON string. Use json_extract(data, '$.fieldName') to query fields inside it.

Key fields by entity_type in the data JSON:
- sales_order: salesOrder, salesOrderType, soldToParty, totalNetAmount, transactionCurrency, creationDate, overallDeliveryStatus, requestedDeliveryDate
- sales_order_item: salesOrder, salesOrderItem, material, requestedQuantity, netAmount, productionPlant
- business_partner: businessPartner, businessPartnerFullName, businessPartnerName, customer
- product: product, productType, creationDate
- product_desc: product, language, productDescription
- delivery: deliveryDocument, creationDate, overallGoodsMovementStatus, overallPickingStatus
- delivery_item: deliveryDocument, deliveryDocumentItem, referenceSdDocument, actualDeliveryQuantity, plant
- billing_doc: billingDocument, billingDocumentType, soldToParty, totalNetAmount, transactionCurrency, billingDocumentDate, billingDocumentIsCancelled
- billing_doc_item: billingDocument, billingDocumentItem, material, billingQuantity, netAmount, referenceSdDocument
- billing_cancel: billingDocument, cancelledBillingDocument, creationDate
- journal_item: companyCode, fiscalYear, accountingDocument, glAccount, referenceDocument, customer, amountInTransactionCurrency, postingDate
- payment: companyCode, fiscalYear, accountingDocument, accountingDocumentItem, customer, amountInTransactionCurrency, clearingAccountingDocument, postingDate, clearingDate
- plant: plant, plantName
- schedule_line: salesOrder, salesOrderItem, scheduleLine, confirmedDeliveryDate, confdOrderQtyByMatlAvailCheck

Edge relationships connect entities:
- sales_order --SOLD_TO--> business_partner (via soldToParty=businessPartner)
- sales_order_item --ITEM_OF--> sales_order
- sales_order_item --FOR_PRODUCT--> product (via material=product)
- delivery_item --DELIVERS_ORDER--> sales_order (via referenceSdDocument=salesOrder)
- billing_doc --BILLED_TO--> business_partner (via soldToParty)
- billing_doc_item --BILLS_DELIVERY--> delivery
- journal_item --POSTED_FROM--> billing_doc (via referenceDocument=billingDocument)
- payment --PAID_BY--> business_partner (via customer=businessPartner)
- payment --PAYMENT_FOR_JOURNAL--> journal_item (via accountingDocument)
"""

SYSTEM_PROMPT = f"""You are a SQL assistant for an SAP Order-to-Cash (O2C) analytics system.
You ONLY answer questions related to the O2C dataset. If the user asks anything unrelated to SAP, Order-to-Cash, sales orders, deliveries, billing, payments, customers, products, plants, or the data in this system, respond with exactly: "{OFF_TOPIC_MSG}"

{DB_SCHEMA}

Rules:
1. Generate ONLY a single valid SQLite SELECT query. No INSERT/UPDATE/DELETE/DROP.
2. Always use json_extract(data, '$.fieldName') to access fields inside the data JSON column.
3. Return the SQL inside a ```sql code block.
4. If the question cannot be answered with the available schema, explain why.
5. Keep queries efficient — use LIMIT when returning many rows.
6. For aggregations across entity types, join the entities table with itself or with edges.
7. When joining through edges, match on (source_type, source_id) or (target_type, target_id).
8. ONLY reference tables 'entities' and 'edges'. No other tables exist.
"""


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    answer: str
    sql: str | None = None
    results: list[dict] | None = None
    error: str | None = None


def extract_sql(text: str) -> str | None:
    """Extract SQL from LLM response. Handles multiple ```sql``` blocks by joining them."""
    # Find all ```sql ... ``` blocks
    blocks = re.findall(r"```sql\s*(.*?)\s*```", text, re.DOTALL)
    if blocks:
        return "\n;\n".join(b.strip() for b in blocks if b.strip())
    # Fallback: single block starting with SELECT or WITH
    match = re.search(r"```\s*((?:SELECT|WITH).*?)\s*```", text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None


@router.post("", response_model=ChatResponse)
async def chat(req: ChatRequest, db: aiosqlite.Connection = Depends(get_db)):
    api_key = _get_api_key()
    if not api_key:
        return ChatResponse(
            answer="Groq API key not configured. Add your key to backend/.env file.",
            error="missing_api_key",
        )

    # Guardrail 1: keyword-based off-topic check before calling LLM
    if not _is_o2c_related(req.message):
        return ChatResponse(answer=OFF_TOPIC_MSG, error="off_topic")

    # Call Groq API
    client = Groq(api_key=api_key)

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": req.message},
            ],
            temperature=0,
            max_tokens=2048,
        )
        llm_text = response.choices[0].message.content
    except Exception as e:
        return ChatResponse(answer=f"Groq API error: {str(e)}", error="groq_error")

    # If LLM itself returned the off-topic message, pass it through
    if OFF_TOPIC_MSG in (llm_text or ""):
        return ChatResponse(answer=OFF_TOPIC_MSG, error="off_topic")

    # Extract SQL
    sql = extract_sql(llm_text)
    if not sql:
        return ChatResponse(answer=llm_text)

    # Split into individual statements (LLM may generate multiple for trace queries)
    statements = _split_sql_statements(sql)
    if not statements:
        return ChatResponse(answer=llm_text)

    # Validate each statement
    for stmt in statements:
        # Guardrail 2: validate SELECT-only, no dangerous statements
        safety_error = _validate_sql_safety(stmt)
        if safety_error:
            return ChatResponse(answer=safety_error, sql=sql, error="unsafe_query")

        # Guardrail 3: validate table names exist in our schema
        table_error = _validate_table_names(stmt)
        if table_error:
            return ChatResponse(answer=table_error, sql=sql, error="invalid_table")

    # Execute all statements, merge results
    all_results = []
    all_columns = []
    try:
        for stmt in statements:
            cursor = await db.execute(stmt)
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            rows = await cursor.fetchall()
            stmt_results = [dict(zip(columns, row)) for row in rows[:200]]
            all_results.extend(stmt_results)
            if columns and not all_columns:
                all_columns = columns
            elif columns:
                # Merge unique column names for multi-statement results
                for c in columns:
                    if c not in all_columns:
                        all_columns.append(c)
    except Exception as e:
        return ChatResponse(
            answer=f"SQL execution error: {str(e)}",
            sql=sql,
            error="sql_error",
        )

    results = all_results[:200]
    columns = all_columns

    # Generate a natural language summary
    summary_prompt = f"""The user asked: "{req.message}"

The SQL query returned {len(results)} rows with columns: {columns}

First few results: {json.dumps(results[:10], default=str)}

Provide a concise, helpful natural language answer based on these results. Include key numbers and facts. Do not include SQL in your response."""

    try:
        summary_response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "user", "content": summary_prompt},
            ],
            temperature=0,
            max_tokens=1024,
        )
        answer = summary_response.choices[0].message.content
    except Exception:
        answer = f"Query returned {len(results)} rows."

    return ChatResponse(answer=answer, sql=sql, results=results)
