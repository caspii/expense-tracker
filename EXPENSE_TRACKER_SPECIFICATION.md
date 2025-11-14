# Expense Tracker - Complete Specification

## 1. Project Overview

### Motivation
As a business owner, tracking expenses is critical but tedious. Most expenses arrive via email (invoices, bills, receipts), and manually entering each one into a spreadsheet or accounting system is time-consuming and error-prone. This app automates the process by:

- **Parsing emails automatically** - Forward expense emails to a dedicated address and they're processed
- **Using AI for extraction** - Claude API extracts structured data from unstructured email text
- **Draft review workflow** - Review and correct AI-extracted data before confirming
- **Simple interface** - Clean web UI focused on the essentials
- **Minimal maintenance** - Serverless-style hosting requires zero server management

### Goals
1. **Simplicity** - Easy to set up, easy to use, minimal features
2. **Automation** - Reduce manual data entry to near zero
3. **Reliability** - Store data safely in Postgres, keep PDF attachments
4. **Low cost** - Under $10/month total operating cost
5. **Personal use** - Single user, no authentication needed

### Non-Goals
- Multi-user support or authentication
- Complex accounting features (depreciation, accrual, etc.)
- Integration with accounting software
- Mobile apps (web UI works on mobile)
- Real-time processing (15-minute polling is fine)

---

## 2. System Architecture

### High-Level Components

```
┌─────────────────┐
│   Email Server  │ (Gmail IMAP)
│  (Forward here) │
└────────┬────────┘
         │
         │ Poll every 15 min
         │
┌────────▼────────┐
│  Flask App      │
│  - Web UI       │
│  - REST API     │
│  - Scheduler    │
└────────┬────────┘
         │
         ├─────► PostgreSQL (Expenses + PDFs)
         │
         └─────► Claude API (Parse emails)
```

### Technology Stack

**Backend:**
- Python 3.11+
- Flask 3.0 - Web framework
- SQLAlchemy - ORM
- Psycopg2 - Postgres driver
- APScheduler - Background jobs

**AI:**
- Anthropic Claude API (Sonnet 4)

**Database:**
- PostgreSQL 15+ (managed via Railway)

**Hosting:**
- Railway.app (recommended)
- Alternatives: Render, Fly.io, DigitalOcean

**Email:**
- IMAP protocol
- Gmail (other providers work too)

### Why These Choices?

**Flask** - Simple, lightweight, perfect for single-purpose apps
**Railway** - Zero DevOps, includes Postgres, auto-deploys from Git
**IMAP** - Universal email protocol, works with any provider
**Claude API** - Best-in-class extraction from unstructured text
**Postgres bytea** - Simplest PDF storage (no separate object storage needed)

---

## 3. Database Schema

### Expenses Table

```sql
CREATE TABLE expenses (
    -- Primary key
    id SERIAL PRIMARY KEY,
    
    -- Core expense data
    amount NUMERIC(10, 2) NOT NULL,
    type VARCHAR(10) NOT NULL,  -- 'income' or 'cost'
    currency VARCHAR(3) NOT NULL DEFAULT 'USD',
    explanation TEXT,
    tags VARCHAR[] DEFAULT '{}',
    
    -- Workflow
    status VARCHAR(20) NOT NULL DEFAULT 'draft',  -- 'draft' or 'confirmed'
    
    -- Email metadata
    sender_email VARCHAR(255),
    sender_domain VARCHAR(255),
    vendor_name VARCHAR(255),
    email_subject VARCHAR(500),
    invoice_number VARCHAR(100),
    payment_status VARCHAR(50),  -- 'paid', 'unpaid', 'pending', NULL
    
    -- PDF attachment
    attachment_filename VARCHAR(255),
    attachment_data BYTEA,  -- Binary PDF data
    has_attachments BOOLEAN DEFAULT FALSE,
    
    -- Timestamps
    email_date TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for common queries
CREATE INDEX idx_expenses_status ON expenses(status);
CREATE INDEX idx_expenses_type ON expenses(type);
CREATE INDEX idx_expenses_vendor ON expenses(vendor_name);
CREATE INDEX idx_expenses_created ON expenses(created_at DESC);
```

