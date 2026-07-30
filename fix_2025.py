"""
One-off corrections to 2025 expenses, derived from the Wise card statement.

Three kinds of change, all cross-checked against the card before being applied:

  1. Delete rows duplicated inside the database (a second copy of one charge).
  2. Delete rows this import added on top of an existing *aggregated* row - where
     one database row already covered several card charges, so a per-charge
     insert double-counted it.
  3. Correct amounts that disagree with the card. Mostly USD charges recorded as
     EUR, plus two digit typos.

Writes an undo script before touching anything. Dry run unless --apply.

    python fix_2025.py --apply
"""

from pathlib import Path

import click
import psycopg2
import psycopg2.extras

from config import Config
from reconcile import load_csv, load_db_rows, reconcile

UNDO_PATH = 'db-backups/undo-fix-2025.sql'

# Verified duplicates: same date, amount and currency, only one backed by a card
# charge. The spare double-counts a deduction.
DELETE_DUPLICATES = {
    363: 'duplicate of 307 (Buffer, 2025-11-12, 48.00 USD)',
    382: 'duplicate of 375 (Ahrefs.com, 2025-11-30, 179.00 EUR)',
    762: 'duplicate of 8 (Ahrefs, 2025-12-30, 179.00 EUR)',
}

# Rows this import created that were already covered by an aggregated row.
# id159 "Ads Microsoft" 101.78 == the two 2025-04-10 charges 51.32 + 50.46.
DELETE_DOUBLE_COUNTED = {
    1607: 'already inside id159 (Ads Microsoft 101.78 = 51.32 + 50.46)',
    1611: 'already inside id159 (Ads Microsoft 101.78 = 51.32 + 50.46)',
}

# id161 "Ads Microsoft" 109.80 does NOT decompose into any combination of April
# card charges, so it is separate ad spend that never touched this card. Its
# same-day pairing with a 50.23 charge is a coincidence, not an error - leave it.
KEEP_DESPITE_FLAG = {161: 'does not correspond to any card charge; not a typo'}


def capture_undo(conn, ids):
    """Write the current state of these rows as restorable SQL."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute('SELECT * FROM expenses WHERE id = ANY(%s) ORDER BY id', (list(ids),))
        records = cur.fetchall()

    lines = ['-- Undo for fix_2025.py. Restores the rows it deleted or changed.',
             'BEGIN;']
    for record in records:
        fields = {k: v for k, v in record.items() if k != 'attachment_data'}
        columns = ', '.join(fields)
        values = ', '.join('NULL' if v is None else
                           ("'" + str(v).replace("'", "''") + "'")
                           for v in fields.values())
        lines.append(f'DELETE FROM expenses WHERE id = {record["id"]};')
        lines.append(f'INSERT INTO expenses ({columns}) VALUES ({values});')
    lines.append("SELECT setval('expenses_id_seq', (SELECT max(id) FROM expenses));")
    lines.append('COMMIT;')
    undo = Path(UNDO_PATH)
    undo.parent.mkdir(parents=True, exist_ok=True)
    undo.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return len(records)


def planned_corrections(conn):
    """Discrepancies from reconcile.py, as (row, txn), minus the ones we keep."""
    txns, _ = load_csv('.context/attachments/V21A2l/transaction-history.csv', 2025)
    rows = load_db_rows(conn, 2025, 45)
    _, _, discrepancies, _ = reconcile(txns, rows)
    return [(row, txn) for txn, row, *_ in discrepancies if row.id not in KEEP_DESPITE_FLAG]


@click.command()
@click.option('--apply', 'do_apply', is_flag=True, help='Actually write. Otherwise dry run.')
def main(do_apply):
    """Delete duplicated rows and correct amounts that disagree with the card."""
    conn = psycopg2.connect(Config.SQLALCHEMY_DATABASE_URI)
    try:
        corrections = planned_corrections(conn)

        click.echo('DELETE — duplicates inside the database')
        for expense_id, why in sorted(DELETE_DUPLICATES.items()):
            click.echo(f'  id {expense_id:<5} {why}')

        click.echo('\nDELETE — double-counted by this import')
        for expense_id, why in sorted(DELETE_DOUBLE_COUNTED.items()):
            click.echo(f'  id {expense_id:<5} {why}')

        click.echo('\nUPDATE — amount disagrees with the card')
        for row, txn in sorted(corrections, key=lambda p: p[0].id):
            amount = txn.tgt_amount if txn.tgt_amount is not None else txn.src_amount
            currency = txn.tgt_currency or txn.src_currency
            click.echo(f'  id {row.id:<5} {row.vendor_name[:22]:22} '
                       f'{row.amount} {row.currency} -> {amount} {currency}'
                       f'   (eur {txn.amount_eur})')

        click.echo('\nKEEP — flagged but verified correct')
        for expense_id, why in sorted(KEEP_DESPITE_FLAG.items()):
            click.echo(f'  id {expense_id:<5} {why}')

        deletions = set(DELETE_DUPLICATES) | set(DELETE_DOUBLE_COUNTED)
        click.echo(f'\n{len(deletions)} deletions, {len(corrections)} corrections')

        if not do_apply:
            click.echo('\nDry run. Re-run with --apply to write.')
            return

        touched = deletions | {row.id for row, _ in corrections}
        saved = capture_undo(conn, touched)
        click.echo(f'\nundo script written for {saved} rows: {UNDO_PATH}')

        with conn.cursor() as cur:
            cur.execute('DELETE FROM expenses WHERE id = ANY(%s)', (list(deletions),))
            deleted = cur.rowcount
            for row, txn in corrections:
                cur.execute(
                    '''UPDATE expenses
                       SET amount = %s, currency = %s, amount_eur = %s, exchange_rate = %s
                       WHERE id = %s''',
                    (txn.tgt_amount if txn.tgt_amount is not None else txn.src_amount,
                     txn.tgt_currency or txn.src_currency,
                     txn.amount_eur,
                     txn.exchange_rate if txn.amount_eur else None,
                     row.id))
        conn.commit()
        click.echo(f'deleted {deleted} rows, corrected {len(corrections)} rows')
        click.echo(f'undo with: psql "{Config.SQLALCHEMY_DATABASE_URI}" -f {UNDO_PATH}')
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    main()
