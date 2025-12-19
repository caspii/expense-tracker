from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Expense(db.Model):
    __tablename__ = 'expenses'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # Core expense data
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    type = db.Column(db.String(10), nullable=False)  # 'income' or 'cost'
    cost_category = db.Column(db.String(20))  # 'operations', 'freelancers', 'equipment', 'other' (costs only)
    currency = db.Column(db.String(3), nullable=False, default='USD')
    explanation = db.Column(db.Text)
    tags = db.Column(db.ARRAY(db.String), default=list)

    # Status and source
    status = db.Column(db.String(20), nullable=False, default='draft')  # 'draft' or 'confirmed'
    source_type = db.Column(db.String(20))  # 'manual', 'email_text', 'pdf_upload', 'email_auto'
    
    # Email metadata
    sender_email = db.Column(db.String(255))
    sender_domain = db.Column(db.String(255))
    vendor_name = db.Column(db.String(255))
    email_subject = db.Column(db.String(500))
    invoice_number = db.Column(db.String(100))
    payment_status = db.Column(db.String(50))
    
    # PDF attachment
    attachment_filename = db.Column(db.String(255))
    attachment_data = db.Column(db.LargeBinary)
    has_attachments = db.Column(db.Boolean, default=False)
    
    # Timestamps
    expense_date = db.Column(db.Date)  # When the expense occurred
    email_date = db.Column(db.DateTime)  # When the email was sent (Phase 3)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<Expense {self.id}: {self.type} {self.amount} {self.currency}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'amount': float(self.amount),
            'type': self.type,
            'cost_category': self.cost_category,
            'currency': self.currency,
            'explanation': self.explanation,
            'tags': self.tags or [],
            'status': self.status,
            'source_type': self.source_type,
            'sender_email': self.sender_email,
            'sender_domain': self.sender_domain,
            'vendor_name': self.vendor_name,
            'email_subject': self.email_subject,
            'invoice_number': self.invoice_number,
            'payment_status': self.payment_status,
            'has_attachments': self.has_attachments,
            'attachment_filename': self.attachment_filename,
            'expense_date': self.expense_date.isoformat() if self.expense_date else None,
            'email_date': self.email_date.isoformat() if self.email_date else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
