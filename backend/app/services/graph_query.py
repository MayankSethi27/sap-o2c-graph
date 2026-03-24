"""Graph traversal queries over the entities + edges tables."""

import json
import aiosqlite
from ..models.schemas import NodeOut, EdgeOut, GraphOut


async def get_node(db: aiosqlite.Connection, entity_type: str, entity_id: str) -> NodeOut | None:
    row = await db.execute(
        "SELECT label, data FROM entities WHERE entity_type = ? AND entity_id = ?",
        (entity_type, entity_id),
    )
    result = await row.fetchone()
    if not result:
        return None
    return NodeOut(
        id=f"{entity_type}:{entity_id}",
        type=entity_type,
        label=result[0],
        data=json.loads(result[1]),
    )


async def traverse(db: aiosqlite.Connection, entity_type: str, entity_id: str, depth: int = 1) -> GraphOut:
    """BFS traversal from a starting node up to `depth` hops."""
    visited_nodes: dict[str, NodeOut] = {}
    collected_edges: list[EdgeOut] = []
    frontier = [(entity_type, entity_id)]

    for _ in range(depth):
        next_frontier = []
        for etype, eid in frontier:
            node_key = f"{etype}:{eid}"
            if node_key not in visited_nodes:
                node = await get_node(db, etype, eid)
                if node:
                    visited_nodes[node_key] = node

            # Outgoing edges
            rows = await db.execute(
                "SELECT target_type, target_id, relationship FROM edges WHERE source_type = ? AND source_id = ?",
                (etype, eid),
            )
            async for row in rows:
                tgt_type, tgt_id, rel = row[0], row[1], row[2]
                collected_edges.append(EdgeOut(
                    source=f"{etype}:{eid}",
                    target=f"{tgt_type}:{tgt_id}",
                    relationship=rel,
                ))
                next_frontier.append((tgt_type, tgt_id))

            # Incoming edges
            rows = await db.execute(
                "SELECT source_type, source_id, relationship FROM edges WHERE target_type = ? AND target_id = ?",
                (etype, eid),
            )
            async for row in rows:
                src_type, src_id, rel = row[0], row[1], row[2]
                collected_edges.append(EdgeOut(
                    source=f"{src_type}:{src_id}",
                    target=f"{etype}:{eid}",
                    relationship=rel,
                ))
                next_frontier.append((src_type, src_id))

        frontier = [(t, i) for t, i in next_frontier if f"{t}:{i}" not in visited_nodes]

    # Resolve frontier nodes
    for etype, eid in frontier:
        node_key = f"{etype}:{eid}"
        if node_key not in visited_nodes:
            node = await get_node(db, etype, eid)
            if node:
                visited_nodes[node_key] = node

    # Deduplicate edges
    seen = set()
    unique_edges = []
    for e in collected_edges:
        key = (e.source, e.target, e.relationship)
        if key not in seen:
            seen.add(key)
            unique_edges.append(e)

    return GraphOut(nodes=list(visited_nodes.values()), edges=unique_edges)


async def get_full_graph(db: aiosqlite.Connection, exclude_types: list[str]) -> GraphOut:
    """Return all nodes and edges, optionally excluding high-volume entity types."""
    # Build nodes
    if exclude_types:
        placeholders = ",".join("?" for _ in exclude_types)
        rows = await db.execute(
            f"SELECT entity_type, entity_id, label, data FROM entities WHERE entity_type NOT IN ({placeholders})",
            exclude_types,
        )
    else:
        rows = await db.execute("SELECT entity_type, entity_id, label, data FROM entities")

    node_keys = set()
    nodes = []
    async for row in rows:
        etype, eid, label, data = row[0], row[1], row[2], row[3]
        key = f"{etype}:{eid}"
        node_keys.add(key)
        nodes.append(NodeOut(id=key, type=etype, label=label, data=json.loads(data)))

    # Build edges — only include edges where both endpoints are in the node set
    rows = await db.execute("SELECT source_type, source_id, target_type, target_id, relationship FROM edges")
    edges = []
    async for row in rows:
        src_key = f"{row[0]}:{row[1]}"
        tgt_key = f"{row[2]}:{row[3]}"
        if src_key in node_keys and tgt_key in node_keys:
            edges.append(EdgeOut(source=src_key, target=tgt_key, relationship=row[4]))

    return GraphOut(nodes=nodes, edges=edges)
