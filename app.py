import click
from flask import Flask, render_template, request, jsonify, send_file
# from apscheduler.schedulers.background import BackgroundScheduler  # Phase 3
from config import Config
from models import db, Expense
# from email_parser import fetch_new_emails  # Phase 3
from ai_parser import parse_text_with_claude, parse_pdf_with_claude
from currency import convert_to_eur
from export import generate_excel_report, get_export_filename
from datetime import datetime, date
from decimal import Decimal
from io import BytesIO
from sqlalchemy import func, extract, or_
from sqlalchemy.exc import IntegrityError
import base64

app = Flask(__name__)
app.config.from_object(Config)

# Initialize database
db.init_app(app)


# Blocks a submission being saved twice. A double-clicked Save fires the two
# requests milliseconds apart, so checking for an existing row before inserting
# loses the race - only the database can settle it.
#
# Keyed on the amount and date as well as the invoice, so one invoice may still
# be split across rows with different amounts; only an exact repeat is refused.
DUPLICATE_INVOICE_INDEX = '''
    CREATE UNIQUE INDEX IF NOT EXISTS expenses_no_duplicate_invoice
    ON expenses (vendor_name, invoice_number, amount, expense_date)
    WHERE invoice_number IS NOT NULL
      AND invoice_number <> ''
      AND vendor_name IS NOT NULL
'''


# CLI Commands
@app.cli.command('reset-db')
@click.option('--yes', is_flag=True, help='Skip confirmation prompt')
def reset_db(yes):
    """Drop all tables and recreate them."""
    if not yes:
        click.confirm('This will delete all data. Are you sure?', abort=True)
    db.drop_all()
    db.create_all()
    click.echo('Database reset successfully.')


@app.cli.command('init-db')
def init_db():
    """Create all tables (without dropping existing ones)."""
    db.create_all()
    click.echo('Database initialized.')


@app.cli.command('migrate-db')
def migrate_db():
    """Add missing columns and indexes to existing tables."""
    db.session.execute(db.text('''
        ALTER TABLE expenses
        ADD COLUMN IF NOT EXISTS cost_category VARCHAR(20),
        ADD COLUMN IF NOT EXISTS source_type VARCHAR(20),
        ADD COLUMN IF NOT EXISTS expense_date DATE,
        ADD COLUMN IF NOT EXISTS amount_eur NUMERIC(10, 2),
        ADD COLUMN IF NOT EXISTS exchange_rate NUMERIC(10, 6),
        ADD COLUMN IF NOT EXISTS external_id VARCHAR(100)
    '''))
    db.session.execute(db.text(DUPLICATE_INVOICE_INDEX))
    db.session.execute(db.text('''
        CREATE UNIQUE INDEX IF NOT EXISTS expenses_external_id_key
        ON expenses (external_id) WHERE external_id IS NOT NULL
    '''))
    db.session.commit()
    click.echo('Database migrated successfully.')


@app.cli.command('backfill-eur')
def backfill_eur():
    """Backfill EUR conversion for existing expenses."""
    expenses = Expense.query.filter(Expense.amount_eur == None).all()
    count = 0
    for expense in expenses:
        amount = Decimal(str(expense.amount))
        amount_eur, exchange_rate = convert_to_eur(amount, expense.currency)
        expense.amount_eur = amount_eur
        expense.exchange_rate = exchange_rate
        count += 1
    db.session.commit()
    click.echo(f'Updated {count} expenses with EUR conversion.')


# Phase 3: Email automation (commented out for now)
# def check_emails():
#     """Background job to check for new emails."""
#     with app.app_context():
#         print(f"Checking emails at {datetime.now()}")
#         expenses = fetch_new_emails()
#
#         for expense_data in expenses:
#             expense = Expense(**expense_data)
#             db.session.add(expense)
#
#         if expenses:
#             db.session.commit()
#             print(f"Created {len(expenses)} expenses")
#
#
# # Initialize scheduler
# scheduler = BackgroundScheduler()
# scheduler.add_job(
#     func=check_emails,
#     trigger='interval',
#     minutes=Config.EMAIL_CHECK_INTERVAL,
#     id='email_check_job',
#     replace_existing=True
# )


