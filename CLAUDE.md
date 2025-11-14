# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Flask-based expense tracker that automatically parses forwarded emails using Claude AI to extract expense information. Expenses are stored in PostgreSQL with PDF attachments. Built for personal use with a draft-review workflow.

## Architecture

### Core Components

- **app.py**: Main Flask application with REST API endpoints and APScheduler background job
- **email_parser.py**: IMAP email fetching and Claude AI parsing logic
- **models.py**: SQLAlchemy Expense model with to_dict() serialization
- **config.py**: Environment variable configuration with DATABASE_URL normalization
- **index.html**: Single-page vanilla JavaScript UI (no framework)

### Data Flow

1. APScheduler runs `check_emails()` every 15 minutes (configurable via `Config.EMAIL_CHECK_INTERVAL`)
2. `fetch_new_emails()` connects via IMAP, fetches UNSEEN emails
3. `parse_email_with_claude()` sends email text to Claude API with structured JSON prompt
4. Expense records created with `status='draft'` including PDF attachments stored as bytea
5. User reviews drafts in UI, edits if needed, confirms or deletes

### Database Schema

Single table: `expenses`
- Core fields: amount, type (income/cost), currency, explanation, tags[]
- Status: draft or confirmed
- Email metadata: sender_email, sender_domain, vendor_name, email_subject, invoice_number, payment_status
- Attachments: attachment_filename, attachment_data (bytea), has_attachments
- Timestamps: email_date, created_at

## Common Commands

### Local Development

```bash
# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Initialize database (run in Python shell)
python
>>> from app import app, db
>>> with app.app_context():
...     db.create_all()
>>> exit()

# Run development server
python app.py
```

### Railway Deployment

```bash
# Install Railway CLI
npm install -g @railway/cli

# Login and link project
railway login
railway link

# Initialize database on Railway
railway run python
>>> from app import app, db
>>> with app.app_context():
...     db.create_all()
>>> exit()

# View logs
railway logs
```

### Testing

```bash
# Test API endpoints
curl http://localhost:5055/api/expenses
curl http://localhost:5055/api/stats
curl -X POST http://localhost:5055/api/check-emails

# Update expense
curl -X PUT http://localhost:5055/api/expenses/1 \
  -H "Content-Type: application/json" \
  -d '{"amount": 99.99, "vendor_name": "Updated Vendor"}'
```

## Important Patterns

### DATABASE_URL Normalization

Railway provides `DATABASE_URL` with `postgres://` scheme, but SQLAlchemy requires `postgresql://`. The config.py:14-15 handles this conversion automatically.

### Email Parsing

- Email body limited to 3000 characters in email_parser.py:124 to avoid token limits
- Claude response may include markdown code blocks - stripped in email_parser.py:48-52
- Only first PDF attachment extracted per email in get_attachment()

### Scheduler Lifecycle

- APScheduler initialized in app.py:33-40 with interval trigger
- Scheduler starts in __main__ block (app.py:197-198)
- Background job runs in app context (app.py:19)

### PDF Handling

- PDFs stored as bytea in Postgres (attachment_data column)
- Downloaded via send_file() with BytesIO in app.py:125-130
- Original filename preserved in attachment_filename

### Stats Aggregation

- Uses SQLAlchemy func.sum() and func.count() for calculations in app.py:139-182
- Only confirmed expenses counted in totals
- Top vendors limited to 10, ordered by total spending

## Environment Variables Required

```bash
SECRET_KEY=<random-string>              # Flask session key
DATABASE_URL=<postgres-url>             # Auto-provided by Railway
EMAIL_ADDRESS=<gmail-address>           # Gmail account for forwarding
EMAIL_PASSWORD=<gmail-app-password>     # 16-char app password (not regular password)
EMAIL_IMAP_SERVER=imap.gmail.com        # Optional, defaults to Gmail
ANTHROPIC_API_KEY=sk-ant-api03-...      # Claude API key
```

## Code Conventions

- All database operations use SQLAlchemy ORM
- API endpoints return JSON via jsonify()
- Error handling: Claude parsing errors caught and logged, email marked as read regardless
- UI: Vanilla JavaScript, no build step, uses Fetch API
- Auto-refresh: Stats and expenses reload every 30 seconds client-side

## Key Implementation Details

### Claude API Prompt Structure

The prompt in email_parser.py:20-35 requests specific JSON fields:
- amount, type, currency, explanation, tags
- vendor_name, invoice_number, payment_status

Returns ONLY valid JSON with no other text (critical for parsing).

### Status Workflow

- New expenses created as `status='draft'` (app.py:24)
- Confirm endpoint changes to `status='confirmed'` (app.py:112)
- Stats only aggregate confirmed expenses
- UI shows confirm button only for drafts

### Frontend State Management

- currentTab tracks active view (drafts/confirmed/all)
- Tab switching updates query params and reloads expense list
- Modal shows/hides with `.show` class toggle
- No state management framework - simple DOM manipulation

## Troubleshooting Common Issues

### Emails Not Being Parsed

1. Check Railway logs: `railway logs`
2. Verify EMAIL_ADDRESS and EMAIL_PASSWORD in environment variables
3. Ensure Gmail has IMAP enabled and 2FA + app password configured
4. Test manually via "Check Emails Now" button

### Database Connection Errors

- Verify DATABASE_URL is set (Railway auto-provides this)
- Check if tables exist - run db.create_all() if needed
- Confirm postgres:// to postgresql:// conversion happened

### Claude API Errors

- Check ANTHROPIC_API_KEY is valid
- Verify API key has credits at console.anthropic.com
- Look for JSON parsing errors in logs - Claude must return valid JSON

### Scheduler Not Running

- Scheduler only starts in __main__ block (app.py:197-198)
- In production with gunicorn, use Railway Procfile: `web: gunicorn app:app`
- Scheduler runs in the main worker process automatically

## Testing Checklist

When making changes, verify:

1. Database operations: Create, read, update, delete expenses via API
2. Email parsing: Forward test email, verify draft created correctly
3. PDF handling: Attach PDF to email, verify download works
4. Stats calculation: Confirm income/costs/net calculate correctly
5. Draft workflow: Edit draft, confirm, verify appears in confirmed list
6. UI: Test all tabs, modal editing, delete confirmation
