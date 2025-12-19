# Database Schema

## Expenses Table

```sql
CREATE TABLE expenses (
    -- Primary key
    id SERIAL PRIMARY KEY,

    -- Core expense data
    amount NUMERIC(10, 2) NOT NULL,
    type VARCHAR(10) NOT NULL,  -- 'income' or 'cost'
    cost_category VARCHAR(20),  -- 'operations', 'freelancers', 'equipment', 'other' (costs only)
    currency VARCHAR(3) NOT NULL DEFAULT 'USD',
    explanation TEXT,
    tags VARCHAR[] DEFAULT '{}',

    -- Euro conversion (for German tax reporting)
    amount_eur NUMERIC(10, 2),  -- Amount converted to EUR
    exchange_rate NUMERIC(10, 6),  -- Exchange rate used (1 EUR = X currency)

    -- Source information
    source_type VARCHAR(20),  -- 'manual', 'email_text', 'pdf_upload', 'email_auto' (phase 3)
    vendor_name VARCHAR(255),
    invoice_number VARCHAR(100),

    -- Email metadata (for phase 3)
    sender_email VARCHAR(255),
    sender_domain VARCHAR(255),
    email_subject VARCHAR(500),

    -- PDF attachment
    attachment_filename VARCHAR(255),
    attachment_data BYTEA,  -- Binary PDF data
    has_attachments BOOLEAN DEFAULT FALSE,

    -- Timestamps
    expense_date DATE,  -- When the expense occurred
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for common queries
CREATE INDEX idx_expenses_type ON expenses(type);
CREATE INDEX idx_expenses_vendor ON expenses(vendor_name);
CREATE INDEX idx_expenses_created ON expenses(created_at DESC);
CREATE INDEX idx_expenses_source ON expenses(source_type);
CREATE INDEX idx_expenses_cost_category ON expenses(cost_category);
```

## Field Descriptions

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `amount` | Numeric | Expense amount in original currency | 49.99 |
| `type` | String | "income" or "cost" | "cost" |
| `cost_category` | String | Category for costs only | "operations" |
| `currency` | String | 3-letter ISO code | "USD" |
| `explanation` | Text | What the expense is for | "Monthly hosting fee" |
| `tags` | Array | Categories/labels | ["software", "hosting"] |
| `amount_eur` | Numeric | Amount converted to EUR | 45.50 |
| `exchange_rate` | Numeric | ECB rate used for conversion | 1.0987 |
| `source_type` | String | How expense was created | "manual", "email_text", "pdf_upload" |
| `vendor_name` | String | Company name | "DigitalOcean" |
| `invoice_number` | String | Invoice/bill ID | "INV-2024-001" |
| `sender_email` | String | Email sender (phase 3) | "billing@digitalocean.com" |
| `sender_domain` | String | Domain of sender | "digitalocean.com" |
| `email_subject` | String | Original subject | "Invoice #12345" |
| `attachment_filename` | String | PDF filename | "invoice.pdf" |
| `attachment_data` | Binary | PDF file content | (binary data) |
| `has_attachments` | Boolean | Has PDF? | true |
| `expense_date` | Date | When expense occurred | 2024-01-15 |
| `created_at` | Timestamp | When record created | 2024-01-15 10:45:00 |

## Euro Conversion

All expenses are converted to EUR for consistent tax reporting. This is required for German tax filings (EÜR - Einnahmenüberschussrechnung).

### Conversion Rules

1. **EUR expenses**: `amount_eur = amount`, `exchange_rate = 1.0`
2. **Other currencies**: Convert using ECB daily reference rate for the expense date
3. **Exchange rate source**: European Central Bank (ECB) daily rates
4. **Rate lookup**: Use the expense_date; if no rate available (weekend/holiday), use the most recent available rate

### ECB Rate Feed

The ECB publishes daily reference rates at:
- Daily XML: `https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml`
- Historical CSV: `https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist.zip`

### Conversion Formula

For non-EUR currencies:
```
amount_eur = amount / exchange_rate
```

Where `exchange_rate` is "1 EUR = X foreign currency" (e.g., 1 EUR = 1.0987 USD).

Example:
- Amount: $49.99 USD
- ECB rate: 1.0987 (1 EUR = 1.0987 USD)
- EUR amount: 49.99 / 1.0987 = 45.50 EUR

## Source Types

| Source Type | Description |
|-------------|-------------|
| `manual` | User entered all fields manually |
| `email_text` | User pasted email text, AI extracted data |
| `pdf_upload` | User uploaded PDF, AI extracted data |
| `email_auto` | (Phase 3) Automatically fetched via IMAP |

## Cost Categories

Categories for classifying costs (not applicable to income):

| Category | Description | Examples |
|----------|-------------|----------|
| `operations` | Recurring costs to run the business | SaaS subscriptions, hosting, domains, email services |
| `freelancers` | Payments to contractors | Developers, designers, copywriters, consultants |
| `equipment` | One-off purchases and assets | Hardware, software licenses, courses, books |
| `other` | Everything else | Miscellaneous expenses |

**Notes:**
- This field is only used when `type = 'cost'`
- For income records, this field should be NULL
- AI parsing will attempt to infer the category based on vendor and description

## Important Code Patterns

### Database URL Handling

```python
# Railway uses postgres:// but SQLAlchemy needs postgresql://
if SQLALCHEMY_DATABASE_URI.startswith('postgres://'):
    SQLALCHEMY_DATABASE_URI = SQLALCHEMY_DATABASE_URI.replace(
        'postgres://', 'postgresql://', 1
    )
```

### Stats Aggregation

Stats should use `amount_eur` for consistent totals:

```python
income = db.session.query(func.sum(Expense.amount_eur)).filter(
    Expense.type == 'income'
).scalar() or 0
```