### Field Descriptions

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `amount` | Numeric | Expense amount | 49.99 |
| `type` | String | "income" or "cost" | "cost" |
| `currency` | String | 3-letter ISO code | "USD" |
| `explanation` | Text | What the expense is for | "Monthly hosting fee" |
| `tags` | Array | Categories/labels | ["software", "hosting"] |
| `status` | String | "draft" or "confirmed" | "draft" |
| `sender_email` | String | Email sender | "billing@digitalocean.com" |
| `sender_domain` | String | Domain of sender | "digitalocean.com" |
| `vendor_name` | String | Company name | "DigitalOcean" |
| `email_subject` | String | Original subject | "Invoice #12345" |
| `invoice_number` | String | Invoice/bill ID | "INV-2024-001" |
| `payment_status` | String | Payment state | "paid" |
| `attachment_filename` | String | PDF filename | "invoice.pdf" |
| `attachment_data` | Binary | PDF file content | (binary data) |
| `has_attachments` | Boolean | Has PDF? | true |
| `email_date` | Timestamp | When email sent | 2024-01-15 10:30:00 |
| `created_at` | Timestamp | When parsed | 2024-01-15 10:45:00 |

---

## 4. Email Parsing Flow

### Step-by-Step Process

```
1. Background Job Triggers (every 15 minutes)
   └─► Check for unread emails in inbox

2. For Each Unread Email:
   ├─► Extract metadata:
   │   ├─► Sender email/domain
   │   ├─► Subject line
   │   ├─► Date sent
   │   └─► Email body (text/plain)
   │
   ├─► Extract PDF attachment (if present)
   │   └─► First .pdf file found
   │
   ├─► Send to Claude API:
   │   └─► Prompt: "Extract expense data from this email"
   │   └─► Returns JSON with structured fields
   │
   ├─► Create Expense record:
   │   ├─► Status = "draft"
   │   ├─► All extracted fields
   │   └─► PDF stored as bytea
   │
   └─► Mark email as read

3. User Reviews Drafts in UI
   ├─► Edit if needed
   └─► Confirm or Delete
```

### IMAP Implementation

```python
# Connect to Gmail
mail = imaplib.IMAP4_SSL('imap.gmail.com')
mail.login(email_address, app_password)
mail.select('inbox')

# Search for unread
status, messages = mail.search(None, 'UNSEEN')

# Process each email
for email_id in messages[0].split():
    status, msg_data = mail.fetch(email_id, '(RFC822)')
    msg = email.message_from_bytes(msg_data[0][1])
    
    # Extract data...
    
    # Mark as read
    mail.store(email_id, '+FLAGS', '\\Seen')
```

### Claude API Integration

**Prompt Template:**
```
Parse this email and extract expense information. 
Return a JSON object with these fields:
- amount (number)
- type ("income" or "cost")
- currency (3-letter code like USD, EUR)
- explanation (brief description)
- tags (array of relevant tags like ["software", "hosting"])
- vendor_name (company name)
- invoice_number (if present)
- payment_status (if mentioned: "paid", "unpaid", or "pending")

Email Subject: {subject}

Email Content:
{body}

Return ONLY valid JSON, no other text.
```

**Example Response:**
```json
{
  "amount": 49.99,
  "type": "cost",
  "currency": "USD",
  "explanation": "Monthly server hosting",
  "tags": ["hosting", "infrastructure"],
  "vendor_name": "DigitalOcean",
  "invoice_number": "INV-2024-12345",
  "payment_status": "paid"
}
```

### Error Handling

- **Invalid JSON from Claude** - Log error, skip email, mark as read
- **Missing required fields** - Use defaults (amount=0, type="cost")
- **IMAP connection failure** - Retry next cycle (15 min later)
- **PDF extraction failure** - Create expense without attachment
- **Claude API rate limit** - Exponential backoff, retry

---

## 5. REST API Specification

### Base URL
`http://localhost:5055` (local)
`https://your-app.railway.app` (production)

