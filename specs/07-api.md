# REST API Specification

## Base URL

- Local: `http://localhost:5055`
- Production: `https://your-app.railway.app`

## Endpoints

### Expenses

#### GET /api/expenses
List all expenses with optional filters.

**Query Parameters:**
- `status` (optional) - "draft" or "confirmed"
- `type` (optional) - "income" or "cost"
- `cost_category` (optional) - "operations", "freelancers", "equipment", "other"
- `source_type` (optional) - "manual", "email_text", "pdf_upload"

**Response:**
```json
[
  {
    "id": 1,
    "amount": 49.99,
    "type": "cost",
    "cost_category": "operations",
    "currency": "USD",
    "explanation": "Monthly hosting",
    "tags": ["hosting"],
    "status": "draft",
    "source_type": "pdf_upload",
    "sender_email": "billing@example.com",
    "sender_domain": "example.com",
    "vendor_name": "Example Inc",
    "email_subject": "Invoice #12345",
    "invoice_number": "INV-12345",
    "payment_status": "paid",
    "has_attachments": true,
    "attachment_filename": "invoice.pdf",
    "expense_date": "2024-01-15",
    "created_at": "2024-01-15T10:45:00Z"
  }
]
```

#### GET /api/expenses/:id
Get single expense details.

**Response:** Same as single item from list above

#### POST /api/expenses
Create a new expense.

**Request Body:**
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
  "payment_status": "paid",
  "expense_date": "2024-01-15",
  "source_type": "manual",
  "attachment_data": "<base64 encoded PDF>",
  "attachment_filename": "invoice.pdf"
}
```

**Response:** Created expense object with id

#### PUT /api/expenses/:id
Update an expense.

**Request Body:**
```json
{
  "amount": 59.99,
  "type": "cost",
  "cost_category": "freelancers",
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

### Attachments

#### GET /api/expenses/:id/pdf
Download PDF attachment.

**Response:**
- Content-Type: application/pdf
- Binary PDF data
- Filename in Content-Disposition header

**Error:** 404 if no attachment

### AI Parsing

#### POST /api/parse-text
Parse email/document text with Claude AI.

**Request Body:**
```json
{
  "text": "Your monthly invoice for $49.99 is ready...",
  "subject": "Invoice #12345"
}
```

**Response (Success):**
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
    "payment_status": "unpaid",
    "expense_date": "2024-01-15"
  }
}
```

**Response (Error):**
```json
{
  "success": false,
  "error": "Failed to parse text: Invalid response from AI"
}
```

#### POST /api/parse-pdf
Parse uploaded PDF with Claude AI.

**Request:** `multipart/form-data`
- `file`: PDF file (required)

**Response (Success):**
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
    "payment_status": "paid",
    "expense_date": "2024-01-10"
  },
  "filename": "aws-invoice.pdf",
  "file_data": "<base64 encoded PDF>"
}
```

**Response (Error):**
```json
{
  "success": false,
  "error": "Failed to parse PDF: Could not extract text"
}
```

### Statistics

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

## Error Responses

All errors follow this format:

```json
{
  "error": "Description of what went wrong"
}
```

### HTTP Status Codes

| Code | Meaning |
|------|---------|
| 200 | Success |
| 201 | Created |
| 204 | No Content (successful delete) |
| 400 | Bad Request (invalid input) |
| 404 | Not Found |
| 500 | Internal Server Error |

## Testing Examples

```bash
# Get all expenses
curl http://localhost:5055/api/expenses

# Get drafts only
curl http://localhost:5055/api/expenses?status=draft

# Get stats
curl http://localhost:5055/api/stats

# Create expense manually
curl -X POST http://localhost:5055/api/expenses \
  -H "Content-Type: application/json" \
  -d '{
    "amount": 99.99,
    "type": "cost",
    "cost_category": "operations",
    "currency": "USD",
    "vendor_name": "Test Vendor",
    "explanation": "Test expense",
    "source_type": "manual"
  }'

# Filter by cost category
curl http://localhost:5055/api/expenses?cost_category=freelancers

# Update expense
curl -X PUT http://localhost:5055/api/expenses/1 \
  -H "Content-Type: application/json" \
  -d '{"amount": 79.99}'

# Confirm expense
curl -X POST http://localhost:5055/api/expenses/1/confirm

# Delete expense
curl -X DELETE http://localhost:5055/api/expenses/1

# Parse text
curl -X POST http://localhost:5055/api/parse-text \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Invoice for $49.99 from DigitalOcean for monthly hosting.",
    "subject": "Your DigitalOcean Invoice"
  }'

# Parse PDF
curl -X POST http://localhost:5055/api/parse-pdf \
  -F "file=@/path/to/invoice.pdf"

# Download PDF
curl http://localhost:5055/api/expenses/1/pdf --output invoice.pdf
```
