# Phase 1: Manual Input

This phase implements three ways to add expenses:
1. **Manual Entry** - Fill out a form with all expense details
2. **Paste Email Text** - Paste email content for AI parsing
3. **Upload PDF** - Drag and drop an invoice/receipt for AI parsing

For options 2 and 3, the AI-extracted data is displayed in the same form as manual entry, allowing the user to review before saving.

## Input Methods

### 1. Manual Entry

User fills out a form with all expense fields directly.

**Flow:**
```
┌─────────────────────────────────────┐
│  [+ Add Expense] button             │
└─────────────────┬───────────────────┘
                  ▼
┌─────────────────────────────────────┐
│  Add Expense Modal                  │
│  ┌─────────────────────────────┐   │
│  │ Amount: [_________]         │   │
│  │ Type:   [Income ▼]          │   │
│  │ Category: [Operations ▼]    │   │  ← (only shown for costs)
│  │ Currency: [USD]             │   │
│  │ Vendor: [_________]         │   │
│  │ Explanation: [___________]  │   │
│  │ Tags: [_________]           │   │
│  │ Date: [____-__-__]          │   │
│  │ Invoice #: [_________]      │   │
│  └─────────────────────────────┘   │
│  [Cancel]                    [Save] │
└─────────────────────────────────────┘
```

**Behavior:**
- All fields are editable
- Source type set to `manual`
- Expense is saved immediately (no draft state)

### 2. Paste Email Text

User pastes raw email text, Claude extracts expense data, user reviews in form.

**Flow:**
```
┌─────────────────────────────────────┐
│  [Paste Email Text] button          │
└─────────────────┬───────────────────┘
                  ▼
┌─────────────────────────────────────┐
│  Paste Email Text Modal             │
│  ┌─────────────────────────────┐   │
│  │ Email Body:                 │   │
│  │ [________________________]  │   │
│  │ [________________________]  │   │
│  │ [________________________]  │   │
│  │ [________________________]  │   │
│  └─────────────────────────────┘   │
│  [Cancel]           [Parse with AI] │
└─────────────────┬───────────────────┘
                  │
                  ▼  (loading spinner)
┌─────────────────────────────────────┐
│  Review Extracted Data Modal        │
│  ┌─────────────────────────────┐   │
│  │ Amount: [49.99] ← pre-filled│   │
│  │ Type:   [Cost ▼]            │   │
│  │ Vendor: [DigitalOcean]      │   │
│  │ ... (all fields editable)   │   │
│  └─────────────────────────────┘   │
│  [Cancel]                    [Save] │
└─────────────────────────────────────┘
```

**Behavior:**
- User pastes email text
- Click "Parse with AI" sends to Claude
- Loading state while parsing
- Pre-filled form appears with extracted data
- User can edit any field before saving
- Source type set to `email_text`

### 3. Upload PDF (Drag and Drop)

User drags and drops a PDF invoice/receipt. Parsing starts automatically on drop.

**Flow:**
```
┌─────────────────────────────────────┐
│  [Upload PDF] button                │
└─────────────────┬───────────────────┘
                  ▼
┌─────────────────────────────────────┐
│  Upload PDF Modal                   │
│  ┌─────────────────────────────┐   │
│  │  ┌───────────────────────┐  │   │
│  │  │                       │  │   │
│  │  │   Drop PDF here       │  │   │
│  │  │   or click to browse  │  │   │
│  │  │                       │  │   │
│  │  └───────────────────────┘  │   │
│  │                             │   │
│  └─────────────────────────────┘   │
│  [Cancel]                          │
└─────────────────┬───────────────────┘
                  │
                  │  (file dropped - auto-upload)
                  ▼  (loading spinner)
┌─────────────────────────────────────┐
│  Review Extracted Data Modal        │
│  ┌─────────────────────────────┐   │
│  │ Amount: [149.00]            │   │
│  │ Type:   [Cost ▼]            │   │
│  │ Vendor: [AWS]               │   │
│  │ ... (all fields editable)   │   │
│  │                             │   │
│  │ Attached: invoice.pdf ✓     │   │
│  └─────────────────────────────┘   │
│  [Cancel]                    [Save] │
└─────────────────────────────────────┘
```

**Behavior:**
- User drags PDF onto drop zone (or clicks to browse)
- Parsing starts automatically when file is dropped
- Loading state while parsing
- Pre-filled form appears with extracted data
- PDF is attached to the expense record
- User can edit any field before saving
- Source type set to `pdf_upload`

## Display Formatting

### Thousands Separators

All monetary amounts should be displayed with thousands separators for readability:

| Raw Value | Displayed |
|-----------|-----------|
| 1000 | 1,000.00 |
| 12500.50 | 12,500.50 |
| 1000000 | 1,000,000.00 |

This applies to:
- Expense list items
- Stats cards (Total Income, Total Costs, Net)
- Form inputs (display only, not for editing)

## Claude AI Integration

### Parse Text Prompt

