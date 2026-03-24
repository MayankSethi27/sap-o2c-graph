"""Load all JSONL files from sap-o2c-data/ into SQLite on startup."""

import json
import os
import glob
import aiosqlite

from ..database import DB_PATH, DATA_DIR

# (folder_name) -> (entity_type, pk_fields, label_func)
# pk_fields: list of JSON keys that form the composite primary key
ENTITY_CONFIG = {
    "business_partners":                ("business_partner",   ["businessPartner"],                              lambda r: r.get("businessPartnerFullName") or r.get("businessPartnerName") or r["businessPartner"]),
    "business_partner_addresses":       ("bp_address",         ["businessPartner", "addressId"],                 lambda r: f'{r["businessPartner"]}:{r["addressId"]}'),
    "customer_company_assignments":     ("cust_company",       ["customer", "companyCode"],                      lambda r: f'{r["customer"]}@{r["companyCode"]}'),
    "customer_sales_area_assignments":  ("cust_sales_area",    ["customer", "salesOrganization", "distributionChannel", "division"], lambda r: f'{r["customer"]}:{r["salesOrganization"]}/{r["distributionChannel"]}/{r["division"]}'),
    "products":                         ("product",            ["product"],                                      lambda r: r.get("product", "")),
    "product_descriptions":             ("product_desc",       ["product", "language"],                          lambda r: r.get("productDescription") or r["product"]),
    "product_plants":                   ("product_plant",      ["product", "plant"],                             lambda r: f'{r["product"]}@{r["plant"]}'),
    "product_storage_locations":        ("product_storage",    ["product", "plant", "storageLocation"],          lambda r: f'{r["product"]}@{r["plant"]}:{r["storageLocation"]}'),
    "plants":                           ("plant",              ["plant"],                                        lambda r: r.get("plantName") or r["plant"]),
    "sales_order_headers":              ("sales_order",        ["salesOrder"],                                   lambda r: f'SO {r["salesOrder"]}'),
    "sales_order_items":                ("sales_order_item",   ["salesOrder", "salesOrderItem"],                 lambda r: f'SO {r["salesOrder"]}/{r["salesOrderItem"]}'),
    "sales_order_schedule_lines":       ("schedule_line",      ["salesOrder", "salesOrderItem", "scheduleLine"], lambda r: f'SO {r["salesOrder"]}/{r["salesOrderItem"]}/L{r["scheduleLine"]}'),
    "outbound_delivery_headers":        ("delivery",           ["deliveryDocument"],                             lambda r: f'DL {r["deliveryDocument"]}'),
    "outbound_delivery_items":          ("delivery_item",      ["deliveryDocument", "deliveryDocumentItem"],     lambda r: f'DL {r["deliveryDocument"]}/{r["deliveryDocumentItem"]}'),
    "billing_document_headers":         ("billing_doc",        ["billingDocument"],                              lambda r: f'BL {r["billingDocument"]}'),
    "billing_document_items":           ("billing_doc_item",   ["billingDocument", "billingDocumentItem"],       lambda r: f'BL {r["billingDocument"]}/{r["billingDocumentItem"]}'),
    "billing_document_cancellations":   ("billing_cancel",     ["billingDocument"],                              lambda r: f'CX {r["billingDocument"]}'),
    "journal_entry_items_accounts_receivable": ("journal_item", ["companyCode", "fiscalYear", "accountingDocument", "glAccount"], lambda r: f'JE {r["accountingDocument"]}/{r["glAccount"]}'),
    "payments_accounts_receivable":     ("payment",            ["companyCode", "fiscalYear", "accountingDocument", "accountingDocumentItem"], lambda r: f'PAY {r["accountingDocument"]}/{r["accountingDocumentItem"]}'),
}