def requested_year():
    """The year to display, defaulting to the current one. 'all' disables filtering."""
    return request.args.get('year', str(datetime.now().year))


def year_filter(year):
    """Restrict to one year, or None for no restriction.

    Expenses with no date are included in every specific year, so they stay
    visible instead of being reachable only through 'all'.
    """
    if year == 'all':
        return None
    return or_(
        extract('year', Expense.expense_date) == int(year),
        Expense.expense_date == None
    )


@app.route('/')
def index():
    """Main page showing expenses and stats."""
    return render_template('index.html')


@app.route('/api/expenses', methods=['GET', 'POST'])
def expenses_list():
    """Get expenses with optional filtering, or create a new expense."""
    if request.method == 'GET':
        expense_type = request.args.get('type')
        cost_category = request.args.get('cost_category')

        query = Expense.query

        selected = year_filter(requested_year())
        if selected is not None:
            query = query.filter(selected)

        if expense_type:
            query = query.filter_by(type=expense_type)
        if cost_category:
            query = query.filter_by(cost_category=cost_category)

        query = query.order_by(Expense.created_at.desc())
        expenses = query.all()

        return jsonify([e.to_dict() for e in expenses])

    elif request.method == 'POST':
        data = request.json

        # Parse expense_date if provided, default to today
        expense_date = date.today()
        if data.get('expense_date'):
            try:
                expense_date = date.fromisoformat(data['expense_date'])
            except ValueError:
                pass

        # Handle attachment data (base64 encoded)
        attachment_data = None
        attachment_filename = None
        has_attachments = False
        if data.get('attachment_data'):
            try:
                attachment_data = base64.b64decode(data['attachment_data'])
                attachment_filename = data.get('attachment_filename', 'attachment.pdf')
                has_attachments = True
            except Exception:
                pass

        # Get amount and currency for EUR conversion
        amount = Decimal(str(data.get('amount', 0)))
        currency = data.get('currency', 'USD')

        # Convert to EUR
        amount_eur, exchange_rate = convert_to_eur(amount, currency)

        expense = Expense(
            amount=amount,
            type=data.get('type', 'cost'),
            cost_category=data.get('cost_category'),
            currency=currency,
            explanation=data.get('explanation'),
            tags=data.get('tags', []),
            amount_eur=amount_eur,
            exchange_rate=exchange_rate,
            source_type=data.get('source_type', 'manual'),
            vendor_name=data.get('vendor_name'),
            invoice_number=data.get('invoice_number'),
            expense_date=expense_date,
            attachment_data=attachment_data,
            attachment_filename=attachment_filename,
            has_attachments=has_attachments,
        )

        db.session.add(expense)
        try:
            db.session.commit()
        except IntegrityError:
            # The duplicate-invoice index rejected this. Report the existing row
            # rather than a 500, so a double-click reads as "already saved".
            db.session.rollback()
            existing = Expense.query.filter_by(
                vendor_name=expense.vendor_name,
                invoice_number=expense.invoice_number,
                amount=expense.amount,
                expense_date=expense.expense_date,
            ).first()
            return jsonify({
                'error': f'Invoice {expense.invoice_number} from '
                         f'{expense.vendor_name} is already recorded for this '
                         f'amount and date.',
                'existing_id': existing.id if existing else None,
            }), 409

        return jsonify(expense.to_dict()), 201


