# Configuration

## Environment Variables

### Required for Phase 1

```bash
# Flask
SECRET_KEY=your-random-secret-key-here-change-this

# Database (auto-provided by Railway)
DATABASE_URL=postgresql://user:pass@host:port/db

# Claude API
ANTHROPIC_API_KEY=sk-ant-api03-...
```

### Required for Phase 2 (Email Automation)

```bash
# Email settings
EMAIL_ADDRESS=expenses@gmail.com
EMAIL_PASSWORD=gmail-app-password-16-chars
EMAIL_IMAP_SERVER=imap.gmail.com  # optional, defaults to Gmail
EMAIL_CHECK_INTERVAL=15  # minutes, optional
```

## Variable Descriptions

| Variable | Required | Description | Example |
|----------|----------|-------------|---------|
| `SECRET_KEY` | Yes | Flask session encryption key | Random 32+ character string |
| `DATABASE_URL` | Yes | PostgreSQL connection string | `postgresql://user:pass@host:5432/db` |
| `ANTHROPIC_API_KEY` | Yes | Claude API key | `sk-ant-api03-...` |
| `EMAIL_ADDRESS` | Phase 2 | Gmail address for email forwarding | `expenses@gmail.com` |
| `EMAIL_PASSWORD` | Phase 2 | Gmail app password (16 chars) | `abcd efgh ijkl mnop` |
| `EMAIL_IMAP_SERVER` | No | IMAP server hostname | `imap.gmail.com` |
| `EMAIL_CHECK_INTERVAL` | No | Minutes between email checks | `15` |

## Example .env File

```bash
# Flask configuration
SECRET_KEY=change-this-to-a-random-string-at-least-32-chars

# Database (Railway provides this automatically)
DATABASE_URL=postgresql://postgres:password@localhost:5432/expenses

# Claude API (required for AI parsing)
ANTHROPIC_API_KEY=sk-ant-api03-your-key-here

# Email settings (Phase 2 only)
# EMAIL_ADDRESS=expenses@gmail.com
# EMAIL_PASSWORD=your-16-char-app-password
# EMAIL_IMAP_SERVER=imap.gmail.com
# EMAIL_CHECK_INTERVAL=15
```

## Database URL Handling

Railway provides `DATABASE_URL` with `postgres://` scheme, but SQLAlchemy requires `postgresql://`. The config handles this automatically:

```python
# config.py
class Config:
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL')

    # Fix Railway's postgres:// vs postgresql://
    if SQLALCHEMY_DATABASE_URI and SQLALCHEMY_DATABASE_URI.startswith('postgres://'):
        SQLALCHEMY_DATABASE_URI = SQLALCHEMY_DATABASE_URI.replace(
            'postgres://', 'postgresql://', 1
        )
```

## Claude API Setup

1. **Sign up** at [console.anthropic.com](https://console.anthropic.com)
2. **Create API key** in the Console
3. **Copy the key** - it starts with `sk-ant-api03-`
4. **Add to environment** as `ANTHROPIC_API_KEY`

### API Key Security

- Never commit API keys to Git
- Use environment variables only
- Regenerate if exposed
- Set up billing alerts in Anthropic Console

## Gmail Setup (Phase 2)

### Prerequisites

1. Gmail account (can be new or existing)
2. Two-factor authentication enabled

### Generate App Password

1. Go to [Google Account Security](https://myaccount.google.com/security)
2. Under "Signing in to Google", click **2-Step Verification**
3. Scroll down and click **App passwords**
4. Select app: "Mail"
5. Select device: "Other (Custom name)" → "Expense Tracker"
6. Click **Generate**
7. Copy the 16-character password (spaces are optional)

### Enable IMAP

1. Go to [Gmail Settings](https://mail.google.com/mail/u/0/#settings/fwdandpop)
2. Click "See all settings"
3. Go to "Forwarding and POP/IMAP" tab
4. Under "IMAP access", select "Enable IMAP"
5. Click "Save Changes"

### Common Issues

| Issue | Solution |
|-------|----------|
| "Invalid credentials" | Use app password, not regular password |
| "IMAP not enabled" | Enable in Gmail settings |
| "Less secure apps" | Not needed with app passwords |
| Spaces in password | Spaces are ignored, include or exclude |

## Local Development Setup

### 1. Create Virtual Environment

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Create .env File

```bash
cp .env.example .env
# Edit .env with your values
```

### 4. Initialize Database

```bash
# Start PostgreSQL locally first, then:
python
>>> from app import app, db
>>> with app.app_context():
...     db.create_all()
>>> exit()
```

### 5. Run Development Server

```bash
python app.py
# Visit http://localhost:5055
```

## Production Configuration

### Railway-Specific

Railway automatically provides:
- `DATABASE_URL` - When you add a Postgres database
- `PORT` - The port to listen on (handled by gunicorn)

You must manually set:
- `SECRET_KEY`
- `ANTHROPIC_API_KEY`
- Email settings (Phase 2)

### Procfile

```
web: gunicorn app:app
```

### Python Version

Create `runtime.txt` if needed:
```
python-3.11.7
```
