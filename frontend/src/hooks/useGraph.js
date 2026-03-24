import { useState, useEffect } from "react";
import { fetchFullGraph } from "../services/api";

const TYPE_COLORS = {
  business_partner: "#4CAF50",
  product: "#2196F3",
  product_desc: "#64B5F6",
  plant: "#FF9800",
  sales_order: "#9C27B0",
  sales_order_item: "#BA68C8",
  delivery: "#F44336",
  delivery_item: "#EF9A9A",
  billing_doc: "#00BCD4",
  billing_doc_item: "#80DEEA",
  billing_cancel: "#FF5722",
  journal_item: "#795548",
  payment: "#E91E63",
};

function toGraphData(result) {
  const nodes = result.nodes.map((n) => ({
    id: n.id,
    label: n.label,
    type: n.type,
    color: TYPE_COLORS[n.type] || "#999",
    data: n.data,
  }));
  const links = result.edges.map((e) => ({
    source: e.source,
    target: e.target,
    label: e.relationship,
  }));
  return { nodes, links };
}

export default function useGraph() {
  const [graphData, setGraphData] = useState({ nodes: [], links: [] });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchFullGraph()
      .then((result) => setGraphData(toGraphData(result)))
      .finally(() => setLoading(false));
  }, []);

  return { graphData, loading };
}