# Edge rules: (source_entity_type, source_fk_fields, target_entity_type, relationship_label, target_match_field)
# source_fk_fields: fields in the source record whose values identify the target
# target_match_field: the target PK field name to match against (for partial composite key matching)
#   When the target has a simple PK, this matches directly.
#   When the target has a composite PK, this specifies which PK component to search.
EDGE_RULES = [
    # Sales order -> customer (soldToParty -> businessPartner)
    ("sales_order",       ["soldToParty"],                  "business_partner",  "SOLD_TO",              "businessPartner"),
    # Sales order item -> sales order header
    ("sales_order_item",  ["salesOrder"],                   "sales_order",       "ITEM_OF",              "salesOrder"),
    # Sales order item -> product (material -> product)
    ("sales_order_item",  ["material"],                     "product",           "FOR_PRODUCT",          "product"),
    # Sales order item -> plant (productionPlant -> plant)
    ("sales_order_item",  ["productionPlant"],              "plant",             "FROM_PLANT",           "plant"),
    # Schedule line -> sales order item (composite match)
    ("schedule_line",     ["salesOrder", "salesOrderItem"], "sales_order_item",  "SCHEDULE_FOR",         None),
    # Delivery item -> delivery header
    ("delivery_item",     ["deliveryDocument"],             "delivery",          "ITEM_OF",              "deliveryDocument"),
    # Delivery item -> sales order (referenceSdDocument -> salesOrder)
    ("delivery_item",     ["referenceSdDocument"],          "sales_order",       "DELIVERS_ORDER",       "salesOrder"),
    # Delivery item -> plant
    ("delivery_item",     ["plant"],                        "plant",             "SHIPPED_FROM_PLANT",   "plant"),
    # Billing doc header -> customer (soldToParty -> businessPartner)
    ("billing_doc",       ["soldToParty"],                  "business_partner",  "BILLED_TO",            "businessPartner"),
    # Billing doc item -> billing doc header
    ("billing_doc_item",  ["billingDocument"],              "billing_doc",       "ITEM_OF",              "billingDocument"),
    # Billing doc item -> product (material -> product)
    ("billing_doc_item",  ["material"],                     "product",           "BILLS_PRODUCT",        "product"),
    # Billing doc item -> delivery (referenceSdDocument -> deliveryDocument)
    ("billing_doc_item",  ["referenceSdDocument"],          "delivery",          "BILLS_DELIVERY",       "deliveryDocument"),
    # Billing cancellation -> billing doc (cancelledBillingDocument -> billingDocument)
    ("billing_cancel",    ["cancelledBillingDocument"],     "billing_doc",       "CANCELS",              "billingDocument"),
    # Journal entry -> billing doc (referenceDocument -> billingDocument)
    ("journal_item",      ["referenceDocument"],            "billing_doc",       "POSTED_FROM",          "billingDocument"),
    # Journal entry -> customer (customer -> businessPartner)
    ("journal_item",      ["customer"],                     "business_partner",  "AR_FOR_CUSTOMER",      "businessPartner"),
    # Payment -> customer (customer -> businessPartner)
    ("payment",           ["customer"],                     "business_partner",  "PAID_BY",              "businessPartner"),
    # Payment -> journal entry (same accountingDocument)
    ("payment",           ["accountingDocument"],           "journal_item",      "PAYMENT_FOR_JOURNAL",  "accountingDocument"),
    # Payment -> clearing journal entry (clearingAccountingDocument -> accountingDocument)
    ("payment",           ["clearingAccountingDocument"],   "journal_item",      "CLEARS",               "accountingDocument"),
    # Business partner address -> business partner
    ("bp_address",        ["businessPartner"],              "business_partner",  "ADDRESS_OF",           "businessPartner"),
    # Customer company assignment -> business partner (customer -> businessPartner)
    ("cust_company",      ["customer"],                     "business_partner",  "COMPANY_ASSIGNMENT",   "businessPartner"),
    # Customer sales area -> business partner (customer -> businessPartner)
    ("cust_sales_area",   ["customer"],                     "business_partner",  "SALES_AREA_OF",        "businessPartner"),
    # Product description -> product
    ("product_desc",      ["product"],                      "product",           "DESCRIBES",            "product"),
    # Product plant -> product
    ("product_plant",     ["product"],                      "product",           "PRODUCT_AT_PLANT",     "product"),
    # Product plant -> plant
    ("product_plant",     ["plant"],                        "plant",             "AT_PLANT",             "plant"),
    # Product storage location -> product
    ("product_storage",   ["product"],                      "product",           "STORED_PRODUCT",       "product"),
    # Product storage location -> plant
    ("product_storage",   ["plant"],                        "plant",             "STORED_AT_PLANT",      "plant"),
]


