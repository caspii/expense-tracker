# Security Considerations

## What's Secure

| Feature | Security Measure |
|---------|------------------|
| API Keys | Stored in environment variables, not in code |
| HTTPS | Railway provides SSL automatically |
| Database | Managed, backed up, encrypted at rest |
| Gmail | App password used, not main account password |
| Session | Flask SECRET_KEY for session encryption |

## What's Not Secure (By Design)

This application is designed for **personal use only** and intentionally lacks certain security features:

| Feature | Status | Reason |
|---------|--------|--------|
| Authentication | None | Single user, personal use |
| User isolation | None | Single user only |
| API authorization | None | No auth needed for personal use |
| Input sanitization | Basic | Trusted single user |
| Rate limiting | None | Personal use doesn't need it |

## Recommendations

### Keep URL Private

- Don't share your deployment URL publicly
- Don't post in public forums or social media
- Consider using a non-obvious subdomain

### Use Strong SECRET_KEY

Generate a strong random key:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Example output: `a3f2c1d4e5b6a7c8d9e0f1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2`

### Enable Railway Basic Auth (Optional)

Railway supports basic authentication for additional security:

1. Go to your Railway project settings
2. Add environment variables:
   - `BASIC_AUTH_USERNAME=your-username`
   - `BASIC_AUTH_PASSWORD=your-password`
3. Configure in your app or use Railway's built-in feature

### Monitor Access

- Check Railway logs periodically for unusual activity
- Review expense entries for unexpected items
- Monitor API usage in Anthropic Console

## If You Need Authentication

For multi-user or more secure deployments, add Flask-HTTPAuth:

```python
from flask_httpauth import HTTPBasicAuth
from werkzeug.security import generate_password_hash, check_password_hash

auth = HTTPBasicAuth()

users = {
    "admin": generate_password_hash(os.getenv('APP_PASSWORD'))
}

@auth.verify_password
def verify_password(username, password):
    if username in users and check_password_hash(users.get(username), password):
        return username

@app.route('/')
@auth.login_required
def index():
    return render_template('index.html')

@app.route('/api/expenses')
@auth.login_required
def get_expenses():
    # ... existing code
```

Add to requirements.txt:
```
Flask-HTTPAuth==4.8.0
```

## Data Privacy

### What Data is Stored

- Expense amounts and descriptions
- Vendor names and invoice numbers
- PDF attachments (invoices, receipts)
- Email text (when pasted for parsing)

### What Data is Sent to Claude API

- Email text content (limited to 5000 chars)
- Extracted PDF text
- No personal identifiers are required

### Data Retention

- All data stored in PostgreSQL database
- Railway provides automatic backups
- No automatic data deletion (manual only)

## Backup Recommendations

### Railway Automatic Backups

Railway's managed Postgres includes:
- Point-in-time recovery
- Daily snapshots
- Retention based on plan

### Manual Backup

```bash
# Export database
railway run pg_dump > backup.sql

# Or via Railway CLI
railway pg:backup
```

## Incident Response

### If API Key is Exposed

1. **Immediately** regenerate the key in Anthropic Console
2. Update the environment variable in Railway
3. Review API usage logs for unauthorized calls
4. Check for unexpected charges

### If Database is Compromised

1. Change all credentials (DATABASE_URL)
2. Review recent expenses for suspicious entries
3. Restore from backup if needed
4. Rotate SECRET_KEY

### If App URL is Discovered

1. Consider adding basic authentication
2. Monitor for unusual activity
3. If abused, redeploy to a new URL
