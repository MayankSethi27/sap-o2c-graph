const LEGEND_ITEMS = [
  { type: "business_partner", label: "Customer", color: "#4CAF50" },
  { type: "sales_order", label: "Sales Order", color: "#9C27B0" },
  { type: "sales_order_item", label: "SO Item", color: "#BA68C8" },
  { type: "delivery", label: "Delivery", color: "#F44336" },
  { type: "delivery_item", label: "DL Item", color: "#EF9A9A" },
  { type: "billing_doc", label: "Billing Doc", color: "#00BCD4" },
  { type: "billing_doc_item", label: "BL Item", color: "#80DEEA" },
  { type: "billing_cancel", label: "Cancellation", color: "#FF5722" },
  { type: "journal_item", label: "Journal Entry", color: "#795548" },
  { type: "payment", label: "Payment", color: "#E91E63" },
  { type: "product", label: "Product", color: "#2196F3" },
  { type: "product_desc", label: "Product Desc", color: "#64B5F6" },
  { type: "plant", label: "Plant", color: "#FF9800" },
];

export default function Legend() {
  return (
    <div className="legend">
      {LEGEND_ITEMS.map((item) => (
        <div key={item.type} className="legend-item">
          <span className="legend-dot" style={{ background: item.color }} />
          <span className="legend-label">{item.label}</span>
        </div>
      ))}
    </div>
  );
}