@app.route('/api/expenses/<int:expense_id>', methods=['GET', 'PUT', 'DELETE'])
def expense_detail(expense_id):
    """Get, update, or delete a specific expense."""
    expense = Expense.query.get_or_404(expense_id)

    if request.method == 'GET':
        return jsonify(expense.to_dict())

    elif request.method == 'PUT':
        data = request.json

        # Track if we need to recalculate EUR conversion
        recalculate_eur = False

        # Update fields
        if 'amount' in data:
            expense.amount = data['amount']
            recalculate_eur = True
        if 'type' in data:
            expense.type = data['type']
        if 'cost_category' in data:
            expense.cost_category = data['cost_category']
        if 'currency' in data:
            expense.currency = data['currency']
            recalculate_eur = True
        if 'explanation' in data:
            expense.explanation = data['explanation']
        if 'tags' in data:
            expense.tags = data['tags']
        if 'vendor_name' in data:
            expense.vendor_name = data['vendor_name']
        if 'invoice_number' in data:
            expense.invoice_number = data['invoice_number']
        if 'expense_date' in data:
            if data['expense_date']:
                try:
                    expense.expense_date = date.fromisoformat(data['expense_date'])
                except ValueError:
                    pass
            else:
                expense.expense_date = None

        # Recalculate EUR conversion if amount or currency changed
        if recalculate_eur:
            amount = Decimal(str(expense.amount))
            amount_eur, exchange_rate = convert_to_eur(amount, expense.currency)
            expense.amount_eur = amount_eur
            expense.exchange_rate = exchange_rate

        try:
            db.session.commit()
        except IntegrityError:
            # Editing a row onto another one's invoice, amount and date hits the
            # same index as a duplicate insert. Report it rather than a 500.
            db.session.rollback()
            return jsonify({
                'error': 'Another expense already records this invoice for the '
                         'same vendor, amount and date.'
            }), 409

        return jsonify(expense.to_dict())

    elif request.method == 'DELETE':
        db.session.delete(expense)
        db.session.commit()
        return '', 204


@app.route('/api/expenses/<int:expense_id>/pdf')
def download_pdf(expense_id):
    """Download PDF attachment."""
    expense = Expense.query.get_or_404(expense_id)

    if not expense.attachment_data:
        return jsonify({'error': 'No attachment'}), 404

    return send_file(
        BytesIO(expense.attachment_data),
        mimetype='application/pdf',
        as_attachment=True,
        download_name=expense.attachment_filename
    )


@app.route('/api/parse-text', methods=['POST'])
def parse_text():
    """Parse text with Claude AI to extract expense data."""
    data = request.json

    if not data or not data.get('text'):
        return jsonify({'success': False, 'error': 'No text provided'}), 400

    text = data.get('text', '')

    result = parse_text_with_claude(text)

    if 'error' in result:
        return jsonify({'success': False, 'error': result['error']}), 400

    return jsonify({'success': True, 'data': result})


