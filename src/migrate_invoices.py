"""Migrate invoices from CSV to account.move via XML-RPC.

Usage:
    python -m src.migrate_invoices --csv sample_data/invoices.csv \
        --config config/odoo.ini

Creates draft customer invoices. Does not post.
"""
import argparse
import csv
import pandas as pd
from .client import OdooClient


_partner_cache = {}
_product_cache = {}
_journal_id = None


def lookup_partner_id(client, email):
    if email in _partner_cache:
        return _partner_cache[email]
    ids = client.search("res.partner", [["email", "=", email]])
    partner_id = ids[0] if ids else None
    _partner_cache[email] = partner_id
    return partner_id


def lookup_product_id(client, code):
    """Look up product.product (variant, not template) by default_code."""
    if code in _product_cache:
        return _product_cache[code]
    ids = client.search("product.product", [["default_code", "=", code]])
    product_id = ids[0] if ids else None
    _product_cache[code] = product_id
    return product_id


def get_sales_journal(client):
    global _journal_id
    if _journal_id is not None:
        return _journal_id
    ids = client.search("account.journal", [["type", "=", "sale"]])
    if not ids:
        raise RuntimeError("No sales journal found. Install Accounting/Invoicing.")
    _journal_id = ids[0]
    return _journal_id


def find_existing_invoice(client, invoice_number):
    ids = client.search(
        "account.move",
        [["ref", "=", invoice_number],
         ["move_type", "=", "out_invoice"]],
    )
    return ids[0] if ids else None


def build_invoice_lines(group_df, client):
    lines = []
    for _, row in group_df.iterrows():
        product_id = lookup_product_id(client, row["product_code"])
        if not product_id:
            raise ValueError(
                f"Product code '{row['product_code']}' not found. "
                "Run product migration first."
            )
        lines.append((0, 0, {
            "product_id": product_id,
            "quantity": float(row["quantity"]),
            "price_unit": float(row["price_unit"]),
        }))
    return lines


def migrate(csv_path, config_path):
    client = OdooClient(config_path)
    df = pd.read_csv(csv_path, dtype=str).fillna("")
    journal_id = get_sales_journal(client)

    created, updated, skipped = 0, 0, 0
    errors = []

    for invoice_number, group_df in df.groupby("invoice_number"):
        first_row = group_df.iloc[0]
        try:
            partner_id = lookup_partner_id(client, first_row["partner_email"])
            if not partner_id:
                raise ValueError(
                    f"Partner email '{first_row['partner_email']}' not found."
                )

            lines = build_invoice_lines(group_df, client)

            values = {
                "move_type": "out_invoice",
                "partner_id": partner_id,
                "invoice_date": first_row["invoice_date"],
                "journal_id": journal_id,
                "ref": invoice_number,
                "invoice_line_ids": lines,
            }

            existing_id = find_existing_invoice(client, invoice_number)
            if existing_id:
                # Update header only. Line replacement is a separate concern.
                client.write("account.move", [existing_id], {
                    "partner_id": partner_id,
                    "invoice_date": first_row["invoice_date"],
                })
                updated += 1
            else:
                client.create("account.move", values)
                created += 1

        except Exception as exc:
            skipped += 1
            errors.append({
                "invoice_number": invoice_number,
                "partner_email": first_row.get("partner_email", ""),
                "error": str(exc),
            })

    if errors:
        with open("errors_invoices.csv", "w", newline="") as f:
            writer = csv.DictWriter(
                f, fieldnames=["invoice_number", "partner_email", "error"]
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
    print("Invoices migration complete.")
    print(f"  Created: {result['created']}")
    print(f"  Updated: {result['updated']}")
    print(f"  Skipped (errors): {result['skipped']}")
    if result["errors"]:
        print("  Error details: errors_invoices.csv")