def _make_id(pk_fields: list[str], record: dict) -> str:
    """Build composite ID from PK fields."""
    return ":".join(str(record.get(f, "")) for f in pk_fields)


async def load_all_data():
    """Load all 19 JSONL datasets and build edges. Skips if DB already populated."""
    async with aiosqlite.connect(DB_PATH) as db:
        # Check if already loaded
        row = await db.execute("SELECT COUNT(*) FROM entities")
        count = (await row.fetchone())[0]
        if count > 0:
            print(f"Database already has {count} entities, skipping ingest.")
            return

        print("Loading SAP O2C data from JSONL files...")

        # Phase 1: Load all entities
        entity_index: dict[str, dict[str, dict]] = {}  # type -> {id -> record}
        total = 0

        for folder_name, (etype, pk_fields, label_fn) in ENTITY_CONFIG.items():
            folder_path = os.path.join(DATA_DIR, folder_name)
            if not os.path.isdir(folder_path):
                print(f"  Skipping {folder_name}: folder not found")
                continue

            jsonl_files = glob.glob(os.path.join(folder_path, "*.jsonl"))
            entity_index[etype] = {}

            for fpath in jsonl_files:
                with open(fpath, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        rec = json.loads(line)
                        eid = _make_id(pk_fields, rec)
                        label = label_fn(rec)
                        entity_index[etype][eid] = rec
                        await db.execute(
                            "INSERT OR REPLACE INTO entities (entity_type, entity_id, label, data) VALUES (?, ?, ?, ?)",
                            (etype, eid, label, json.dumps(rec)),
                        )
                        total += 1

            print(f"  {folder_name} -> {len(entity_index[etype])} {etype} entities")

        await db.commit()
        print(f"Loaded {total} entities total.")

        # Phase 2: Build edges
        print("Building graph edges...")
        edge_count = 0

        # Lookup: entity_type -> pk_fields from ENTITY_CONFIG
        type_to_pk: dict[str, list[str]] = {}
        for _, (et, pks, _) in ENTITY_CONFIG.items():
            type_to_pk[et] = pks

        for rule in EDGE_RULES:
            src_type, src_fk_fields, tgt_type, rel, tgt_match_field = rule
            if src_type not in entity_index:
                continue

            tgt_ids = entity_index.get(tgt_type, {})
            if not tgt_ids:
                continue

            tgt_pk_fields = type_to_pk.get(tgt_type, [])

            # Build a partial index when FK has fewer fields than target PK.
            # Maps a target PK field's value -> list of full composite entity IDs.
            partial_index: dict[str, list[str]] = {}
            if tgt_match_field and len(tgt_pk_fields) > 1:
                for tgt_eid, tgt_rec in tgt_ids.items():
                    val = str(tgt_rec.get(tgt_match_field, ""))
                    if val:
                        partial_index.setdefault(val, []).append(tgt_eid)

            rule_count = 0
            for src_eid, rec in entity_index[src_type].items():
                fk_vals = [str(rec.get(f, "")) for f in src_fk_fields]
                if all(v == "" or v == "None" for v in fk_vals):
                    continue

                # Try exact composite key match first
                tgt_eid = ":".join(fk_vals)
                if tgt_eid in tgt_ids:
                    await db.execute(
                        "INSERT INTO edges (source_type, source_id, target_type, target_id, relationship) VALUES (?, ?, ?, ?, ?)",
                        (src_type, src_eid, tgt_type, tgt_eid, rel),
                    )
                    rule_count += 1
                elif len(src_fk_fields) == 1 and partial_index:
                    # Single FK -> partial match against a composite PK field
                    fk_val = fk_vals[0]
                    for matched_eid in partial_index.get(fk_val, []):
                        await db.execute(
                            "INSERT INTO edges (source_type, source_id, target_type, target_id, relationship) VALUES (?, ?, ?, ?, ?)",
                            (src_type, src_eid, tgt_type, matched_eid, rel),
                        )
                        rule_count += 1

            edge_count += rule_count
            if rule_count > 0:
                print(f"  {rel}: {rule_count} edges")

        await db.commit()
        print(f"Built {edge_count} edges total.")
