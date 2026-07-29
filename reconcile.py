"""
Reconcile a Wise card transaction-history CSV against the expenses database.

Answers one question: which card transactions are missing from the DB?

Report-only. The database connection is opened as a read-only Postgres session,
so writes are rejected by the server, not merely avoided by convention. The
local database holds live production data (see CLAUDE.md).

Usage:
    python reconcile.py transaction-history.csv --year 2025
"""

import csv
import difflib
import re
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import click
import psycopg2

from config import Config

# ---------------------------------------------------------------------------
# Vendor knowledge. This is the part that gets hand-edited each year.
# ---------------------------------------------------------------------------

# Wise merchant name -> the vendor_name it appears under in the database.
# Only entries listed here are trusted for matching. Automatic similarity is
# reported as a suggestion but never applied: it proposes "Claude" -> "CloudFlare",
# which would silently reconcile 14 Anthropic charges against the wrong vendor.
VENDOR_ALIASES = {
    'claude': 'Anthropic',
    'twilio': 'Sendgrid',                       # Twilio owns SendGrid
    'solarwinds': 'Papertrail',
    # Both Gsuite accounts collapse to this once normalize() drops the account
    # suffix, so one key covers "Wrede2024.c" and "Keepthescor" alike.
    'google gsuite': 'Google Workspace',
    'microsoft': 'LAN DATA (Microsoft Office)',
    'dnsimple registrar': 'DNSimple',
    'superhuman': 'Superhuman Mail',
    'customer io email mark': 'Customer.io',
    'canva design and publishing': 'Canva',
    'buffer plan': 'Buffer',
    'wispr': 'Wispr Flow',
    'chatgpt subscription': 'OpenAI',
    'openai chatgpt subscription': 'OpenAI',
    'dp dodopay nanobanana': 'Nano Banana AI Studio',
    'nano ba9qaa': 'Nano Banana AI Studio',
    'forwardmx invoice 896': 'ForwardMX',
    'notion labs': 'Notion',
}

# Merchants that look like private spending rather than business costs.
# Tagged, never dropped - the point is to let you skim past them.
# MediaMarkt is deliberately absent: the 2025 charge there was an iPhone, i.e.
# equipment. Electronics retailers are business purchases often enough that
# guessing "personal" costs more than leaving them to be triaged.
PERSONAL_MERCHANTS = (
    'nintendo', 'easyjet', 'spirit airlines', 'totalenergies',
    'cafe', 'konditorei', 'gondola', 'alter krug', 'lexington', 'bio ',
    'amazon prime', 'auto tanken',
)

# Wise's own categories that indicate private spending.
PERSONAL_WISE_CATEGORIES = {'Groceries', 'Eating out', 'Trips', 'Cash', 'Transport'}

EQUIPMENT_MERCHANTS = ('mediamarkt', 'apple store', 'apple')

LEGAL_SUFFIXES = re.compile(
    r'\b(pte|ltd|llc|inc|gmbh|corp|limited|plc|bv|sarl|ug)\b\.?', re.IGNORECASE
)

# Account-identifying noise Wise appends to some merchant names.
NOISE_TOKENS = {'wrede2024', 'keepthescor', 'c'}


def normalize(name):
    """Reduce a vendor name to a comparable form."""
    if not name:
        return ''
    text = name.lower().replace('ı', 'i')        # "Notıon Labs" -> "notion labs"
    text = LEGAL_SUFFIXES.sub(' ', text)
    text = re.sub(r'[^a-z0-9 ]', ' ', text)
    tokens = [t for t in text.split() if t not in NOISE_TOKENS]
    return ' '.join(tokens)


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

