# Expense Tracker

Simple Flask app to track business expenses by parsing forwarded emails.

## Features

- 📧 Auto-parse expenses from forwarded emails (IMAP + Claude API)
- 💰 Track income and costs with currency, tags, explanations
- 📎 Store PDF attachments (invoices, bills)
- ✅ Review draft entries before confirming
- 📊 Simple stats dashboard
- 🏢 Track vendor spending

## Setup

### 1. Gmail Setup

1. Create a new Gmail account for expenses (e.g., `myexpenses@gmail.com`)
2. Enable 2FA on the account
3. Generate an App Password:
   - Go to Google Account > Security > 2-Step Verification > App passwords
   - Create a new app password for "Mail"
   - Save this password for later

### 2. Get Anthropic API Key

1. Sign up at https://console.anthropic.com
2. Create an API key
3. Save it for later

### 3. Local Development

```bash
# Clone or download this project
cd expense-tracker

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy .env.example to .env and fill in your values
cp .env.example .env

# Edit .env with your credentials:
# - SECRET_KEY (generate random string)
# - EMAIL_ADDRESS (your Gmail)
# - EMAIL_PASSWORD (Gmail app password)
# - ANTHROPIC_API_KEY (Claude API key)

# Run migrations
python
>>> from app import app, db
>>> with app.app_context():
...     db.create_all()
>>> exit()

# Run the app
python app.py
```

Visit http://localhost:5055

### 4. Deploy to Railway

1. Push code to GitHub:
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   git remote add origin YOUR_GITHUB_REPO_URL
   git push -u origin main
   ```

2. Deploy on Railway:
   - Go to https://railway.app
   - Click "New Project" > "Deploy from GitHub"
   - Select your repository
   - Railway will auto-detect the Procfile and deploy

3. Add Postgres:
   - In your Railway project, click "New" > "Database" > "PostgreSQL"
   - Railway automatically sets DATABASE_URL environment variable

4. Set Environment Variables:
   - In Railway project settings > Variables
   - Add:
     - `SECRET_KEY` (random string)
     - `EMAIL_ADDRESS` (your Gmail)
     - `EMAIL_PASSWORD` (Gmail app password)
     - `ANTHROPIC_API_KEY` (Claude API key)
   - Railway provides `DATABASE_URL` automatically

5. Get your URL:
   - Railway will give you a URL like `https://your-app.railway.app`

### 5. Initialize Database

After first deploy:
```bash
# Install Railway CLI: https://docs.railway.app/develop/cli
railway login
railway link  # Link to your project

# Run database migration
railway run python
>>> from app import app, db
>>> with app.app_context():
...     db.create_all()
>>> exit()
```

## Usage

1. **Forward emails to your Gmail expense account**
   - Forward invoices, bills, receipts to the Gmail you configured
   - App checks every 15 minutes automatically
   - Or click "Check Emails Now" button for instant check

2. **Review drafts**
   - New expenses appear as "Drafts"
   - Edit any incorrect data
   - Click ✓ to confirm or × to delete

3. **View stats**
   - Dashboard shows income, costs, net
   - Top vendors by spending
   - All confirmed expenses

## Email Forwarding Tips

- Forward from any email account to your expense tracker Gmail
- Works with:
  - Invoice emails from vendors
  - Bill notifications
  - Receipt emails
  - Bank statements
- PDFs are automatically extracted and stored

## API Endpoints

- `GET /api/expenses` - List expenses (filter by ?status=draft or ?type=income)
- `GET /api/expenses/<id>` - Get expense details
- `PUT /api/expenses/<id>` - Update expense
- `DELETE /api/expenses/<id>` - Delete expense
- `POST /api/expenses/<id>/confirm` - Confirm draft
- `GET /api/expenses/<id>/pdf` - Download PDF attachment
- `GET /api/stats` - Get statistics
- `POST /api/check-emails` - Manually trigger email check

## Tech Stack

- **Backend**: Flask, SQLAlchemy
- **Database**: PostgreSQL
- **Email**: IMAP (Gmail)
- **AI**: Claude API (Anthropic)
- **Hosting**: Railway
- **Scheduler**: APScheduler

## Cost Estimate

- **Railway**: ~$5-10/month (includes Postgres)
- **Claude API**: ~$0.01-0.05 per email parsed (very cheap)
- **Gmail**: Free

## Troubleshooting

**Emails not being parsed:**
- Check Railway logs for errors
- Verify Gmail credentials are correct
- Ensure Gmail app password (not regular password)
- Check if 2FA is enabled on Gmail

**Database errors:**
- Run `db.create_all()` to create tables
- Check DATABASE_URL is set correctly

**Claude API errors:**
- Verify ANTHROPIC_API_KEY is correct
- Check API key has credits
- Review Railway logs for specific errors

## Security Notes

- Never commit `.env` file (in .gitignore)
- Use strong SECRET_KEY in production
- Gmail app password is safer than regular password
- Railway environment variables are encrypted
