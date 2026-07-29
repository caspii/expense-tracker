"""
Insert reviewed Wise card transactions into the expenses database.

Reads the `missing-YYYY.csv` produced by reconcile.py. That file is meant to be
edited first - delete any line you don't want, and this imports what remains.

Every inserted row carries `source_type='wise_import'` and the Wise transaction
id in `external_id`, so an import is idempotent (re-running inserts nothing) and
reversible:

    DELETE FROM expenses WHERE source_type = 'wise_import';

Dry run by default. Pass --apply to write.

    python import_wise.py reconcile-output/missing-2025.csv --apply
"""

import csv
from decimal import Decimal

import click
import psycopg2

from config import Config

# The transaction is already recorded; only its date is wrong. Inserting it
# would create the very duplicates reconcile.py exists to find.
ALREADY_RECORDED = 'same vendor and amount'


def add_external_id_column(conn):
    """Additive schema change, matching the `flask migrate-db` pattern.

    The unique index makes a re-run a no-op rather than a second copy - the gap
    that let an earlier ad-hoc import leave duplicate rows behind.
    """
    with conn.cursor() as cur:
        cur.execute('ALTER TABLE expenses ADD COLUMN IF NOT EXISTS external_id VARCHAR(100)')
        cur.execute('''
            CREATE UNIQUE INDEX IF NOT EXISTS expenses_external_id_key
            ON expenses (external_id) WHERE external_id IS NOT NULL
        ''')


def existing_external_ids(conn):
    with conn.cursor() as cur:
        cur.execute('SELECT external_id FROM expenses WHERE external_id IS NOT NULL')
        return {row[0] for row in cur.fetchall()}


def decimal_or_none(raw, places='0.01'):
    if raw is None or raw == '':
        return None
    return Decimal(raw).quantize(Decimal(places))


def build_row(record):
    """Map a reviewed CSV line onto the Expense columns.

    Amount and currency take the *merchant* side, which is how the database
    already records USD subscriptions. The EUR figure and rate come from Wise
    and are the ones actually charged - better than currency.convert_to_eur(),
    which only knows today's ECB rate.
    """
    amount_eur = decimal_or_none(record['amount_eur'])

    # `exchange_rate` means "1 EUR = X currency". Where Wise billed in USD or GBP
    # directly there is no EUR leg, and its rate column reads 1.0 - writing that
    # against USD would assert EUR 1 = USD 1 and quietly corrupt EUR totals.
    # Without a EUR amount there is no rate to record.
    rate = decimal_or_none(record['exchange_rate'], '0.000001') if amount_eur else None

    return {
        'amount': decimal_or_none(record['amount_original']),
        'currency': record['currency'],
        'type': 'cost',
        'cost_category': record['suggested_cost_category'],
        'explanation': record['merchant'],
        'vendor_name': record['merchant'],
        'amount_eur': amount_eur,
        'exchange_rate': rate,
        'expense_date': record['date'],
        'source_type': 'wise_import',
        'external_id': record['wise_id'],
    }


INSERT = '''
    INSERT INTO expenses (amount, currency, type, cost_category, explanation,
                          vendor_name, amount_eur, exchange_rate, expense_date,
                          source_type, external_id, tags, has_attachments, created_at)
    VALUES (%(amount)s, %(currency)s, %(type)s, %(cost_category)s, %(explanation)s,
            %(vendor_name)s, %(amount_eur)s, %(exchange_rate)s, %(expense_date)s,
            %(source_type)s, %(external_id)s, '{}', false, now())
    ON CONFLICT (external_id) WHERE external_id IS NOT NULL DO NOTHING
'''


@click.command()
@click.argument('missing_csv', type=click.Path(exists=True, dir_okay=False))
@click.option('--apply', 'do_apply', is_flag=True, help='Actually write. Otherwise dry run.')
@click.option('--include-personal', is_flag=True, help='Also import rows tagged likely_personal.')
@click.option('--exclude', multiple=True, help='Skip merchants containing this text (repeatable).')
def main(missing_csv, do_apply, include_personal, exclude):
    """Insert reviewed Wise transactions from a reconcile.py missing-*.csv."""
    with open(missing_csv, newline='', encoding='utf-8') as handle:
        records = list(csv.DictReader(handle))

    selected, skipped = [], []
    for record in records:
        merchant = record['merchant']
        if record['likely_personal'] == 'yes' and not include_personal:
            skipped.append((merchant, 'likely personal'))
        elif any(term.lower() in merchant.lower() for term in exclude):
            skipped.append((merchant, 'excluded by request'))
        elif ALREADY_RECORDED in record['why_not_matched']:
            skipped.append((merchant, f"already in DB as id {record['nearest_db_id']}, "
                                      f"wrong date - fix that row instead"))
        else:
            selected.append(record)

    for merchant, reason in sorted(set(skipped)):
        click.echo(f'  skip  {merchant:28} {reason}')
    click.echo(f'\n{len(selected)} rows to insert, {len(skipped)} skipped')

    total = sum((decimal_or_none(r['amount_eur']) or Decimal(0)) for r in selected)
    click.echo(f'EUR {total:,.2f} (rows without a EUR figure count as 0)')

    if not do_apply:
        click.echo('\nDry run. Re-run with --apply to write.')
        return

    conn = psycopg2.connect(Config.SQLALCHEMY_DATABASE_URI)
    try:
        add_external_id_column(conn)
        already = existing_external_ids(conn)
        fresh = [r for r in selected if r['wise_id'] not in already]
        if len(fresh) < len(selected):
            click.echo(f'{len(selected) - len(fresh)} already imported previously, skipping')

        with conn.cursor() as cur:
            for record in fresh:
                cur.execute(INSERT, build_row(record))
        conn.commit()
        click.echo(f'\ninserted {len(fresh)} rows as source_type=wise_import')
        click.echo('undo with: DELETE FROM expenses WHERE source_type = \'wise_import\';')
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    main()
