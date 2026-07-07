"""Migrate partners from CSV to res.partner via XML-RPC.

Usage:
    python -m src.migrate_partners --csv sample_data/partners.csv \
        --config config/odoo.ini
"""
import argparse
import csv
import pandas as pd
from .client import OdooClient


_country_cache = {}


def lookup_country_id(client, code):
    """Look up res.country ID by ISO code. Cached."""
    if not code:
        return None
    if code in _country_cache:
        return _country_cache[code]
    ids = client.search("res.country", [["code", "=", code]])
    country_id = ids[0] if ids else None
    _country_cache[code] = country_id
    return country_id


def find_existing_partner(client, email):
    """Return existing partner ID by email, or None."""
    if not email:
        return None
    ids = client.search("res.partner", [["email", "=", email]])
    return ids[0] if ids else None


def build_partner_values(row, country_id):
    """Transform a CSV row dict into an Odoo values dict."""
    return {
        "name": row["name"].strip(),
        "email": row["email"].strip() or False,
        "phone": row["phone"].strip() or False,
        "street": row["street"].strip() or False,
        "city": row["city"].strip() or False,
        "zip": row["zip"].strip() or False,
        "country_id": country_id,
        "is_company": row["is_company"].strip().lower() == "true",
        "vat": row["vat"].strip() or False,
        "customer_rank": int(row["customer_rank"] or 0),
        "supplier_rank": int(row["supplier_rank"] or 0),
    }


def migrate(csv_path, config_path):
    client = OdooClient(config_path)
    # dtype=str forces ALL columns to be read as strings.
    # Prevents pandas from silently converting e.g. "+31201234567" to int.
    df = pd.read_csv(csv_path, dtype=str).fillna("")

    created, updated, skipped = 0, 0, 0
    errors = []

    for idx, row in df.iterrows():
        try:
            country_id = lookup_country_id(client, row["country_code"])
            values = build_partner_values(row.to_dict(), country_id)
            existing_id = find_existing_partner(client, row["email"])
            if existing_id:
                client.write("res.partner", [existing_id], values)
                updated += 1
            else:
                client.create("res.partner", values)
                created += 1
        except Exception as exc:
            skipped += 1
            errors.append({
                "row_index": idx,
                "name": row.get("name", ""),
                "email": row.get("email", ""),
                "error": str(exc),
            })

    if errors:
        with open("errors_partners.csv", "w", newline="") as f:
            writer = csv.DictWriter(
                f, fieldnames=["row_index", "name", "email", "error"]
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
    print("Partners migration complete.")
    print(f"  Created: {result['created']}")
    print(f"  Updated: {result['updated']}")
    print(f"  Skipped (errors): {result['skipped']}")
    if result["errors"]:
        print("  Error details: errors_partners.csv")
