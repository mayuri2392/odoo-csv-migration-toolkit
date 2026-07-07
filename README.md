# odoo-csv-migration-toolkit

A Python CLI for CSV-to-Odoo 18 data migration — partners, products, and invoices — over XML-RPC, with SQL-based validation that proves counts, totals, duplicates, and required-field nulls before go-live sign-off.

![Odoo](https://img.shields.io/badge/Odoo-18%20Community-8B5CF6)
![License: LGPL-3](https://img.shields.io/badge/License-LGPL--3-blue.svg)
![Python](https://img.shields.io/badge/Python-3.10+-3776AB)

Built on Odoo 18 Community. Tested with the OdooMates `om_account_accountant` module and Netherlands fiscal localization.

---

## Table of Contents

- [What It Does](#what-it-does)
- [Screenshots](#screenshots)
- [Project Structure](#project-structure)
- [Installation](#installation)
- [Sample Data](#sample-data)
- [Workflow Overview](#workflow-overview)
- [Technical Notes](#technical-notes)
- [License](#license)
- [Author](#author)

---

## What It Does

### Partner Migration

- Reads a flat CSV of customer/supplier records and creates or updates `res.partner` via XML-RPC
- Resolves country codes (NL, DE, BE, FR) to Odoo country IDs with in-memory caching
- Deduplicates on email — safe to re-run without creating duplicates
- Handles both companies (with VAT) and individuals
- Tags migrated records with `ref = MIGRATION_DEMO` for validation isolation
- Per-row error tolerance — bad rows go to `errors_partners.csv`, batch continues

### Product Migration

- Loads `product.template` records with hierarchical categories (`All / Furniture`)
- Get-or-create pattern for missing category levels
- Looks up sales taxes by exact name (`21% ST` for goods, `21% ST S` for services in the Dutch localization)
- Deduplicates on `default_code` (internal reference)
- Handles Odoo 18's split `type` / `is_storable` fields

### Invoice Migration

- Reads a flat CSV of invoice lines and groups by `invoice_number` to build parent and children in one call
- Creates draft `account.move` records via Odoo command tuples `(0, 0, {})`
- Cross-migration foreign keys: partner by email, product by `default_code`
- Draft state only — posting is a separate finance-owned step after sign-off
- Deduplicates on the source invoice number stored in `ref`

### SQL Validation

- Direct PostgreSQL queries — bypasses the XML-RPC layer that did the loading
- Record counts per model against expected values from the source CSV
- Sum of invoice totals ex-VAT compared to source
- Duplicate detection on natural keys (email, `default_code`)
- Null checks on required fields (country on companies, VAT on NL companies)
- Exit code 0 on all-pass, 1 on any-fail — CI-scriptable

---

## Screenshots

### SQL Validation Report — 9 Checks, All Pass
![Validation report](screenshots/validation_report.png)

Direct SQL queries against Odoo's PostgreSQL — bypassing the XML-RPC layer that did the loading. Record counts, invoice totals ex-VAT, duplicate detection, and null checks with expected values inline for finance sign-off.

### Contacts List — Filtered to Migrated Partners
![Contacts list](screenshots/contacts_list.png)

Twenty partners across NL, DE, BE, and FR after migration. Mix of companies with valid Dutch VAT numbers and individuals. Filtered by the `.example` email domain to isolate the migrated set from Odoo's built-in demo partners.

### Products List — Grouped by Category
![Products list](screenshots/products_list.png)

Twenty products across four hierarchical categories: Furniture, Stationery, Electronics, and Services. The migration script's get-or-create pattern created the missing category levels. Filtered by internal reference prefix (FURN-, STAT-, TECH-, SVC-).

### Invoices List — Draft State, Filtered by Reference
![Invoices list](screenshots/invoices_list.png)

Twelve draft customer invoices with 33 line items, built from a flat CSV grouped by invoice number. Draft state — posting is a separate finance-owned step. Totals match source data down to the cent.

---

## Project Structure

```
odoo-csv-migration-toolkit/
├── config/
│   ├── odoo.example.ini       # Committed template with placeholders
│   └── odoo.ini               # Local secrets — gitignored
├── src/
│   ├── __init__.py
│   ├── client.py              # XML-RPC connection wrapper
│   ├── migrate_partners.py    # res.partner
│   ├── migrate_products.py    # product.template
│   ├── migrate_invoices.py    # account.move (draft)
│   └── validate.py            # PostgreSQL validation queries
├── sample_data/
│   ├── partners.csv           # 20 NL/EU SME partners
│   ├── products.csv           # 20 products across 4 categories
│   └── invoices.csv           # 33 lines forming 12 invoices
├── screenshots/
├── requirements.txt
└── README.md
```

Loading flows through Odoo's ORM via XML-RPC (so validations, computed fields, and defaults fire correctly). Validation queries PostgreSQL directly — a bug in the loader can't hide itself in a matching-but-wrong validation query.

---

## Installation

**Prerequisites:** Odoo 18 running on `localhost:8069` with the Contacts, Inventory, and Accounting (or Invoicing) modules installed. Netherlands fiscal localization enabled for the tax records the sample CSVs reference. Python 3.10+ with virtual environment support on the client machine.

```bash
git clone https://github.com/mayuri2392/odoo-csv-migration-toolkit
cd odoo-csv-migration-toolkit
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp config/odoo.example.ini config/odoo.ini
```

Edit `config/odoo.ini` with your Odoo URL, database name, admin username, API key, and Postgres credentials.

**Run the migrations in order:**

```bash
python -m src.migrate_partners --csv sample_data/partners.csv --config config/odoo.ini
python -m src.migrate_products --csv sample_data/products.csv --config config/odoo.ini
python -m src.migrate_invoices --csv sample_data/invoices.csv --config config/odoo.ini
python -m src.validate --config config/odoo.ini
```

> `config/odoo.ini` is gitignored to prevent API keys from leaking. Only `config/odoo.example.ini` (a placeholder template) is committed. Generate an Odoo API key under **My Profile → Account Security → New API Key** rather than putting your admin password in the config file.

---

## Sample Data

Twenty synthetic Dutch and EU SME partners across NL, DE, BE, and FR — mix of companies (with valid Dutch VAT numbers passing Odoo's mod-11 checksum) and individuals. Twenty products spanning furniture, stationery, electronics, and services categories. Twelve invoices with 33 line items totalling €32,031.55 ex-VAT.

All data is synthetic — no real client information.

---

## Workflow Overview

### Load Order

Partners must exist before products can reference them via invoices. Products must exist before invoice lines can reference them. Run in the order shown in Installation — partners → products → invoices → validate.

### Idempotency

Every migration script is safe to re-run. On the second run:

- Partners match by email → `Updated: 20, Created: 0`
- Products match by `default_code` → `Updated: 20, Created: 0`
- Invoices match by `ref` → `Updated: 12, Created: 0`

Bad-data fixes go into the source CSV, then a re-run brings Odoo back in sync without duplicates.

### Error Handling

Each row is wrapped in try/except. On failure, the row index, natural key, and error message are appended to a per-model `errors_*.csv` in the project root (gitignored). The batch continues. The output at the end reports created/updated/skipped counts and points to the error file if any rows failed.

---

## Technical Notes

- All CSV reads use `dtype=str` to prevent pandas from silently converting phone numbers to `int64` (a leading `+` is treated as a numeric sign).
- Odoo 18 split the `product.template.type` field. Storable products are `type='consu'` combined with `is_storable=True` — the migration script handles this mapping from the CSV's `type` column.
- Migrated partners are tagged with `ref='MIGRATION_DEMO'` so the validation script can isolate them from Odoo's built-in demo partners without relying on email patterns.
- VAT numbers are validated by Odoo's `base_vat` module at write time. The sample data uses Dutch VAT numbers that pass the mod-11 checksum; DE and BE company VAT fields are left empty rather than faking their country-specific formats.
- Tax lookups are case- and format-sensitive. The sample CSV uses `21% ST` and `21% ST S` matching the OdooMates NL localization; adjust the `tax_name` column for other Odoo variants (Enterprise typically uses `21% BTW`).
- Invoices are created in `draft` state only. Posting triggers sequence assignment and general-ledger writes, which are finance-owned actions after migration sign-off.

---

## License

[LGPL-3](LICENSE)

---

## Author

**Mayuri Patil** — Odoo Functional + Technical Consultant

6 years across B2B retail, logistics, and perishable goods. Open to EU roles.

[![LinkedIn](https://img.shields.io/badge/LinkedIn-mayuri--patil--2392-0A66C2?logo=linkedin)](https://linkedin.com/in/mayuri-patil-2392)
[![GitHub](https://img.shields.io/badge/GitHub-mayuri2392-181717?logo=github)](https://github.com/mayuri2392)