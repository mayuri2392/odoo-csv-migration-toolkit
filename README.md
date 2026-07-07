# odoo-csv-migration-toolkit

Reusable Python CLI for CSV-to-Odoo 18 data migration via XML-RPC, with SQL-based validation.

![Validation Report](screenshots/validation_report.png)

## What it does

Takes CSV extracts of partners, products, and invoices and loads them into a fresh Odoo 18 instance. Handles foreign-key resolution (countries, categories, taxes, partners, products), deduplication (idempotent re-runs), per-row error tolerance, and post-migration SQL validation against expected numbers.

## Why

Every Odoo SME implementation involves moving historical data from the client's old system (Excel, Exact, QuickBooks) into Odoo before go-live. This toolkit is the pattern I use in real client work at [Bluzee](https://www.bluzee.com), packaged as a public reference.

## Architecture

```
sample_data/*.csv   →   src/client.py   →   Odoo 18 (XML-RPC :8069)
                                                   │
                                                   ↓
                                              PostgreSQL
                                                   ↑
                        src/validate.py   ─────────┘
```

Loading goes through Odoo's ORM (XML-RPC → all validations, computed fields, defaults fire correctly). Validation queries PostgreSQL directly — bypasses the same layer that did the loading, so a silent XML-RPC bug can't hide itself in a matching-but-wrong result.

## Install and run

```bash
git clone https://github.com/mayuri2392/odoo-csv-migration-toolkit.git
cd odoo-csv-migration-toolkit
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp config/odoo.example.ini config/odoo.ini
# Edit config/odoo.ini with your Odoo URL, database, and API key
# Also set your Postgres user/password to match your docker-compose setup

python -m src.migrate_partners --csv sample_data/partners.csv --config config/odoo.ini
python -m src.migrate_products --csv sample_data/products.csv --config config/odoo.ini
python -m src.migrate_invoices --csv sample_data/invoices.csv --config config/odoo.ini
python -m src.validate --config config/odoo.ini
```

Tested against Odoo 18 Community Edition with the OdooMates `om_account_accountant` module. Works identically on Odoo 18 Enterprise (Invoicing module).

## What's demonstrated

- **XML-RPC connection layer** (`src/client.py`) — config-driven, handles auth via Odoo API key
- **Partner migration** — country FK lookup with in-memory caching, email-based dedup, per-row error tolerance
- **Product migration** — hierarchical category get-or-create, tax lookup by name, `default_code` dedup, Odoo 18's split `type`/`is_storable` fields
- **Invoice migration** — CSV group-by-invoice, parent+child creation via Odoo command tuples `(0, 0, {})`, draft state only
- **SQL validation** — direct PostgreSQL, count/sum/duplicate/null checks with expected values inline, exit code for CI

## What's NOT covered

- **Posting invoices** — deliberately out of scope. Migrations get data in; finance posts after review.
- **Opening balances** — separate workstream, journal-entry based.
- **Full-database Odoo-version migrations** — for that, see [OpenUpgrade](https://github.com/OCA/OpenUpgrade).

## Sample data

Twenty synthetic Dutch/EU SME partners (NL/DE/BE/FR), twenty products across furniture/stationery/electronics/services categories, twelve invoices with thirty-three line items totalling €32,031.55 ex-VAT. All data is synthetic — no real client information. Valid Dutch VAT numbers on NL companies pass Odoo's mod-11 checksum validator.

## Real-world gotchas encountered while building this

- Pandas' `read_csv` silently converts phone numbers like `+31201234567` to `int64`. Fixed with explicit `dtype=str`.
- Odoo 18 removed `'product'` as a valid `type` value on `product.template`. Storables now use `type='consu'` + `is_storable=True`.
- Odoo's `base_vat` module validates VAT numbers with country-specific checksums (mod-11 for NL). Synthetic VAT numbers must respect the checksum or the whole company batch is rejected.

## License

LGPL-3.0

---

*Author: [Mayuri Patil](https://www.linkedin.com/in/mayuri-mahendra-patil/) — Odoo Functional Consultant, Hoofddorp NL.*