class Txn:
    """One Wise card transaction."""

    def __init__(self, idx, row):
        self.idx = idx
        self.wise_id = row['ID']
        self.date = date.fromisoformat(row['Created on'][:10])
        self.merchant = row['Target name']
        self.norm = normalize(self.merchant)
        self.wise_category = row['Category']

        self.src_amount = _money(row['Source amount (after fees)'])
        self.src_currency = row['Source currency']
        self.tgt_amount = _money(row['Target amount (after fees)'])
        self.tgt_currency = row['Target currency']
        self.exchange_rate = row['Exchange rate']

        # The database stores sometimes the EUR charged, sometimes the merchant
        # amount, so both are valid join keys.
        keys = {(self.src_amount, self.src_currency)}
        if self.tgt_amount is not None and self.tgt_currency:
            keys.add((self.tgt_amount, self.tgt_currency))
        self.amount_keys = keys

        self.amount_eur = self.src_amount if self.src_currency == 'EUR' else None

    @property
    def alias(self):
        return VENDOR_ALIASES.get(self.norm)

    @property
    def is_personal(self):
        if self.wise_category in PERSONAL_WISE_CATEGORIES:
            return True
        return any(k in self.norm for k in PERSONAL_MERCHANTS)

    @property
    def suggested_cost_category(self):
        if self.is_personal:
            return 'other'
        if any(k in self.norm for k in EQUIPMENT_MERCHANTS):
            return 'equipment'
        return 'operations'

    def sort_amount(self):
        """EUR value where known, for ranking. Falls back to the source amount."""
        return self.amount_eur if self.amount_eur is not None else self.src_amount


class DbRow:
    """One expense row from the database."""

    def __init__(self, rec):
        (self.id, self.date, amount, self.currency, amount_eur,
         self.vendor_name, self.explanation, self.cost_category) = rec
        self.amount = _q(amount)
        self.amount_eur = _q(amount_eur) if amount_eur is not None else None
        self.norm = normalize(self.vendor_name or self.explanation)


def _q(value):
    return Decimal(str(value)).quantize(Decimal('0.01'))


def _money(raw):
    if raw is None or raw == '':
        return None
    return _q(raw)


def load_csv(path, year):
    """Completed outgoing card transactions for the given year."""
    txns, skipped = [], 0
    with open(path, newline='', encoding='utf-8') as handle:
        for row in csv.DictReader(handle):
            if row['Status'] != 'COMPLETED' or row['Direction'] != 'OUT':
                skipped += 1
                continue
            if year and row['Created on'][:4] != str(year):
                skipped += 1
                continue
            txns.append(Txn(len(txns), row))
    return txns, skipped


def infer_year(path):
    with open(path, newline='', encoding='utf-8') as handle:
        years = defaultdict(int)
        for row in csv.DictReader(handle):
            years[row['Created on'][:4]] += 1
    return int(max(years, key=years.get))


