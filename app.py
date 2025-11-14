from flask import Flask, render_template, request, jsonify, send_file
from apscheduler.schedulers.background import BackgroundScheduler
from config import Config
from models import db, Expense
from email_parser import fetch_new_emails
from datetime import datetime
from io import BytesIO
from sqlalchemy import func

app = Flask(__name__)
app.config.from_object(Config)

# Initialize database
db.init_app(app)


def check_emails():
    """Background job to check for new emails."""
    with app.app_context():
        print(f"Checking emails at {datetime.now()}")
        expenses = fetch_new_emails()
        
        for expense_data in expenses:
            expense = Expense(**expense_data, status='draft')
            db.session.add(expense)
        
        if expenses:
            db.session.commit()
            print(f"Created {len(expenses)} draft expenses")


# Initialize scheduler
scheduler = BackgroundScheduler()
scheduler.add_job(
    func=check_emails,
    trigger='interval',
    minutes=Config.EMAIL_CHECK_INTERVAL,
    id='email_check_job',
    replace_existing=True
)


@app.route('/')
def index():
    """Main page showing drafts and stats."""
    return render_template('index.html')


@app.route('/api/expenses')
def get_expenses():
    """Get expenses with optional filtering."""
    status = request.args.get('status')
    expense_type = request.args.get('type')
    
    query = Expense.query
    
    if status:
        query = query.filter_by(status=status)
    if expense_type:
        query = query.filter_by(type=expense_type)
    
    query = query.order_by(Expense.created_at.desc())
    expenses = query.all()
    
    return jsonify([e.to_dict() for e in expenses])


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


@app.route('/api/check-emails', methods=['POST'])
def manual_email_check():
    """Manually trigger email check."""
    check_emails()
    return jsonify({'message': 'Email check triggered'})


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    
    # Start scheduler
    if not scheduler.running:
        scheduler.start()
    
    app.run(debug=True, host='0.0.0.0', port=5055)
