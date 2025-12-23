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
from sqlalchemy import func
import base64

app = Flask(__name__)
app.config.from_object(Config)

# Initialize database
db.init_app(app)


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
    """Add missing columns to existing tables."""
    db.session.execute(db.text('''
        ALTER TABLE expenses
        ADD COLUMN IF NOT EXISTS cost_category VARCHAR(20),
        ADD COLUMN IF NOT EXISTS source_type VARCHAR(20),
        ADD COLUMN IF NOT EXISTS expense_date DATE,
        ADD COLUMN IF NOT EXISTS amount_eur NUMERIC(10, 2),
        ADD COLUMN IF NOT EXISTS exchange_rate NUMERIC(10, 6)
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

        if expense_type:
            query = query.filter_by(type=expense_type)
        if cost_category:
            query = query.filter_by(cost_category=cost_category)

        query = query.order_by(Expense.created_at.desc())
        expenses = query.all()

        return jsonify([e.to_dict() for e in expenses])

    elif request.method == 'POST':
        data = request.json

        # Parse expense_date if provided
        expense_date = None
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
        db.session.commit()

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

        db.session.commit()
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


@app.route('/api/stats')
def get_stats():
    """Get expense statistics in EUR."""
    # Total income and costs (using EUR amounts for consistency)
    income = db.session.query(func.sum(Expense.amount_eur)).filter(
        Expense.type == 'income'
    ).scalar() or 0

    costs = db.session.query(func.sum(Expense.amount_eur)).filter(
        Expense.type == 'cost'
    ).scalar() or 0

    # Count by type
    income_count = Expense.query.filter_by(type='income').count()
    cost_count = Expense.query.filter_by(type='cost').count()

    # By vendor (using EUR amounts)
    vendor_stats = db.session.query(
        Expense.vendor_name,
        func.sum(Expense.amount_eur).label('total'),
        func.count(Expense.id).label('count')
    ).filter(
        Expense.type == 'cost',
        Expense.vendor_name != None
    ).group_by(
        Expense.vendor_name
    ).order_by(
        func.sum(Expense.amount_eur).desc()
    ).limit(10).all()

    return jsonify({
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


@app.route('/api/export')
def export_expenses():
    """Export all expenses to Excel file."""
    expenses = Expense.query.order_by(Expense.expense_date.desc()).all()

    excel_file = generate_excel_report(expenses)
    filename = get_export_filename()

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