```
Parse this email/document and extract expense information.
Return a JSON object with these fields:
- amount (number, required)
- type ("income" or "cost", required)
- cost_category (only if type is "cost": "operations", "freelancers", "equipment", or "other")
  - operations: recurring costs like SaaS, hosting, subscriptions
  - freelancers: payments to contractors, developers, designers
  - equipment: one-off purchases like hardware, software licenses
  - other: anything that doesn't fit above
- currency (3-letter code like USD, EUR, default USD)
- explanation (brief description)
- tags (array of relevant tags like ["software", "hosting"])
- vendor_name (company name)
- invoice_number (if present)
- expense_date (YYYY-MM-DD format if mentioned)

Content:
{body}

Return ONLY valid JSON, no other text.
```

### Parse PDF Flow

1. Extract text from PDF using PyPDF2
2. Send extracted text to Claude with same prompt
3. Parse JSON response
4. Return structured data

```python
def parse_pdf_with_claude(pdf_data: bytes, filename: str) -> dict:
    # Extract text from PDF
    pdf_reader = PyPDF2.PdfReader(io.BytesIO(pdf_data))
    text = ""
    for page in pdf_reader.pages:
        text += page.extract_text() + "\n"

    # Limit text length
    text = text[:5000]

    # Send to Claude
    return parse_text_with_claude(text)
```

### Example Response

```json
{
  "amount": 49.99,
  "type": "cost",
  "cost_category": "operations",
  "currency": "USD",
  "explanation": "Monthly server hosting",
  "tags": ["hosting", "infrastructure"],
  "vendor_name": "DigitalOcean",
  "invoice_number": "INV-2024-12345",
  "expense_date": "2024-01-15"
}
```

### Error Handling

| Error | Handling |
|-------|----------|
| Invalid JSON from Claude | Show error message, allow manual entry |
| Missing required fields | Use defaults (amount=0, type="cost") |
| PDF text extraction fails | Show error, suggest manual entry |
| Claude API rate limit | Show error with retry option |
| Empty PDF content | Show error, suggest manual entry |

## API Endpoints for Phase 1

### POST /api/parse-text
Parse email text with Claude AI.

**Request:**
```json
{
  "text": "Your monthly invoice for $49.99..."
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "amount": 49.99,
    "type": "cost",
    "cost_category": "operations",
    "currency": "USD",
    "explanation": "Monthly invoice",
    "tags": ["subscription"],
    "vendor_name": "Example Corp",
    "invoice_number": "12345",
    "expense_date": "2024-01-15"
  }
}
```

### POST /api/parse-pdf
Parse uploaded PDF with Claude AI.

**Request:** `multipart/form-data`
- `file`: PDF file

**Response:**
```json
{
  "success": true,
  "data": {
    "amount": 149.00,
    "type": "cost",
    "cost_category": "operations",
    "currency": "USD",
    "explanation": "Cloud services",
    "tags": ["cloud", "infrastructure"],
    "vendor_name": "AWS",
    "invoice_number": "INV-2024-001",
    "expense_date": "2024-01-10"
  },
  "filename": "aws-invoice.pdf"
}
```

### POST /api/expenses
Create a new expense (used for all input methods).

**Request:**
```json
{
  "amount": 49.99,
  "type": "cost",
  "cost_category": "operations",
  "currency": "USD",
  "explanation": "Monthly hosting",
  "tags": ["hosting"],
  "vendor_name": "DigitalOcean",
  "invoice_number": "INV-12345",
  "expense_date": "2024-01-15",
  "source_type": "email_text",
  "attachment_data": "<base64 encoded PDF>",
  "attachment_filename": "invoice.pdf"
}
```

**Response:** Created expense object

## UI Components

### Add Expense Button Group

```
┌────────────────┐ ┌──────────────┐ ┌────────────┐
│ + Add Manually │ │ Paste Email  │ │ Upload PDF │
└────────────────┘ └──────────────┘ └────────────┘
```

### Shared Edit/Review Modal

The same modal component is used for:
- Manual entry (blank form)
- Review after text parsing (pre-filled)
- Review after PDF parsing (pre-filled + attachment)
- Editing existing expenses

Fields:
- Amount (number, required)
- Type (dropdown: income/cost, required)
- Category (dropdown: operations/freelancers/equipment/other) - only shown for costs
- Currency (text, 3 chars)
- Vendor Name (text)
- Explanation (textarea)
- Tags (comma-separated)
- Expense Date (date picker)
- Invoice Number (text)

## Testing Checklist

### Manual Entry
- [ ] Open modal with blank form
- [ ] Fill all fields
- [ ] Save expense
- [ ] Verify expense appears in list with formatted amount
- [ ] Edit the expense

### Paste Email Text
- [ ] Paste sample invoice email
- [ ] Click parse, see loading state
- [ ] Verify fields are pre-filled correctly
- [ ] Edit a field before saving
- [ ] Save and verify in list

### Upload PDF
- [ ] Drag PDF onto drop zone
- [ ] Verify auto-upload starts immediately
- [ ] See loading state while parsing
- [ ] Verify fields are pre-filled correctly
- [ ] Verify PDF is attached
- [ ] Save and verify in list
- [ ] Download attached PDF
- [ ] Test with non-PDF file (should reject)
- [ ] Test with empty/corrupted PDF (should handle gracefully)

### Number Formatting
- [ ] Verify amounts show thousands separators (e.g., 1,000.00)
- [ ] Verify stats cards use formatted numbers
- [ ] Verify expense list uses formatted numbers
