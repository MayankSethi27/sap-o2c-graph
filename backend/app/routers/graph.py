"""Routes for graph querying and traversal."""

import json
from fastapi import APIRouter, Depends, Query, HTTPException
import aiosqlite

from ..database import get_db
from ..models.schemas import GraphOut, NodeOut
from ..services.graph_query import traverse, get_node, get_full_graph

router = APIRouter(prefix="/api/graph", tags=["graph"])

# Large volume entity types excluded from full graph by default
DEFAULT_EXCLUDE = [
    "product_storage", "product_plant",
    "cust_company", "cust_sales_area",
    "schedule_line", "bp_address",
]


@router.get("/full", response_model=GraphOut)
async def full_graph(
    exclude_types: str = Query(
        ",".join(DEFAULT_EXCLUDE),
        description="Comma-separated entity types to exclude (high-volume types excluded by default)",
    ),
    db: aiosqlite.Connection = Depends(get_db),
):
    exclude = [t.strip() for t in exclude_types.split(",") if t.strip()] if exclude_types else []
    return await get_full_graph(db, exclude)


@router.get("/traverse", response_model=GraphOut)
async def graph_traverse(
    entity_type: str = Query(..., description="Entity type, e.g. 'sales_order'"),
    entity_id: str = Query(..., description="Entity ID"),
    depth: int = Query(1, ge=1, le=5, description="Traversal depth (1-5)"),
    db: aiosqlite.Connection = Depends(get_db),
):
    return await traverse(db, entity_type, entity_id, depth)


@router.get("/node", response_model=NodeOut)
async def get_single_node(
    entity_type: str = Query(...),
    entity_id: str = Query(...),
    db: aiosqlite.Connection = Depends(get_db),
):
    node = await get_node(db, entity_type, entity_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    return node


@router.get("/entity-types", response_model=list[str])
async def list_entity_types(db: aiosqlite.Connection = Depends(get_db)):
    rows = await db.execute("SELECT DISTINCT entity_type FROM entities ORDER BY entity_type")
    return [row[0] async for row in rows]


@router.get("/entities")
async def list_entities(
    entity_type: str = Query(...),
    limit: int = Query(50, ge=1, le=500),
    search: str = Query("", description="Optional search term for label"),
    db: aiosqlite.Connection = Depends(get_db),
):
    if search:
        rows = await db.execute(
            "SELECT entity_id, label FROM entities WHERE entity_type = ? AND label LIKE ? LIMIT ?",
            (entity_type, f"%{search}%", limit),
        )
    else:
        rows = await db.execute(
            "SELECT entity_id, label FROM entities WHERE entity_type = ? LIMIT ?",
            (entity_type, limit),
        )
    return [{"id": row[0], "type": entity_type, "label": row[1]} async for row in rows]


@router.get("/stats")
async def get_stats(db: aiosqlite.Connection = Depends(get_db)):
    rows = await db.execute("SELECT entity_type, COUNT(*) FROM entities GROUP BY entity_type ORDER BY entity_type")
    tables = {row[0]: row[1] async for row in rows}

    row = await db.execute("SELECT COUNT(*) FROM edges")
    total_edges = (await row.fetchone())[0]

    return {"tables": tables, "total_edges": total_edges}
