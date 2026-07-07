"""Migrate products from CSV to product.template via XML-RPC.

Usage:
    python -m src.migrate_products --csv sample_data/products.csv \
        --config config/odoo.ini

Note: Odoo 18 split product type. 'product' (storable) is no longer a
valid `type` value — storables are type='consu' + is_storable=True.
"""
import argparse
import csv
import pandas as pd
from .client import OdooClient


_category_cache = {}
_tax_cache = {}


def get_or_create_category(client, path):
    if path in _category_cache:
        return _category_cache[path]
    parts = [p.strip() for p in path.split("/")]
    parent_id = None
    for name in parts:
        domain = [["name", "=", name]]
        if parent_id is None:
            domain.append(["parent_id", "=", False])
        else:
            domain.append(["parent_id", "=", parent_id])
        ids = client.search("product.category", domain)
        if ids:
            parent_id = ids[0]
        else:
            parent_id = client.create(
                "product.category",
                {"name": name, "parent_id": parent_id},
            )
    _category_cache[path] = parent_id
    return parent_id


def lookup_tax_id(client, name):
    if not name:
        return None
    if name in _tax_cache:
        return _tax_cache[name]
    ids = client.search(
        "account.tax",
        [["name", "=", name], ["type_tax_use", "=", "sale"]],
    )
    tax_id = ids[0] if ids else None
    _tax_cache[name] = tax_id
    return tax_id


def find_existing_product(client, default_code):
    if not default_code:
        return None
    ids = client.search(
        "product.template", [["default_code", "=", default_code]]
    )
    return ids[0] if ids else None


def build_product_values(row, category_id, tax_id):
    """Odoo 18 split: 'product' (storable) becomes 'consu' + is_storable=True."""
    csv_type = row["type"].strip() or "consu"
    if csv_type == "product":
        odoo_type = "consu"
        is_storable = True
    elif csv_type == "service":
        odoo_type = "service"
        is_storable = False
    else:  # consu
        odoo_type = "consu"
        is_storable = False

    values = {
        "name": row["name"].strip(),
        "default_code": row["default_code"].strip(),
        "categ_id": category_id,
        "list_price": float(row["list_price"] or 0),
        "standard_price": float(row["standard_price"] or 0),
        "sale_ok": row["sale_ok"].strip().lower() == "true",
        "purchase_ok": row["purchase_ok"].strip().lower() == "true",
        "type": odoo_type,
        "is_storable": is_storable,
    }
    if tax_id:
        values["taxes_id"] = [(6, 0, [tax_id])]
    return values


def migrate(csv_path, config_path):
    client = OdooClient(config_path)
    df = pd.read_csv(csv_path, dtype=str).fillna("")

    created, updated, skipped = 0, 0, 0
    errors = []

    for idx, row in df.iterrows():
        try:
            category_id = get_or_create_category(client, row["category"])
            tax_id = lookup_tax_id(client, row["tax_name"])
            values = build_product_values(row.to_dict(), category_id, tax_id)
            existing_id = find_existing_product(client, row["default_code"])
            if existing_id:
                client.write("product.template", [existing_id], values)
                updated += 1
            else:
                client.create("product.template", values)
                created += 1
        except Exception as exc:
            skipped += 1
            errors.append({
                "row_index": idx,
                "default_code": row.get("default_code", ""),
                "name": row.get("name", ""),
                "error": str(exc),
            })

    if errors:
        with open("errors_products.csv", "w", newline="") as f:
            writer = csv.DictWriter(
                f, fieldnames=["row_index", "default_code", "name", "error"]
            )
            writer.writeheader()
            writer.writerows(errors)

    return {"created": created, "updated": updated,
            "skipped": skipped, "errors": errors}


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--csv", required=True)
    p.add_argument("--config", default="config/odoo.ini")
    args = p.parse_args()

    result = migrate(args.csv, args.config)
    print("Products migration complete.")
    print(f"  Created: {result['created']}")
    print(f"  Updated: {result['updated']}")
    print(f"  Skipped (errors): {result['skipped']}")
    if result["errors"]:
        print("  Error details: errors_products.csv")