def load_db_rows(conn, year, margin_days):
    """Cost rows around the target year. Reads only."""
    start = date(year, 1, 1) - timedelta(days=margin_days)
    end = date(year + 1, 1, 1) + timedelta(days=margin_days)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, expense_date, amount, currency, amount_eur,
                   vendor_name, explanation, cost_category
            FROM expenses
            WHERE type = 'cost'
              AND expense_date >= %s AND expense_date < %s
            ORDER BY expense_date, id
            """,
            (start, end),
        )
        return [DbRow(rec) for rec in cur.fetchall()]


# ---------------------------------------------------------------------------
# Matching
#
# Amount is the only thing that can create a match. Vendor similarity may widen
# the date window for an amount-equal pair, but never invents a match on its
# own - so a wrong alias cannot mark a real transaction as reconciled.
# ---------------------------------------------------------------------------

def amount_exact(txn, row):
    if (row.amount, row.currency) in txn.amount_keys:
        return True, Decimal('0')
    return False, None


def amount_near(txn, row):
    """Within 2% or EUR 1 - absorbs FX drift (Superhuman 91.12 vs 91.20 USD)."""
    best = None
    for amount, currency in txn.amount_keys:
        if currency != row.currency:
            continue
        delta = abs(amount - row.amount)
        if delta <= max(Decimal('1.00'), amount * Decimal('0.02')):
            best = delta if best is None else min(best, delta)
    return (True, best) if best is not None else (False, None)


def vendor_matches(txn, row):
    candidates = {txn.norm}
    if txn.alias:
        candidates.add(normalize(txn.alias))
    for candidate in candidates:
        if not candidate or not row.norm:
            continue
        if candidate == row.norm or candidate in row.norm or row.norm in candidate:
            return True
    return False


def exact_and_vendor(txn, row):
    ok, delta = amount_exact(txn, row)
    return (ok and vendor_matches(txn, row), delta)


def near_and_vendor(txn, row):
    ok, delta = amount_near(txn, row)
    return (ok and vendor_matches(txn, row), delta)


def same_day_same_vendor(txn, row):
    """Same vendor, same day, amount too far apart to be FX drift.

    Run last and only at zero date distance, so it catches a wrong amount in the
    database rather than a genuinely absent transaction - the DB has Anthropic at
    EUR 24.42 on 2025-01-05 where the card was charged EUR 21.42.
    """
    if not vendor_matches(txn, row):
        return False, None
    deltas = [abs(amount - row.amount)
              for amount, currency in txn.amount_keys if currency == row.currency]
    return (True, min(deltas)) if deltas else (False, None)


# (label, date window in days, predicate, outcome)
#
# Windows are bounded by the shortest billing cycle (28 days, February) minus the
# largest observed drift (6 days, Superhuman): beyond ~22 days a subscription
# charge can reach into an adjacent month and match the wrong one. Measured on
# 2025, exact matching at 10 days already reaches 296 of the 304 pairs achievable
# at *any* window, so widening buys nothing and risks a lot.
PASSES = (
    ('exact',       3,  amount_exact,         'matched'),
    ('near-date',   10, amount_exact,         'matched'),
    ('aliased',     14, exact_and_vendor,     'matched'),
    ('probable',    7,  near_and_vendor,      'probable'),
    ('discrepancy', 0,  same_day_same_vendor, 'discrepancy'),
)


def run_pass(txns, rows, window, predicate):
    """Best-first assignment: nearest date wins, so a far pair cannot consume a
    database row that a nearer pair needed."""
    candidates = []
    for txn in txns:
        for row in rows:
            distance = abs((row.date - txn.date).days)
            if distance > window:
                continue
            ok, delta = predicate(txn, row)
            if ok:
                candidates.append((distance, delta or Decimal('0'), txn, row))

    candidates.sort(key=lambda c: (c[0], c[1], c[2].idx, c[3].id))

    taken_txns, taken_rows, pairs = set(), set(), []
    for distance, delta, txn, row in candidates:
        if txn.idx in taken_txns or row.id in taken_rows:
            continue
        taken_txns.add(txn.idx)
        taken_rows.add(row.id)
        pairs.append((txn, row, distance, delta))
    return pairs


def reconcile(txns, rows):
    remaining_txns = list(txns)
    remaining_rows = list(rows)
    outcomes = {'matched': [], 'probable': [], 'discrepancy': []}

    for label, window, predicate, outcome in PASSES:
        pairs = run_pass(remaining_txns, remaining_rows, window, predicate)
        if not pairs:
            continue
        for txn, row, distance, delta in pairs:
            outcomes[outcome].append((txn, row, label, distance, delta))
        paired_txns = {t.idx for t, _, _, _ in pairs}
        paired_rows = {r.id for _, r, _, _ in pairs}
        remaining_txns = [t for t in remaining_txns if t.idx not in paired_txns]
        remaining_rows = [r for r in remaining_rows if r.id not in paired_rows]

    return outcomes['matched'], outcomes['probable'], outcomes['discrepancy'], remaining_txns


def dead_alias_keys(txns):
    """Alias keys no CSV merchant normalizes to - almost always a typo."""
    seen = {t.norm for t in txns}
    return sorted(k for k in VENDOR_ALIASES if k not in seen)


# ---------------------------------------------------------------------------
# Extra findings, cheap to compute while the data is loaded
# ---------------------------------------------------------------------------

def find_db_duplicates(rows, year, matched_ids):
    """Same date, amount and currency - split by whether the card backs them up.

    Two identical rows are not automatically an error: the Elgato pair on
    2025-06-24 is two devices ("für Caspar" / "für Denis") and there are two card
    charges to prove it. What indicts a row is having no card charge of its own
    while its twin does.
    """
    groups = defaultdict(list)
    for row in rows:
        if row.date.year == year:
            groups[(row.date, row.amount, row.currency)].append(row)

    confirmed, unbacked = [], []
    for key, group in sorted(groups.items(), key=lambda item: item[0][0]):
        if len(group) < 2:
            continue
        backed = [r for r in group if r.id in matched_ids]
        spare = [r for r in group if r.id not in matched_ids]
        if backed and spare:
            confirmed.append((key, backed, spare))
        elif not backed:
            unbacked.append((key, group))
        # all backed: one card charge each, so genuinely separate purchases
    return confirmed, unbacked


def diagnose(txn, leftover):
    """Nearest unclaimed database row and why it did not match.

    Without this every missing row is a research project; with it most resolve
    at a glance.
    """
    # Wider than any matching window on purpose: this only ever explains, never
    # pairs, so it can safely reach the previous month to surface "a duplicate
    # absorbed this slot".
    near = [r for r in leftover if abs((r.date - txn.date).days) <= 40]
    by_vendor = [r for r in near if vendor_matches(txn, r)]
    if by_vendor:
        row = min(by_vendor, key=lambda r: abs((r.date - txn.date).days))
        gap = abs((row.date - txn.date).days)
        deltas = [abs(a - row.amount) for a, c in txn.amount_keys if c == row.currency]
        if deltas and min(deltas) == 0:
            return row, f'same vendor and amount, but {gap}d away'
        if deltas:
            return row, f'same vendor, amount differs by {min(deltas)} {row.currency}'
        return row, f'same vendor, but recorded in {row.currency}'

    by_amount = [r for r in near if (r.amount, r.currency) in txn.amount_keys]
    if by_amount:
        row = min(by_amount, key=lambda r: abs((r.date - txn.date).days))
        gap = abs((row.date - txn.date).days)
        return row, f'same amount {gap}d away, but an unrelated vendor'

    return None, 'nothing comparable in the database'


def vendor_is_tracked(txn, rows):
    """Does this merchant appear in the database at all, under any amount?"""
    return any(vendor_matches(txn, row) for row in rows)


def find_fixable_eur(matched, year):
    """Database rows with no EUR value where the CSV supplies the historical one."""
    out = []
    for txn, row, _, _, _ in matched:
        if row.amount_eur is None and row.date.year == year and txn.amount_eur is not None:
            out.append((row, txn))
    return sorted(out, key=lambda item: item[0].date)


def suggest_aliases(missing, rows):
    """Similarity hits for unmatched merchants. Proposals only - see VENDOR_ALIASES."""
    known = {}
    for row in rows:
        if row.norm:
            known.setdefault(row.norm, row.vendor_name or row.explanation)

    seen, out = set(), []
    for txn in missing:
        if txn.norm in seen or txn.alias or not txn.norm:
            continue
        seen.add(txn.norm)
        hit = next((v for k, v in known.items() if txn.norm in k or k in txn.norm), None)
        how = 'substring'
        if not hit:
            close = difflib.get_close_matches(txn.norm, list(known), n=1, cutoff=0.6)
            hit, how = (known[close[0]], 'fuzzy') if close else (None, None)
        if hit:
            out.append((txn.merchant, hit, how))
    return sorted(out)


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def eur_total(txns):
    return sum((t.amount_eur for t in txns if t.amount_eur is not None), Decimal('0'))


def total_label(txns):
    """EUR total, or the original amounts when Wise billed in another currency."""
    if any(t.amount_eur is not None for t in txns):
        return f'EUR {eur_total(txns):,.2f}'
    parts = defaultdict(Decimal)
    for txn in txns:
        parts[txn.src_currency] += txn.src_amount
    body = ' + '.join(f'{cur} {amount:,.2f}' for cur, amount in sorted(parts.items()))
    return f'{body} (no EUR figure in the CSV)'


def group_by_merchant(txns):
    groups = defaultdict(list)
    for txn in txns:
        groups[txn.merchant].append(txn)
    return sorted(groups.items(), key=lambda kv: (-eur_total(kv[1]), kv[0]))


def write_missing_csv(path, missing, leftover, rows):
    ordered = sorted(missing, key=lambda t: (t.is_personal, -t.sort_amount(), t.date))
    with open(path, 'w', newline='', encoding='utf-8') as handle:
        writer = csv.writer(handle)
        writer.writerow([
            'date', 'merchant', 'amount_eur', 'amount_original', 'currency',
            'exchange_rate', 'wise_category', 'likely_personal',
            'suggested_cost_category', 'vendor_tracked', 'why_not_matched',
            'nearest_db_id', 'nearest_db_date', 'nearest_db_vendor', 'wise_id',
        ])
        for txn in ordered:
            row, reason = diagnose(txn, leftover)
            writer.writerow([
                txn.date.isoformat(),
                txn.merchant,
                txn.amount_eur if txn.amount_eur is not None else '',
                txn.tgt_amount if txn.tgt_amount is not None else txn.src_amount,
                txn.tgt_currency or txn.src_currency,
                txn.exchange_rate,
                txn.wise_category,
                'yes' if txn.is_personal else 'no',
                txn.suggested_cost_category,
                'yes' if vendor_is_tracked(txn, rows) else 'no',
                reason,
                row.id if row else '',
                row.date.isoformat() if row else '',
                row.vendor_name if row else '',
                txn.wise_id,
            ])


def _csv_amounts(txn):
    """Both sides of the transaction, since either may be what the DB stored."""
    source = f'{txn.src_amount} {txn.src_currency}'
    if txn.tgt_amount is None or txn.tgt_currency == txn.src_currency:
        return source
    return f'{source} → {txn.tgt_amount} {txn.tgt_currency}'


def write_markdown(path, year, csv_path, txns, matched, probable, discrepancies,
                   missing, leftover, rows, dupes, fixable, alias_hints):
    business = [t for t in missing if not t.is_personal]
    personal = [t for t in missing if t.is_personal]
    out = []
    add = out.append

    add(f'# Reconciliation {year} — Wise card vs expenses database\n')
    add(f'Source: `{csv_path}`\n')
    add('Report only. Nothing in the database was modified.\n')

    add('## Summary\n')
    add('| | count | EUR |')
    add('|---|---:|---:|')
    add(f'| Card transactions in CSV | {len(txns)} | {eur_total(txns):,.2f} |')
    add(f'| Matched to a database row | {len(matched)} | '
        f'{eur_total([t for t, *_ in matched]):,.2f} |')
    add(f'| Probable match (verify) | {len(probable)} | '
        f'{eur_total([t for t, *_ in probable]):,.2f} |')
    add(f'| Amount discrepancy | {len(discrepancies)} | '
        f'{eur_total([t for t, *_ in discrepancies]):,.2f} |')
    add(f'| **Missing — business** | **{len(business)}** | **{eur_total(business):,.2f}** |')
    add(f'| Missing — likely personal | {len(personal)} | {eur_total(personal):,.2f} |')
    add('')
    add('The database legitimately holds more 2025 cost rows than the CSV — it also '
        'covers bank transfers and freelancer invoices that never touched the card. '
        'This check runs one direction only: CSV → database.\n')

    untracked = [t for t in business if not vendor_is_tracked(t, rows)]
    gaps = [t for t in business if vendor_is_tracked(t, rows)]

    def merchant_tables(group_list):
        for merchant, group in group_by_merchant(group_list):
            charges = 'charge' if len(group) == 1 else 'charges'
            add(f'### {merchant} — {len(group)} {charges}, {total_label(group)}\n')
            add('| date | amount | wise category | nearest database row |')
            add('|---|---:|---|---|')
            for txn in sorted(group, key=lambda t: t.date):
                amount = (f'{txn.tgt_amount} {txn.tgt_currency}'
                          if txn.tgt_amount is not None else
                          f'{txn.src_amount} {txn.src_currency}')
                row, reason = diagnose(txn, leftover)
                note = f'`{row.id}` {row.date} — {reason}' if row else reason
                add(f'| {txn.date} | {amount} | {txn.wise_category} | {note} |')
            add('')

    add('## Missing — vendor never appears in the database\n')
    if untracked:
        add(f'{len(untracked)} charges, {total_label(untracked)}. '
            'Near-certain data-entry gaps — the action is simply to add them.\n')
        merchant_tables(untracked)
    else:
        add('None.\n')

    add('## Missing — vendor is tracked, but this charge is not\n')
    if gaps:
        add(f'{len(gaps)} charges, {total_label(gaps)}. '
            'A different problem: you already record this vendor, so a date or '
            'amount discrepancy — or a duplicate absorbing the slot — is more '
            'likely than a genuine omission. Check the nearest row before adding.\n')
        merchant_tables(gaps)
    else:
        add('None.\n')

    add('## Missing — likely personal\n')
    if personal:
        add('Heuristic: Wise category plus a merchant keyword list. Check before discarding.\n')
        add('| merchant | count | total |')
        add('|---|---:|---:|')
        for merchant, group in group_by_merchant(personal):
            add(f'| {merchant} | {len(group)} | {total_label(group)} |')
        add('')
    else:
        add('None.\n')

    add('## Probable matches — please verify\n')
    if probable:
        add('Amount differs slightly (FX drift). Treated as **not** confirmed.\n')
        add('| csv date | merchant | csv amount | db id | db date | db amount | db vendor |')
        add('|---|---|---|---:|---|---:|---|')
        for txn, row, _, _, _ in sorted(probable, key=lambda p: p[0].date):
            add(f'| {txn.date} | {txn.merchant} | {_csv_amounts(txn)} | {row.id} | {row.date} '
                f'| {row.amount} {row.currency} | {row.vendor_name} |')
        add('')
    else:
        add('None.\n')

    add('## Amount discrepancies\n')
    if discrepancies:
        add('Same vendor, same day, but the amounts disagree by more than FX drift. '
            'The transaction *is* in the database — one of the two figures is wrong.\n')
        add('| date | merchant | card charged | db id | db amount | db vendor |')
        add('|---|---|---|---:|---:|---|')
        for txn, row, _, _, _ in sorted(discrepancies, key=lambda p: p[0].date):
            add(f'| {txn.date} | {txn.merchant} | {_csv_amounts(txn)} | {row.id} '
                f'| {row.amount} {row.currency} | {row.vendor_name} |')
        add('')
    else:
        add('None.\n')

    add('## Suggested new aliases\n')
    if alias_hints:
        add('Automatic similarity hits for merchants reported missing. **Not applied** — '
            'similarity alone proposes wrong pairings (it suggests `Claude → CloudFlare`). '
            'Confirm by eye, then add to `VENDOR_ALIASES` in `reconcile.py` and re-run.\n')
        add('| csv merchant | possible db vendor | how |')
        add('|---|---|---|')
        for merchant, vendor, how in alias_hints:
            add(f'| {merchant} | {vendor} | {how} |')
        add('')
    else:
        add('None.\n')

    # A spare row that is also the nearest explanation for a missing charge is
    # more likely misdated than duplicated - deleting it would erase a real cost.
    cited = {}
    for txn in missing:
        row, _ = diagnose(txn, leftover)
        if row is not None:
            cited.setdefault(row.id, txn)

    confirmed_dupes, unbacked_dupes = dupes
    add('## Duplicate rows in the database\n')
    if confirmed_dupes:
        add('Identical date, amount and currency, where **only one** of the rows has a '
            'card charge behind it. The spare is double-counting a deduction.\n')
        add('| date | amount | backed by the card | spare | verdict |')
        add('|---|---:|---|---|---|')
        for (day, amount, currency), backed, spare in confirmed_dupes:
            keeps = ' · '.join(f'`{r.id}` {r.vendor_name}' for r in backed)
            drops = ' · '.join(f'`{r.id}` {r.vendor_name}' for r in spare)
            claim = next((cited[r.id] for r in spare if r.id in cited), None)
            verdict = (f'**check first** — also the nearest match for the missing '
                       f'{claim.date} charge, so it may be misdated rather than duplicated'
                       if claim else 'likely duplicate')
            add(f'| {day} | {amount} {currency} | {keeps} | {drops} | {verdict} |')
        add('')
        add('Identical pairs where *both* rows matched a card charge are excluded — '
            'those are genuinely separate purchases.\n')
    else:
        add('None.\n')

    if unbacked_dupes:
        add('### Identical pairs with no card charge either side\n')
        add('Not card spend, so this tool cannot judge them. Listed only because the '
            'shape is suspicious.\n')
        add('| date | amount | rows |')
        add('|---|---:|---|')
        for (day, amount, currency), group in unbacked_dupes:
            listing = ' · '.join(f'`{r.id}` {r.vendor_name}' for r in group)
            add(f'| {day} | {amount} {currency} | {listing} |')
        add('')

    add('## Database rows the CSV could fix\n')
    if fixable:
        add(f'{len(fixable)} matched rows have no `amount_eur`. The CSV carries the '
            'historical rate actually charged; `flask backfill-eur` would apply '
            "today's ECB rate instead, since `convert_to_eur()` takes no date.\n")
        add('| db id | date | amount | true EUR | rate | vendor |')
        add('|---:|---|---:|---:|---|---|')
        for row, txn in fixable:
            add(f'| {row.id} | {row.date} | {row.amount} {row.currency} '
                f'| {txn.amount_eur} | {txn.exchange_rate} | {row.vendor_name} |')
        add('')
    else:
        add('None.\n')

    add('---\n')
    add('Month attribution is approximate for monthly subscriptions charged at an '
        'identical amount; counts and totals are exact.\n')

    Path(path).write_text('\n'.join(out), encoding='utf-8')


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@click.command()
@click.argument('csv_path', type=click.Path(exists=True, dir_okay=False))
@click.option('--year', type=int, default=None, help='Year to reconcile (default: infer from CSV).')
@click.option('--out-dir', default='reconcile-output', help='Where to write the reports.')
@click.option('--margin-days', default=45, show_default=True,
              help='How far outside the year to look for matching database rows.')
def main(csv_path, year, out_dir, margin_days):
    """Report which Wise card transactions are missing from the expenses database."""
    year = year or infer_year(csv_path)

    txns, skipped = load_csv(csv_path, year)
    click.echo(f'CSV        {len(txns)} card transactions in {year}'
               + (f' ({skipped} rows skipped)' if skipped else ''))

    for key in dead_alias_keys(txns):
        click.echo(f'  warning: VENDOR_ALIASES key {key!r} matches no merchant '
                   f'in this CSV — check it against normalize()', err=True)

    conn = psycopg2.connect(Config.SQLALCHEMY_DATABASE_URI)
    conn.set_session(readonly=True)
    click.echo(f'Database   {Config.SQLALCHEMY_DATABASE_URI} (read-only session)')
    try:
        rows = load_db_rows(conn, year, margin_days)
    finally:
        conn.close()
    click.echo(f'           {len(rows)} cost rows in range')

    matched, probable, discrepancies, missing = reconcile(txns, rows)
    business = [t for t in missing if not t.is_personal]
    personal = [t for t in missing if t.is_personal]

    claimed = {r.id for _, r, *_ in matched + probable + discrepancies}
    leftover = [r for r in rows if r.id not in claimed]

    dupes = find_db_duplicates(rows, year, claimed)
    fixable = find_fixable_eur(matched, year)
    alias_hints = suggest_aliases(missing, rows)

    directory = Path(out_dir)
    directory.mkdir(parents=True, exist_ok=True)
    missing_csv = directory / f'missing-{year}.csv'
    report_md = directory / f'reconcile-{year}.md'
    write_missing_csv(missing_csv, missing, leftover, rows)
    write_markdown(report_md, year, csv_path, txns, matched, probable, discrepancies,
                   missing, leftover, rows, dupes, fixable, alias_hints)

    click.echo('')
    click.echo(f'  matched            {len(matched):4d}   EUR {eur_total([t for t, *_ in matched]):>10,.2f}')
    click.echo(f'  probable (verify)  {len(probable):4d}   EUR {eur_total([t for t, *_ in probable]):>10,.2f}')
    click.echo(f'  amount discrepancy {len(discrepancies):4d}   EUR {eur_total([t for t, *_ in discrepancies]):>10,.2f}')
    click.echo(f'  MISSING business   {len(business):4d}   EUR {eur_total(business):>10,.2f}')
    click.echo(f'  missing personal   {len(personal):4d}   EUR {eur_total(personal):>10,.2f}')
    click.echo('')
    click.echo(f'  {report_md}')
    click.echo(f'  {missing_csv}')


if __name__ == '__main__':
    main()
