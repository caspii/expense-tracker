import click
from flask import Flask, render_template, request, jsonify, send_file
# from apscheduler.schedulers.background import BackgroundScheduler  # Phase 3
from config import Config
from models import db, Expense
# from email_parser import fetch_new_emails  # Phase 3
from ai_parser import parse_text_with_claude, parse_pdf_with_claude
from datetime import datetime, date
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
        ADD COLUMN IF NOT EXISTS expense_date DATE
    '''))
    db.session.commit()
    click.echo('Database migrated successfully.')


# Phase 3: Email automation (commented out for now)
# def check_emails():
#     """Background job to check for new emails."""
#     with app.app_context():
#         print(f"Checking emails at {datetime.now()}")
#         expenses = fetch_new_emails()
#
#         for expense_data in expenses:
#             expense = Expense(**expense_data, status='draft')
#             db.session.add(expense)
#
#         if expenses:
#             db.session.commit()
#             print(f"Created {len(expenses)} draft expenses")
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
    """Main page showing drafts and stats."""
    return render_template('index.html')


@app.route('/api/expenses', methods=['GET', 'POST'])
def expenses_list():
    """Get expenses with optional filtering, or create a new expense."""
    if request.method == 'GET':
        status = request.args.get('status')
        expense_type = request.args.get('type')
        cost_category = request.args.get('cost_category')

        query = Expense.query

        if status:
            query = query.filter_by(status=status)
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

        expense = Expense(
            amount=data.get('amount', 0),
            type=data.get('type', 'cost'),
            cost_category=data.get('cost_category'),
            currency=data.get('currency', 'USD'),
            explanation=data.get('explanation'),
            tags=data.get('tags', []),
            status='draft',
            source_type=data.get('source_type', 'manual'),
            vendor_name=data.get('vendor_name'),
            invoice_number=data.get('invoice_number'),
            payment_status=data.get('payment_status'),
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

        # Update fields
        if 'amount' in data:
            expense.amount = data['amount']
        if 'type' in data:
            expense.type = data['type']
        if 'cost_category' in data:
            expense.cost_category = data['cost_category']
        if 'currency' in data:
            expense.currency = data['currency']
        if 'explanation' in data:
            expense.explanation = data['explanation']
        if 'tags' in data:
            expense.tags = data['tags']
        if 'status' in data:
            expense.status = data['status']
        if 'vendor_name' in data:
            expense.vendor_name = data['vendor_name']
        if 'invoice_number' in data:
            expense.invoice_number = data['invoice_number']
        if 'payment_status' in data:
            expense.payment_status = data['payment_status']
        if 'expense_date' in data:
            if data['expense_date']:
                try:
                    expense.expense_date = date.fromisoformat(data['expense_date'])
                except ValueError:
                    pass
            else:
                expense.expense_date = None

        db.session.commit()
        return jsonify(expense.to_dict())
    
    elif request.method == 'DELETE':
        db.session.delete(expense)
        db.session.commit()
        return '', 204


@app.route('/api/expenses/<int:expense_id>/confirm', methods=['POST'])
def confirm_expense(expense_id):
    """Confirm a draft expense."""
    expense = Expense.query.get_or_404(expense_id)
    expense.status = 'confirmed'
    db.session.commit()
    return jsonify(expense.to_dict())


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
    subject = data.get('subject', '')

    result = parse_text_with_claude(text, subject)

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
    """Get expense statistics."""
    confirmed_expenses = Expense.query.filter_by(status='confirmed')
    
    # Total income and costs
    income = db.session.query(func.sum(Expense.amount)).filter(
        Expense.type == 'income',
        Expense.status == 'confirmed'
    ).scalar() or 0
    
    costs = db.session.query(func.sum(Expense.amount)).filter(
        Expense.type == 'cost',
        Expense.status == 'confirmed'
    ).scalar() or 0
    
    # Count by type
    income_count = confirmed_expenses.filter_by(type='income').count()
    cost_count = confirmed_expenses.filter_by(type='cost').count()
    
    # Draft count
    draft_count = Expense.query.filter_by(status='draft').count()
    
    # By vendor
    vendor_stats = db.session.query(
        Expense.vendor_name,
        func.sum(Expense.amount).label('total'),
        func.count(Expense.id).label('count')
    ).filter(
        Expense.status == 'confirmed',
        Expense.type == 'cost',
        Expense.vendor_name != None
    ).group_by(
        Expense.vendor_name
    ).order_by(
        func.sum(Expense.amount).desc()
    ).limit(10).all()
    
    return jsonify({
        'total_income': float(income),
        'total_costs': float(costs),
        'net': float(income - costs),
        'income_count': income_count,
        'cost_count': cost_count,
        'draft_count': draft_count,
        'top_vendors': [
            {'name': v[0], 'total': float(v[1]), 'count': v[2]}
            for v in vendor_stats
        ]
    })


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