### Endpoints

#### GET /api/expenses
List all expenses with optional filters.

**Query Parameters:**
- `status` (optional) - "draft" or "confirmed"
- `type` (optional) - "income" or "cost"

**Response:**
```json
[
  {
    "id": 1,
    "amount": 49.99,
    "type": "cost",
    "currency": "USD",
    "explanation": "Monthly hosting",
    "tags": ["hosting"],
    "status": "draft",
    "sender_email": "billing@example.com",
    "sender_domain": "example.com",
    "vendor_name": "Example Inc",
    "email_subject": "Invoice #12345",
    "invoice_number": "INV-12345",
    "payment_status": "paid",
    "has_attachments": true,
    "attachment_filename": "invoice.pdf",
    "email_date": "2024-01-15T10:30:00Z",
    "created_at": "2024-01-15T10:45:00Z"
  }
]
```

#### GET /api/expenses/:id
Get single expense details.

**Response:** Same as single item from list above

#### PUT /api/expenses/:id
Update an expense.

**Request Body:**
```json
{
  "amount": 59.99,
  "type": "cost",
  "currency": "USD",
  "explanation": "Updated description",
  "tags": ["new", "tags"],
  "vendor_name": "New Vendor",
  "invoice_number": "INV-99999",
  "payment_status": "unpaid"
}
```

**Response:** Updated expense object

#### DELETE /api/expenses/:id
Delete an expense.

**Response:** 204 No Content

#### POST /api/expenses/:id/confirm
Change expense status from "draft" to "confirmed".

**Response:** Updated expense object

#### GET /api/expenses/:id/pdf
Download PDF attachment.

**Response:** 
- Content-Type: application/pdf
- Binary PDF data
- Filename in Content-Disposition header

#### GET /api/stats
Get summary statistics.

**Response:**
```json
{
  "total_income": 5000.00,
  "total_costs": 2500.00,
  "net": 2500.00,
  "income_count": 10,
  "cost_count": 45,
  "draft_count": 3,
  "top_vendors": [
    {
      "name": "DigitalOcean",
      "total": 600.00,
      "count": 12
    },
    {
      "name": "AWS",
      "total": 450.00,
      "count": 8
    }
  ]
}
```

