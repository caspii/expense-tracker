# Architecture

## High-Level Components

```
┌─────────────────────────────────────────────────────┐
│                    Web Browser                       │
│  ┌───────────────────────────────────────────────┐  │
│  │  Manual Entry  │  Paste Text  │  Upload PDF   │  │
│  └───────────────────────────────────────────────┘  │
└────────────────────────┬────────────────────────────┘
                         │
                         ▼
              ┌──────────────────────┐
              │     Flask App        │
              │  - Web UI            │
              │  - REST API          │
              │  - AI Integration    │
              └──────────┬───────────┘
                         │
          ┌──────────────┼──────────────┐
          ▼              ▼              ▼
    ┌──────────┐  ┌───────────┐  ┌──────────┐
    │ PostgreSQL│  │Claude API │  │  PDF     │
    │ (Data +   │  │ (Parsing) │  │ Storage  │
    │  PDFs)    │  │           │  │ (bytea)  │
    └──────────┘  └───────────┘  └──────────┘
```

## Technology Stack

### Backend
- Python 3.11+
- Flask 3.0 - Web framework
- SQLAlchemy - ORM
- Psycopg2 - Postgres driver

### AI
- Anthropic Claude API (Sonnet 4)

### Database
- PostgreSQL 15+ (managed via Railway)

### Hosting
- Railway.app (recommended)
- Alternatives: Render, Fly.io, DigitalOcean

## Why These Choices?

**Flask** - Simple, lightweight, perfect for single-purpose apps

**Railway** - Zero DevOps, includes Postgres, auto-deploys from Git

**Claude API** - Best-in-class extraction from unstructured text and documents

**Postgres bytea** - Simplest PDF storage (no separate object storage needed)

## File Structure

```
expense-tracker/
├── app.py                 # Main Flask application
│   ├── Routes (/, /api/*)
│   ├── AI parsing endpoints
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
├── ai_parser.py           # AI parsing logic
│   ├── parse_text_with_claude()
│   └── parse_pdf_with_claude()
│
├── templates/
│   └── index.html         # Single-page UI
│
├── specs/                 # Specification documents
│   ├── 01-overview.md
│   ├── 02-architecture.md
│   └── ...
│
├── requirements.txt       # Python dependencies
├── Procfile              # Railway: web: gunicorn app:app
├── .env.example          # Template for .env
├── .gitignore           # Ignore .env, __pycache__, etc.
├── DEPLOYMENT.md        # Deployment guide
└── README.md            # Setup instructions
```

## Dependencies (requirements.txt)

```
Flask==3.0.0
Flask-SQLAlchemy==3.1.1
psycopg2-binary==2.9.9
anthropic==0.18.1
python-dotenv==1.0.0
gunicorn==21.2.0
PyPDF2==3.0.1
```

## Technical Decisions & Rationale

### Why Postgres Bytea vs Object Storage?

**Postgres Bytea (Chosen):**
- Zero additional services
- Atomic transactions (expense + PDF together)
- Backup included with database
- Simpler code
- Database size grows (acceptable for personal use)

**Object Storage (Not Chosen):**
- Better for many/large files
- Separate scaling
- Additional service (S3, R2, B2)
- More complex code

**Verdict:** Most invoices are <2MB. Even 1000 PDFs = 2GB, which is fine for Postgres. Simpler is better.

### Why Claude API vs Open Source Models?

**Claude API (Chosen):**
- Best extraction accuracy
- Zero infrastructure
- Pay per use (~$0.01/document)
- Reliable and fast

**Open Source (Not Chosen):**
- No API costs
- Need to host model
- Lower accuracy
- More code complexity

**Verdict:** $1-5/month in API costs is worth the accuracy and simplicity.

### Why Single-Page UI vs Traditional Forms?

**Single-Page UI (Chosen):**
- Feels faster (no page reloads)
- Better for frequent actions
- Auto-refresh works seamlessly

**Traditional Forms (Not Chosen):**
- Simpler to build
- Works without JavaScript
- Page reloads annoying

**Verdict:** Vanilla JavaScript is simple enough, SPA is better UX.

## Cost Analysis

### Monthly Operating Costs

**Railway:**
- Hobby plan: $5/month
- Postgres: Included
- Traffic: Included (reasonable use)
- Total: **$5/month**

**Claude API:**
- Text/PDF parsing: ~$0.01 per document
- 100 documents/month: **$1/month**
- 500 documents/month: **$5/month**

**Total: $6-10/month** depending on usage volume

### Cost Optimization

- Use Railway free trial initially
- Claude API has generous free tier
- Consider switching to Render free tier for testing
- VPS option: $5/month total (but more work)
