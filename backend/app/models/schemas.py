from pydantic import BaseModel
from typing import Any


class NodeOut(BaseModel):
    id: str
    type: str
    label: str
    data: dict[str, Any]


class EdgeOut(BaseModel):
    source: str
    target: str
    relationship: str


class GraphOut(BaseModel):
    nodes: list[NodeOut]
    edges: list[EdgeOut]