@app.route('/api/parse-pdf', methods=['POST'])
def parse_pdf():
    """Parse uploaded PDF with Claude AI to extract expense data."""
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file provided'}), 400

    file = request.files['file']

    if file.filename == '':
        return jsonify({'success': False, 'error': 'No file selected'}), 400

    if not file.filename.lower().endswith('.pdf'):
        return jsonify({'success': False, 'error': 'File must be a PDF'}), 400

    try:
        pdf_data = file.read()
        filename = file.filename

        result = parse_pdf_with_claude(pdf_data, filename)

        if 'error' in result:
            return jsonify({'success': False, 'error': result['error']}), 400

        # Include base64 encoded PDF data for storage
        return jsonify({
            'success': True,
            'data': result,
            'filename': filename,
            'file_data': base64.b64encode(pdf_data).decode('utf-8')
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/years')
def get_years():
    """Years that actually have expenses, newest first, for the year picker."""
    rows = db.session.query(
        extract('year', Expense.expense_date)
    ).filter(Expense.expense_date != None).distinct().all()

    years = sorted({int(row[0]) for row in rows}, reverse=True)
    return jsonify({'years': years, 'current': datetime.now().year})


@app.route('/api/stats')
def get_stats():
    """Get expense statistics in EUR for the selected year."""
    year = requested_year()
    selected = year_filter(year)
    # 'all' has no filter; use a no-op so the queries below read the same either way.
    conditions = [] if selected is None else [selected]

    # Total income and costs (using EUR amounts for consistency)
    income = db.session.query(func.sum(Expense.amount_eur)).filter(
        Expense.type == 'income',
        *conditions
    ).scalar() or 0

    costs = db.session.query(func.sum(Expense.amount_eur)).filter(
        Expense.type == 'cost',
        *conditions
    ).scalar() or 0

    # Count by type
    income_count = Expense.query.filter(
        Expense.type == 'income',
        *conditions
    ).count()
    cost_count = Expense.query.filter(
        Expense.type == 'cost',
        *conditions
    ).count()

    # By vendor (using EUR amounts)
    vendor_stats = db.session.query(
        Expense.vendor_name,
        func.sum(Expense.amount_eur).label('total'),
        func.count(Expense.id).label('count')
    ).filter(
        Expense.type == 'cost',
        Expense.vendor_name != None,
        *conditions
    ).group_by(
        Expense.vendor_name
    ).order_by(
        func.sum(Expense.amount_eur).desc()
    ).limit(10).all()

    return jsonify({
        'year': 'All years' if year == 'all' else int(year),
        'total_income': float(income),
        'total_costs': float(costs),
        'net': float(income - costs),
        'income_count': income_count,
        'cost_count': cost_count,
        'top_vendors': [
            {'name': v[0], 'total': float(v[1]) if v[1] else 0, 'count': v[2]}
            for v in vendor_stats
        ]
    })


@app.route('/api/monthly-summary')
def get_monthly_summary():
    """Get monthly expense totals grouped by category, plus income and net."""
    # Query costs grouped by year, month, and category
    cost_results = db.session.query(
        extract('year', Expense.expense_date).label('year'),
        extract('month', Expense.expense_date).label('month'),
        Expense.cost_category,
        func.sum(Expense.amount_eur).label('total')
    ).filter(
        Expense.type == 'cost',
        Expense.expense_date != None
    ).group_by(
        extract('year', Expense.expense_date),
        extract('month', Expense.expense_date),
        Expense.cost_category
    ).all()

    # Query income grouped by year, month
    income_results = db.session.query(
        extract('year', Expense.expense_date).label('year'),
        extract('month', Expense.expense_date).label('month'),
        func.sum(Expense.amount_eur).label('total')
    ).filter(
        Expense.type == 'income',
        Expense.expense_date != None
    ).group_by(
        extract('year', Expense.expense_date),
        extract('month', Expense.expense_date)
    ).all()

    # Organize results by month
    months_dict = {}

    # Process costs
    for row in cost_results:
        year, month = int(row.year), int(row.month)
        key = (year, month)
        if key not in months_dict:
            months_dict[key] = {
                'year': year,
                'month': month,
                'income': 0,
                'categories': {
                    'operations': 0,
                    'freelancers': 0,
                    'equipment': 0,
                    'other': 0,
                    'uncategorized': 0
                }
            }
        category = row.cost_category if row.cost_category else 'uncategorized'
        if category in months_dict[key]['categories']:
            months_dict[key]['categories'][category] = float(row.total) if row.total else 0
        else:
            months_dict[key]['categories']['uncategorized'] += float(row.total) if row.total else 0

    # Process income
    for row in income_results:
        year, month = int(row.year), int(row.month)
        key = (year, month)
        if key not in months_dict:
            months_dict[key] = {
                'year': year,
                'month': month,
                'income': 0,
                'categories': {
                    'operations': 0,
                    'freelancers': 0,
                    'equipment': 0,
                    'other': 0,
                    'uncategorized': 0
                }
            }
        months_dict[key]['income'] = float(row.total) if row.total else 0

    # Convert to list and add labels/totals/net
    month_names = ['', 'January', 'February', 'March', 'April', 'May', 'June',
                   'July', 'August', 'September', 'October', 'November', 'December']
    months = []
    for key in sorted(months_dict.keys(), reverse=True):
        data = months_dict[key]
        data['label'] = f"{month_names[data['month']]} {data['year']}"
        data['total_costs'] = sum(data['categories'].values())
        data['net'] = data['income'] - data['total_costs']
        months.append(data)

    return jsonify({'months': months})


@app.route('/monthly')
def monthly_view_redirect():
    """Redirect old monthly URL to summary."""
    from flask import redirect
    return redirect('/summary')


@app.route('/summary')
def summary_view():
    """Render the summary page."""
    return render_template('summary.html')


@app.route('/api/yearly-summary')
def get_yearly_summary():
    """Get yearly expense totals grouped by category, plus income and net."""
    # Query costs grouped by year and category
    cost_results = db.session.query(
        extract('year', Expense.expense_date).label('year'),
        Expense.cost_category,
        func.sum(Expense.amount_eur).label('total')
    ).filter(
        Expense.type == 'cost',
        Expense.expense_date != None
    ).group_by(
        extract('year', Expense.expense_date),
        Expense.cost_category
    ).all()

    # Query income grouped by year
    income_results = db.session.query(
        extract('year', Expense.expense_date).label('year'),
        func.sum(Expense.amount_eur).label('total')
    ).filter(
        Expense.type == 'income',
        Expense.expense_date != None
    ).group_by(
        extract('year', Expense.expense_date)
    ).all()

    # Organize results by year
    years_dict = {}

    # Process costs
    for row in cost_results:
        year = int(row.year)
        if year not in years_dict:
            years_dict[year] = {
                'year': year,
                'income': 0,
                'categories': {
                    'operations': 0,
                    'freelancers': 0,
                    'equipment': 0,
                    'other': 0,
                    'uncategorized': 0
                }
            }
        category = row.cost_category if row.cost_category else 'uncategorized'
        if category in years_dict[year]['categories']:
            years_dict[year]['categories'][category] = float(row.total) if row.total else 0
        else:
            years_dict[year]['categories']['uncategorized'] += float(row.total) if row.total else 0

    # Process income
    for row in income_results:
        year = int(row.year)
        if year not in years_dict:
            years_dict[year] = {
                'year': year,
                'income': 0,
                'categories': {
                    'operations': 0,
                    'freelancers': 0,
                    'equipment': 0,
                    'other': 0,
                    'uncategorized': 0
                }
            }
        years_dict[year]['income'] = float(row.total) if row.total else 0

    # Convert to list and add labels/totals/net
    years = []
    for year in sorted(years_dict.keys(), reverse=True):
        data = years_dict[year]
        data['label'] = str(year)
        data['total_costs'] = sum(data['categories'].values())
        data['net'] = data['income'] - data['total_costs']
        years.append(data)

    return jsonify({'years': years})


@app.route('/api/export')
def export_expenses():
    """Export the selected year's expenses to an Excel file."""
    year = requested_year()

    query = Expense.query
    selected = year_filter(year)
    if selected is not None:
        query = query.filter(selected)
    expenses = query.order_by(Expense.expense_date.desc()).all()

    excel_file = generate_excel_report(expenses, year)
    filename = get_export_filename(year)

    return send_file(
        excel_file,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=filename
    )


# Phase 3: Manual email check endpoint (commented out for now)
# @app.route('/api/check-emails', methods=['POST'])
# def manual_email_check():
#     """Manually trigger email check."""
#     check_emails()
#     return jsonify({'message': 'Email check triggered'})


if __name__ == '__main__':
    with app.app_context():
        db.create_all()

    # Phase 3: Start scheduler (commented out for now)
    # if not scheduler.running:
    #     scheduler.start()

    app.run(debug=True, host='0.0.0.0', port=5055)