#### POST /api/check-emails
Manually trigger email check (don't wait for scheduled run).

**Response:**
```json
{
  "message": "Email check triggered"
}
```

---

## 6. Web UI Specification

### Layout

```
┌─────────────────────────────────────────────┐
│  📊 Expense Tracker                         │
│  [📧 Check Emails Now]                      │
├─────────────────────────────────────────────┤
│  ┌──────────┐ ┌──────────┐ ┌──────────┐   │
│  │  INCOME  │ │  COSTS   │ │   NET    │   │
│  │ $5000.00 │ │ $2500.00 │ │ $2500.00 │   │
│  │ 10 items │ │ 45 items │ │          │   │
│  └──────────┘ └──────────┘ └──────────┘   │
│  ┌──────────┐                               │
│  │  DRAFTS  │                               │
│  │    3     │                               │
│  └──────────┘                               │
├─────────────────────────────────────────────┤
│  [Drafts] [Confirmed] [All]                 │
├─────────────────────────────────────────────┤
│  ┌─────────────────────────────────────┐   │
│  │ COST   DigitalOcean         $49.99  │   │
│  │        Monthly hosting              │   │
│  │        Invoice: INV-12345           │   │
│  │        [✓] [✎] [PDF] [×]           │   │
│  ├─────────────────────────────────────┤   │
│  │ INCOME Customer Payment   $1000.00  │   │
│  │        Project X payment            │   │
│  │        [✓] [✎] [×]                 │   │
│  └─────────────────────────────────────┘   │
└─────────────────────────────────────────────┘
```

### Features

**Stats Cards:**
- Total income (green)
- Total costs (red)
- Net (blue)
- Draft count (gray)

**Tabs:**
- Drafts - Only unconfirmed expenses
- Confirmed - Only confirmed expenses
- All - Everything

**Expense List Items:**
- Type badge (INCOME/COST)
- Vendor name or sender email
- Explanation text
- Email subject and invoice number
- Tags as colored pills
- Amount with currency
- Action buttons:
  - ✓ Confirm (drafts only)
  - ✎ Edit
  - PDF Download (if has attachment)
  - × Delete

**Edit Modal:**
- Amount (number input)
- Type (dropdown: income/cost)
- Currency (text input, 3 chars)
- Vendor (text input)
- Explanation (textarea)
- Tags (comma-separated text input)
- [Cancel] [Save] buttons

**Auto-refresh:**
- Stats and list refresh every 30 seconds
- Manual "Check Emails" button for immediate check

---

## 7. Configuration & Environment

### Environment Variables

Required for deployment:

```bash
# Flask
SECRET_KEY=your-random-secret-key-here-change-this

# Database (auto-provided by Railway)
DATABASE_URL=postgresql://user:pass@host:port/db

# Email
EMAIL_ADDRESS=expenses@gmail.com
EMAIL_PASSWORD=gmail-app-password-16-chars
EMAIL_IMAP_SERVER=imap.gmail.com

# Claude API
ANTHROPIC_API_KEY=sk-ant-api03-...
```

### Gmail Setup Instructions

1. **Create Gmail account** - Dedicated for expenses
2. **Enable 2FA** - Required for app passwords
3. **Generate app password:**
   - Google Account → Security → 2-Step Verification
   - App passwords → Select "Mail"
   - Copy 16-character password
4. **Use app password** - Not your regular Gmail password

### File Structure

```
expense-tracker/
├── app.py                 # Main Flask application
│   ├── Routes (/, /api/*)
│   ├── Background scheduler setup
│   └── Database initialization
│
├── models.py              # SQLAlchemy models
│   └── Expense class with to_dict()
│
├── config.py              # Configuration loader
│   ├── Reads .env file
│   ├── Database URL parsing
│   └── Default values
│
├── email_parser.py        # Email processing
│   ├── connect_to_email()
│   ├── parse_email_with_claude()
│   ├── get_attachment()
│   └── fetch_new_emails()
│
├── templates/
│   └── index.html         # Single-page UI
│
├── requirements.txt       # Python dependencies
├── Procfile              # Railway: web: gunicorn app:app
├── .env.example          # Template for .env
├── .gitignore           # Ignore .env, __pycache__, etc.
└── README.md            # Setup instructions
```

### Dependencies (requirements.txt)

```
Flask==3.0.0
Flask-SQLAlchemy==3.1.1
psycopg2-binary==2.9.9
APScheduler==3.10.4
anthropic==0.18.1
python-dotenv==1.0.0
gunicorn==21.2.0
```

---

## 8. Deployment Guide

### Option 1: Railway (Recommended)

**Why Railway?**
- Simplest deployment experience
- Managed Postgres included
- Auto-deploys from Git pushes
- Built-in environment variables UI
- ~$5-10/month for everything

**Steps:**

1. **Prepare code:**
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   git remote add origin YOUR_GITHUB_REPO
   git push -u origin main
   ```

2. **Deploy on Railway:**
   - Go to railway.app
   - "New Project" → "Deploy from GitHub"
   - Select your repository
   - Railway auto-detects Python + Procfile

3. **Add Postgres:**
   - In project: "New" → "Database" → "PostgreSQL"
   - DATABASE_URL auto-set

4. **Set environment variables:**
   - Project → Variables
   - Add: SECRET_KEY, EMAIL_ADDRESS, EMAIL_PASSWORD, ANTHROPIC_API_KEY

5. **Initialize database:**
   ```bash
   # Install Railway CLI
   npm install -g @railway/cli
   railway login
   railway link
   
   # Run migration
   railway run python
   >>> from app import app, db
   >>> with app.app_context():
   ...     db.create_all()
   >>> exit()
   ```

6. **Get URL:**
   - Railway provides: https://your-app.railway.app
   - Visit to see UI

### Option 2: Render

- Similar to Railway
- Connect GitHub repo
- Add Postgres database
- Set environment variables
- Free tier available (with limitations)

### Option 3: Fly.io

- Dockerfile deployment
- Free Postgres (small size)
- CLI-based deployment
- Good for learning infrastructure

### Option 4: DigitalOcean App Platform

- GitHub integration
- Managed Postgres
- More expensive (~$12/month minimum)
- More control over resources

### Option 5: Traditional VPS

- Most control, most work
- Need to manage: Nginx, systemd, Postgres, SSL
- Cheapest option (~$5/month)
- Best for learning

---

## 9. Usage Workflow

### Daily Use

1. **Forward expense emails**
   - Get invoice → Forward to expenses@gmail.com
   - Get receipt → Forward to expenses@gmail.com
   - Get bill → Forward to expenses@gmail.com

2. **App processes automatically**
   - Checks every 15 minutes
   - Creates draft expenses
   - Extracts PDFs

3. **Review drafts**
   - Open app
   - Check "Drafts" tab
   - Verify amounts and details
   - Edit if needed
   - Click ✓ to confirm

4. **View stats**
   - Dashboard shows totals
   - Track spending by vendor
   - Monitor income vs costs

### Manual Email Check

- Click "Check Emails Now" button
- Useful when you just forwarded an email
- Don't want to wait 15 minutes

### Editing Expenses

- Click ✎ on any expense
- Modify fields in modal
- Save changes
- Works for drafts and confirmed

### Deleting Expenses

- Click × on any expense
- Confirms before deleting
- Permanent (no undo)

### Viewing PDFs

- Click "PDF" button on expenses with attachments
- Opens in new tab
- Original filename preserved

---

## 10. Technical Decisions & Rationale

### Why IMAP Polling vs Webhooks?

**IMAP Polling (Chosen):**
- ✅ Works with any email provider
- ✅ No domain/DNS setup needed
- ✅ No webhook URL to secure
- ✅ Simple to implement
- ❌ 15-minute delay

**Webhooks (Not Chosen):**
- ✅ Instant processing
- ❌ Requires custom domain
- ❌ Need webhook service (SendGrid, Mailgun)
- ❌ More complex setup
- ❌ Additional cost

**Verdict:** For personal use, 15-minute delay is acceptable for much simpler setup.

### Why Postgres Bytea vs Object Storage?

**Postgres Bytea (Chosen):**
- ✅ Zero additional services
- ✅ Atomic transactions (expense + PDF together)
- ✅ Backup included with database
- ✅ Simpler code
- ❌ Database size grows
- ❌ Slower for very large files

**Object Storage (Not Chosen):**
- ✅ Better for many/large files
- ✅ Separate scaling
- ❌ Additional service (S3, R2, B2)
- ❌ More complex code
- ❌ Another thing to manage

**Verdict:** Most invoices are <2MB. Even 1000 PDFs = 2GB, which is fine for Postgres. Simpler is better.

### Why APScheduler vs Celery?

**APScheduler (Chosen):**
- ✅ Built into app process
- ✅ No separate worker/broker
- ✅ Perfect for simple periodic tasks
- ✅ Easier to deploy

**Celery (Not Chosen):**
- ✅ More powerful
- ✅ Better for many tasks
- ❌ Requires Redis/RabbitMQ
- ❌ Separate worker process
- ❌ Overkill for this use case

**Verdict:** One periodic job doesn't need Celery's complexity.

### Why Claude API vs Open Source Models?

**Claude API (Chosen):**
- ✅ Best extraction accuracy
- ✅ Zero infrastructure
- ✅ Pay per use (~$0.01/email)
- ✅ Reliable and fast

**Open Source (Not Chosen):**
- ✅ No API costs
- ❌ Need to host model
- ❌ Lower accuracy
- ❌ More code complexity

**Verdict:** $1-5/month in API costs is worth the accuracy and simplicity.

### Why Single-Page UI vs Traditional Forms?

**Single-Page UI (Chosen):**
- ✅ Feels faster (no page reloads)
- ✅ Better for frequent actions
- ✅ Auto-refresh works seamlessly

**Traditional Forms (Not Chosen):**
- ✅ Simpler to build
- ✅ Works without JavaScript
- ❌ Page reloads annoying

**Verdict:** Vanilla JavaScript is simple enough, SPA is better UX.

---

## 11. Cost Analysis

### Monthly Operating Costs

**Railway:**
- Hobby plan: $5/month
- Postgres: Included
- Traffic: Included (reasonable use)
- Total: **$5/month**

**Claude API:**
- Email parsing: ~$0.01 per email
- 100 emails/month: **$1/month**
- 500 emails/month: **$5/month**

**Gmail:**
- **Free** (personal account)

**Total: $6-10/month** depending on email volume

### Cost Optimization

- Use Railway free trial initially
- Claude API has generous free tier
- Consider switching to Render free tier for testing
- VPS option: $5/month total (but more work)

---

## 12. Security Considerations

### What's Secure

✅ **Gmail app password** - Not main account password
✅ **Environment variables** - Not in code/Git
✅ **HTTPS** - Railway provides SSL automatically
✅ **Database** - Managed, backed up, encrypted at rest

### What's Not Secure (By Design)

❌ **No authentication** - Anyone with URL can access
❌ **No user isolation** - Personal use only
❌ **Email plaintext** - Stored in database
❌ **API endpoints open** - No auth required

### Recommendations

- **Keep URL private** - Don't share publicly
- **Use strong SECRET_KEY** - Random 32+ characters
- **Enable Railway's basic auth** - Optional password protection
- **Regular backups** - Railway does this automatically
- **Monitor logs** - Check for suspicious activity

### If You Need Auth

Add Flask-Login or Flask-HTTPAuth:
```python
from flask_httpauth import HTTPBasicAuth
auth = HTTPBasicAuth()

@auth.verify_password
def verify_password(username, password):
    if username == 'admin':
        return check_password_hash(PASSWORD_HASH, password)
    return False

@app.route('/')
@auth.login_required
def index():
    return render_template('index.html')
```

---

## 13. Troubleshooting

### Email Not Being Parsed

**Symptoms:** Emails forwarded but no drafts appear

**Checks:**
1. Verify EMAIL_ADDRESS and EMAIL_PASSWORD in Railway variables
2. Check Railway logs for errors: `railway logs`
3. Ensure 2FA enabled and using app password (not regular password)
4. Test manually: Click "Check Emails Now" button
5. Check Gmail inbox - are emails marked as read?

**Common Issues:**
- Wrong password → "Authentication failed" in logs
- IMAP not enabled → Gmail settings → Enable IMAP
- Firewall blocking → Railway should handle this

### Claude API Errors

**Symptoms:** Drafts created but fields are empty/wrong

**Checks:**
1. Verify ANTHROPIC_API_KEY is correct
2. Check API key has credits: console.anthropic.com
3. Look for rate limiting in logs
4. Test API key separately

**Common Issues:**
- Invalid API key → "401 Unauthorized"
- No credits → "402 Payment Required"
- Rate limited → Retry with backoff

### Database Errors

**Symptoms:** 500 errors, can't save expenses

**Checks:**
1. Verify DATABASE_URL is set correctly
2. Check if database was initialized: `db.create_all()`
3. Review Railway Postgres logs
4. Check disk space (rare on Railway)

**Common Issues:**
- Tables not created → Run migration
- Connection pool exhausted → Restart app
- Postgres out of storage → Upgrade plan

### UI Not Loading

**Symptoms:** Blank page or 404 errors

**Checks:**
1. Verify app is running: Railway dashboard
2. Check build logs for errors
3. Test API directly: /api/expenses
4. Browser console for JavaScript errors

**Common Issues:**
- Missing templates folder → Check Git
- JavaScript error → Browser console
- API endpoint wrong → Check fetch() URLs

---

## 14. Future Enhancements

### Easy Additions

- **Export to CSV** - Download all expenses as spreadsheet
- **Date range filters** - View expenses from specific period
- **Search** - Find by vendor, amount, description
- **Categories** - Group expenses beyond tags
- **Budget alerts** - Email when spending exceeds threshold

### Medium Complexity

- **Recurring expenses detection** - Flag monthly bills
- **Currency conversion** - Convert all to base currency
- **Bank statement parsing** - Handle CSV imports
- **Receipt OCR** - Extract data from image attachments
- **Multiple email accounts** - Check multiple inboxes

### Advanced Features

- **Multi-user support** - Separate workspaces per user
- **Authentication** - Login system
- **Approval workflows** - Manager approval for expenses
- **Accounting integration** - Export to QuickBooks, Xero
- **Analytics dashboard** - Charts, trends, predictions
- **Mobile app** - Native iOS/Android

### AI Improvements

- **Smart categorization** - Auto-tag based on vendor
- **Duplicate detection** - Flag similar expenses
- **Anomaly detection** - Alert on unusual amounts
- **Predictive budgeting** - Forecast future expenses
- **Natural language queries** - "Show me AWS costs this quarter"

---

## 15. Code Implementation Notes

### Key Functions

**app.py - check_emails()**
- Background job that runs every 15 minutes
- Calls `fetch_new_emails()` from email_parser
- Creates Expense records with status='draft'
- Commits to database

**email_parser.py - fetch_new_emails()**
- Connects to Gmail via IMAP
- Searches for UNSEEN emails
- Extracts metadata, body, attachments
- Calls `parse_email_with_claude()`
- Returns list of expense data dicts
- Marks emails as read

**email_parser.py - parse_email_with_claude()**
- Sends email text to Claude API
- Prompt asks for structured JSON
- Parses response (handling markdown code blocks)
- Returns dict with expense fields

**models.py - Expense.to_dict()**
- Converts SQLAlchemy model to JSON-serializable dict
- Used by all API endpoints
- Handles datetime formatting

**API Routes**
- All CRUD operations
- Stats aggregation using SQLAlchemy functions
- PDF download with send_file()
- Confirm endpoint updates status

**UI (index.html)**
- Vanilla JavaScript (no framework)
- Fetch API for all requests
- Simple tab switching
- Modal for editing
- Auto-refresh every 30 seconds

### Important Code Patterns

**Database URL Handling:**
```python
# Railway uses postgres:// but SQLAlchemy needs postgresql://
if SQLALCHEMY_DATABASE_URI.startswith('postgres://'):
    SQLALCHEMY_DATABASE_URI = SQLALCHEMY_DATABASE_URI.replace(
        'postgres://', 'postgresql://', 1
    )
```

**PDF Extraction:**
```python
# Get first PDF attachment from email
for part in msg.walk():
    if part.get_content_maintype() == 'multipart':
        continue
    filename = part.get_filename()
    if filename and filename.lower().endswith('.pdf'):
        return filename, part.get_payload(decode=True)
```

**Stats Aggregation:**
```python
income = db.session.query(func.sum(Expense.amount)).filter(
    Expense.type == 'income',
    Expense.status == 'confirmed'
).scalar() or 0
```

**Scheduler Setup:**
```python
scheduler = BackgroundScheduler()
scheduler.add_job(
    func=check_emails,
    trigger='interval',
    minutes=15,
    id='email_check_job',
    replace_existing=True
)
if not scheduler.running:
    scheduler.start()
```

---

## 16. Testing Strategy

### Manual Testing

**Email Parsing:**
1. Forward a real invoice email
2. Wait 15 min or click "Check Emails"
3. Verify draft appears with correct data
4. Check PDF downloads correctly

**Draft Workflow:**
1. Create draft (via email)
2. Edit fields in UI
3. Confirm draft
4. Verify appears in confirmed list
5. Check stats update

**API Testing:**
```bash
# Get all expenses
curl http://localhost:5055/api/expenses

# Get stats
curl http://localhost:5055/api/stats

# Update expense
curl -X PUT http://localhost:5055/api/expenses/1 \
  -H "Content-Type: application/json" \
  -d '{"amount": 99.99}'

# Confirm expense
curl -X POST http://localhost:5055/api/expenses/1/confirm
```

### Integration Testing

**Database:**
```python
from app import app, db, Expense

with app.app_context():
    # Create test expense
    expense = Expense(
        amount=100,
        type='cost',
        currency='USD',
        explanation='Test expense',
        status='draft'
    )
    db.session.add(expense)
    db.session.commit()
    
    # Query
    assert Expense.query.count() == 1
    assert Expense.query.first().amount == 100
```

**Email Parser:**
```python
# Create test email message
import email
msg = email.message_from_string("""
From: billing@example.com
Subject: Invoice #12345
Date: Mon, 15 Jan 2024 10:00:00 +0000

Your monthly invoice for $49.99 is ready.
""")

# Test parsing
# (Would need to mock Claude API)
```

### Deployment Testing

1. Deploy to Railway staging
2. Trigger email check via API
3. Verify logs show successful processing
4. Check database has data
5. Test all UI functions
6. Monitor for 24 hours

---

## 17. Monitoring & Maintenance

### What to Monitor

**Application Logs (Railway):**
- Email check job runs every 15 min
- Successful parsing messages
- API errors (4xx, 5xx)
- Claude API failures

**Database Health:**
- Disk usage (watch PDF growth)
- Query performance
- Connection count

**Email Processing:**
- Number of emails processed per day
- Parse failure rate
- Draft vs confirmed ratio

### Regular Tasks

**Daily:**
- Check Railway logs for errors
- Verify email checks running

**Weekly:**
- Review draft expenses (shouldn't accumulate)
- Check stats make sense

**Monthly:**
- Review costs (Railway + Claude)
- Database backup verification
- Clean up old confirmed expenses (optional)

### Alerts to Set Up

- Railway: Email on deployment failure
- Railway: Email on app crash
- Claude API: Budget alert in console
- Custom: If draft count > 10 (emails not being reviewed)

---

## 18. Documentation Checklist

### For New Users

- [ ] README.md with setup steps
- [ ] .env.example with all variables explained
- [ ] Gmail app password creation guide
- [ ] Railway deployment walkthrough
- [ ] First-time use tutorial

### For Developers

- [ ] Code comments on complex logic
- [ ] API endpoint documentation
- [ ] Database schema diagram
- [ ] Email parsing flow diagram
- [ ] Environment variable reference

### For Maintenance

- [ ] Troubleshooting guide
- [ ] Backup/restore procedures
- [ ] Scaling considerations
- [ ] Migration path (if changing services)

---

## 19. Summary

This expense tracker is designed for **simplicity and personal use**. It automates the tedious task of tracking business expenses by:

1. **Parsing emails automatically** using IMAP and Claude AI
2. **Storing structured data** in Postgres with PDF attachments
3. **Providing a clean UI** for review and confirmation
4. **Generating simple stats** for financial overview

The architecture prioritizes **ease of deployment** (Railway) and **low maintenance** (serverless-style, managed services) over scalability or multi-user features.

**Total setup time:** 30-60 minutes
**Monthly cost:** $6-10
**Maintenance:** Minimal (check logs occasionally)

Perfect for freelancers, small business owners, or anyone who wants to automate expense tracking without complex accounting software.

---

## 20. Quick Start Summary

```bash
# 1. Set up Gmail
# - Create account: expenses@gmail.com
# - Enable 2FA
# - Generate app password

# 2. Get Claude API key
# - Sign up: console.anthropic.com
# - Create API key

# 3. Deploy to Railway
# - Push code to GitHub
# - Connect Railway to repo
# - Add Postgres database
# - Set environment variables:
#   - SECRET_KEY
#   - EMAIL_ADDRESS
#   - EMAIL_PASSWORD
#   - ANTHROPIC_API_KEY

# 4. Initialize database
railway run python
>>> from app import app, db
>>> with app.app_context():
...     db.create_all()

# 5. Start using
# - Forward expense emails
# - Wait 15 min or click "Check Emails"
# - Review drafts
# - Confirm expenses
# - View stats
```

**Done!** Your expense tracker is live.
