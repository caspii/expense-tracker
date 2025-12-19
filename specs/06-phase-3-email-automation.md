# Phase 3: Email Automation (Future)

This phase adds automatic email processing via IMAP polling. It builds on earlier phases by adding a background job that periodically checks for new emails and creates draft expenses automatically.

**Status:** Not yet implemented. This document describes the planned functionality.

## Overview

```
┌─────────────────┐
│   Email Server  │ (Gmail IMAP)
│  (Forward here) │
└────────┬────────┘
         │
         │ Poll every 15 min
         │
┌────────▼────────┐
│  Background Job │
│  - Fetch emails │
│  - Parse with AI│
│  - Create drafts│
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Draft Expenses │
│  (User reviews) │
└─────────────────┘
```

## Email Processing Flow

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
   │   └─► Same prompt as Phase 1
   │   └─► Returns JSON with structured fields
   │
   ├─► Create Expense record:
   │   ├─► Status = "draft"
   │   ├─► Source type = "email_auto"
   │   ├─► All extracted fields
   │   └─► PDF stored as bytea
   │
   └─► Mark email as read

3. User Reviews Drafts in UI
   ├─► Edit if needed
   └─► Confirm or Delete
```

## IMAP Implementation

### Connection

```python
import imaplib
import email

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

### PDF Extraction

```python
def get_attachment(msg):
    """Extract first PDF attachment from email."""
    for part in msg.walk():
        if part.get_content_maintype() == 'multipart':
            continue
        filename = part.get_filename()
        if filename and filename.lower().endswith('.pdf'):
            return filename, part.get_payload(decode=True)
    return None, None
```

## Background Scheduler

### APScheduler Setup

```python
from apscheduler.schedulers.background import BackgroundScheduler

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

### Check Emails Job

```python
def check_emails():
    """Background job to fetch and process new emails."""
    with app.app_context():
        try:
            expenses = fetch_new_emails()
            for exp_data in expenses:
                expense = Expense(
                    amount=exp_data.get('amount', 0),
                    type=exp_data.get('type', 'cost'),
                    currency=exp_data.get('currency', 'USD'),
                    explanation=exp_data.get('explanation'),
                    tags=exp_data.get('tags', []),
                    status='draft',
                    source_type='email_auto',
                    # ... other fields
                )
                db.session.add(expense)
            db.session.commit()
            app.logger.info(f"Processed {len(expenses)} emails")
        except Exception as e:
            app.logger.error(f"Email check failed: {e}")
```

## Additional Dependencies

Add to requirements.txt:
```
APScheduler==3.10.4
```

## Additional Environment Variables

```bash
# Email settings
EMAIL_ADDRESS=expenses@gmail.com
EMAIL_PASSWORD=gmail-app-password-16-chars
EMAIL_IMAP_SERVER=imap.gmail.com
EMAIL_CHECK_INTERVAL=15  # minutes, optional
```

## Gmail Setup Instructions

1. **Create Gmail account** - Dedicated for expenses
2. **Enable 2FA** - Required for app passwords
3. **Generate app password:**
   - Google Account → Security → 2-Step Verification
   - App passwords → Select "Mail"
   - Copy 16-character password
4. **Enable IMAP** - Gmail Settings → See all settings → Forwarding and POP/IMAP → Enable IMAP
5. **Use app password** - Not your regular Gmail password

## Additional API Endpoints

### POST /api/check-emails
Manually trigger email check (don't wait for scheduled run).

**Response:**
```json
{
  "message": "Email check triggered",
  "new_expenses": 3
}
```

### GET /api/email-status
Check email processing status.

**Response:**
```json
{
  "connected": true,
  "last_check": "2024-01-15T10:45:00Z",
  "next_check": "2024-01-15T11:00:00Z",
  "emails_processed_today": 5
}
```

## Error Handling

| Error | Handling |
|-------|----------|
| IMAP connection failure | Log error, retry next cycle |
| Authentication failed | Log error, alert user |
| Invalid JSON from Claude | Log error, skip email, mark as read |
| Missing required fields | Use defaults (amount=0, type="cost") |
| PDF extraction failure | Create expense without attachment |
| Claude API rate limit | Exponential backoff, retry |

## UI Updates for Phase 2

### Email Status Indicator

```
┌─────────────────────────────────────────────┐
│  📊 Expense Tracker                         │
│  [📧 Check Emails Now]                      │
│  Last check: 5 min ago | Next: in 10 min   │
└─────────────────────────────────────────────┘
```

### Manual Email Check Button

Triggers immediate email check instead of waiting for scheduler.

## Testing Checklist

- [ ] Forward a real invoice email
- [ ] Wait 15 min or click "Check Emails"
- [ ] Verify draft appears with correct data
- [ ] Check PDF downloads correctly
- [ ] Verify email marked as read in Gmail
- [ ] Test with email without PDF
- [ ] Test with malformed email
- [ ] Test scheduler runs on schedule
- [ ] Test manual trigger works

## Technical Decisions

### Why IMAP Polling vs Webhooks?

**IMAP Polling (Chosen):**
- Works with any email provider
- No domain/DNS setup needed
- No webhook URL to secure
- Simple to implement
- 15-minute delay (acceptable for personal use)

**Webhooks (Not Chosen):**
- Instant processing
- Requires custom domain
- Need webhook service (SendGrid, Mailgun)
- More complex setup
- Additional cost

### Why APScheduler vs Celery?

**APScheduler (Chosen):**
- Built into app process
- No separate worker/broker
- Perfect for simple periodic tasks
- Easier to deploy

**Celery (Not Chosen):**
- More powerful
- Better for many tasks
- Requires Redis/RabbitMQ
- Separate worker process
- Overkill for this use case
