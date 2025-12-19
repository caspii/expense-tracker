# Troubleshooting

## Common Issues

### AI Parsing Errors

**Symptoms:** AI returns empty fields or wrong data

**Checks:**
1. Verify `ANTHROPIC_API_KEY` is correct
2. Check API key has credits at [console.anthropic.com](https://console.anthropic.com)
3. Review logs for rate limiting
4. Test with simple, clear invoice text

**Common Causes:**
- Invalid API key → "401 Unauthorized"
- No credits → "402 Payment Required"
- Rate limited → Wait and retry
- Very long text → Content truncated, important info may be cut

**Solutions:**
- Verify API key is correct
- Add credits to Anthropic account
- For long documents, key expense info should be near the beginning

### PDF Parsing Issues

**Symptoms:** PDF upload returns empty or wrong data

**Checks:**
1. Is the PDF text-based (not scanned image)?
2. Is the text extractable?
3. Is the file actually a PDF?

**Common Causes:**
- Scanned PDF (image-based) → Text extraction fails
- Password-protected PDF → Cannot read
- Corrupted file → Extraction error

**Solutions:**
- Use text-based PDFs when possible
- For scanned documents, use OCR first (future enhancement)
- Try re-saving the PDF
- Enter data manually if extraction fails

### Database Errors

**Symptoms:** 500 errors, can't save expenses

**Checks:**
1. Verify `DATABASE_URL` is set correctly
2. Check if database was initialized with `db.create_all()`
3. Review Railway Postgres logs
4. Check disk space (rare on Railway)

**Common Issues:**
- Tables not created → Run migration: `db.create_all()`
- Connection pool exhausted → Restart app
- Invalid connection string → Check URL format

**Solutions:**
```bash
# Initialize database
railway run python
>>> from app import app, db
>>> with app.app_context():
...     db.create_all()
>>> exit()
```

### UI Not Loading

**Symptoms:** Blank page or 404 errors

**Checks:**
1. Verify app is running in Railway dashboard
2. Check build logs for errors
3. Test API directly: `/api/expenses`
4. Open browser console for JavaScript errors

**Common Issues:**
- Missing templates folder → Check Git
- JavaScript error → Check browser console
- API endpoint wrong → Check fetch() URLs

### Railway Deployment Issues

**Symptoms:** App not deploying or crashing

**Checks:**
1. Review deploy logs in Railway dashboard
2. Check for missing environment variables
3. Verify Procfile exists and is correct

**Common Issues:**
- Missing dependency → Add to requirements.txt
- Wrong Python version → Add runtime.txt
- Procfile syntax error → Should be `web: gunicorn app:app`

## Debugging Steps

### Check Logs

```bash
# Railway CLI
railway logs

# Or in Railway dashboard:
# Project → Deployments → View logs
```

### Test API Endpoints

```bash
# Health check
curl https://your-app.railway.app/api/stats

# Create test expense
curl -X POST https://your-app.railway.app/api/expenses \
  -H "Content-Type: application/json" \
  -d '{"amount": 1, "type": "cost", "source_type": "manual"}'

# Test AI parsing
curl -X POST https://your-app.railway.app/api/parse-text \
  -H "Content-Type: application/json" \
  -d '{"text": "Invoice for $50 from Test Company"}'
```

### Verify Environment Variables

```bash
# List all variables
railway variables

# Check specific variable (masked)
railway run printenv | grep ANTHROPIC
```

### Database Inspection

```bash
# Connect to database
railway run python
>>> from app import app, db, Expense
>>> with app.app_context():
...     print(Expense.query.count())
...     print(Expense.query.first().to_dict() if Expense.query.first() else "No expenses")
>>> exit()
```

## Error Messages Reference

| Error | Meaning | Solution |
|-------|---------|----------|
| "401 Unauthorized" (Claude) | Invalid API key | Check ANTHROPIC_API_KEY |
| "402 Payment Required" | No API credits | Add credits in Anthropic Console |
| "429 Too Many Requests" | Rate limited | Wait and retry |
| "500 Internal Server Error" | Server error | Check logs for details |
| "Connection refused" | Database down | Check DATABASE_URL |
| "No such table: expenses" | Not initialized | Run db.create_all() |

## Getting Help

### Collect Information

Before seeking help, gather:
1. Error message (exact text)
2. What you were trying to do
3. Railway logs (last 50 lines)
4. Browser console errors (if UI issue)

### Resources

- Railway Documentation: [docs.railway.app](https://docs.railway.app)
- Flask Documentation: [flask.palletsprojects.com](https://flask.palletsprojects.com)
- Anthropic Documentation: [docs.anthropic.com](https://docs.anthropic.com)
