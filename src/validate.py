"""SQL validation for a completed migration.

Runs a suite of counts, sums, duplicate detects, and null checks against
the Odoo PostgreSQL database. Compares against expected values from the
source CSV.

Isolation of migrated records:
  - Partners: filtered by ref = 'MIGRATION_DEMO' (set by migrate_partners)
  - Products: filtered by default_code prefix (FURN-, STAT-, TECH-, SVC-)
  - Invoices: filtered by ref LIKE 'INV-2026-%' (source invoice numbers)

Usage:
    python -m src.validate --config config/odoo.ini
"""
import argparse
import configparser
import psycopg2


EXPECTED = {
    "partner_count": 20,
    "product_count": 20,
    "invoice_count": 12,
    "invoice_line_count": 33,
    "invoice_total_ex_vat": 32031.55,
}


CHECKS = {
    "partner_count": """
        SELECT COUNT(*) FROM res_partner
        WHERE active = TRUE
          AND ref = 'MIGRATION_DEMO'
    """,
    "product_count": """
        SELECT COUNT(*) FROM product_template
        WHERE active = TRUE
          AND default_code SIMILAR TO '(FURN|STAT|TECH|SVC)-%'
    """,
    "invoice_count": """
        SELECT COUNT(*) FROM account_move
        WHERE move_type = 'out_invoice'
          AND ref LIKE 'INV-2026-%'
    """,
    "invoice_line_count": """
        SELECT COUNT(*) FROM account_move_line l
        JOIN account_move m ON m.id = l.move_id
        WHERE m.move_type = 'out_invoice'
          AND m.ref LIKE 'INV-2026-%'
          AND l.product_id IS NOT NULL
    """,
    "invoice_total_ex_vat": """
        SELECT COALESCE(SUM(amount_untaxed), 0)
        FROM account_move
        WHERE move_type = 'out_invoice'
          AND ref LIKE 'INV-2026-%'
    """,
    "duplicate_partner_emails": """
        SELECT email, COUNT(*)
        FROM res_partner
        WHERE ref = 'MIGRATION_DEMO'
          AND email IS NOT NULL AND email != ''
        GROUP BY email
        HAVING COUNT(*) > 1
    """,
    "duplicate_product_codes": """
        SELECT default_code, COUNT(*)
        FROM product_template
        WHERE default_code SIMILAR TO '(FURN|STAT|TECH|SVC)-%'
        GROUP BY default_code
        HAVING COUNT(*) > 1
    """,
    "null_country_partners": """
        SELECT name FROM res_partner
        WHERE ref = 'MIGRATION_DEMO'
          AND country_id IS NULL
    """,
    "null_vat_nl_companies": """
        SELECT name FROM res_partner
        WHERE ref = 'MIGRATION_DEMO'
          AND is_company = TRUE
          AND (vat IS NULL OR vat = '')
          AND country_id = (SELECT id FROM res_country WHERE code = 'NL')
    """,
}


def main(config_path):
    cfg = configparser.ConfigParser()
    cfg.read(config_path)
    pg = cfg["postgres"]

    print("=" * 60)
    print("MIGRATION VALIDATION REPORT")
    print("=" * 60)

    passed, failed = 0, 0

    with psycopg2.connect(
        host=pg["host"], port=pg["port"], dbname=pg["dbname"],
        user=pg["user"], password=pg["password"],
    ) as conn:
        with conn.cursor() as cur:
            for name, sql in CHECKS.items():
                cur.execute(sql)
                rows = cur.fetchall()

                if name in EXPECTED:
                    actual = rows[0][0] if rows else 0
                    expected = EXPECTED[name]
                    if isinstance(expected, float):
                        ok = abs(float(actual) - expected) < 0.01
                    else:
                        ok = actual == expected
                    status = "PASS" if ok else "FAIL"
                    print(f"[{status}] {name:30s} "
                          f"actual={actual}  expected={expected}")
                    if ok:
                        passed += 1
                    else:
                        failed += 1
                else:
                    if not rows:
                        print(f"[PASS] {name:30s} 0 issues found")
                        passed += 1
                    else:
                        print(f"[FAIL] {name:30s} {len(rows)} issue(s):")
                        for row in rows[:5]:
                            print(f"       {row}")
                        if len(rows) > 5:
                            print(f"       ... and {len(rows) - 5} more")
                        failed += 1

    print("=" * 60)
    print(f"Result: {passed} passed, {failed} failed")
    print("=" * 60)
    return failed == 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--config", default="config/odoo.ini")
    args = p.parse_args()
    ok = main(args.config)
    raise SystemExit(0 if ok else 1)