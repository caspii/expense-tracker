# Deployment Guide

This document covers deployment options for the Expense Tracker application.

## Option 1: Railway (Recommended)

### Why Railway?

- Simplest deployment experience
- Managed Postgres included
- Auto-deploys from Git pushes
- Built-in environment variables UI
- ~$5-10/month for everything

### Deployment Steps

#### 1. Prepare Code

```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin YOUR_GITHUB_REPO
git push -u origin main
```

#### 2. Deploy on Railway

1. Go to [railway.app](https://railway.app)
2. Click "New Project" → "Deploy from GitHub"
3. Select your repository
4. Railway auto-detects Python + Procfile

#### 3. Add Postgres Database

1. In your project, click "New" → "Database" → "PostgreSQL"
2. `DATABASE_URL` is automatically set

#### 4. Set Environment Variables

Go to Project → Variables and add:

| Variable | Value |
|----------|-------|
| `SECRET_KEY` | Random 32+ character string |
| `ANTHROPIC_API_KEY` | Your Claude API key |

#### 5. Initialize Database

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

#### 6. Access Your App

Railway provides a URL like: `https://your-app.railway.app`

### Railway Costs

- Hobby plan: $5/month
- Includes Postgres
- Includes traffic (reasonable use)

---

## Option 2: Render

### Overview

- Similar to Railway
- Free tier available (with limitations)
- Good alternative if Railway doesn't work for you

### Deployment Steps

1. Go to [render.com](https://render.com)
2. Connect your GitHub repository
3. Select "Web Service"
4. Configure:
   - Build command: `pip install -r requirements.txt`
   - Start command: `gunicorn app:app`
5. Add Postgres database from Render dashboard
6. Set environment variables
7. Deploy

### Render Costs

- Free tier: Limited hours per month, sleeps after inactivity
- Starter: $7/month for always-on

---

## Option 3: Fly.io

### Overview

- Dockerfile deployment
- Free Postgres (small size)
- CLI-based deployment
- Good for learning infrastructure

### Deployment Steps

#### 1. Install Fly CLI

```bash
# macOS
brew install flyctl

# Linux
curl -L https://fly.io/install.sh | sh
```

#### 2. Create Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .

CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:8080"]
```

#### 3. Deploy

```bash
fly auth login
fly launch
fly postgres create
fly secrets set SECRET_KEY=your-secret-key
fly secrets set ANTHROPIC_API_KEY=your-api-key
fly deploy
```

### Fly.io Costs

- Free tier: 3 shared VMs, 3GB storage
- Postgres: Free for small instances

---

## Option 4: DigitalOcean App Platform

### Overview

- GitHub integration
- Managed Postgres
- More control over resources
- Higher starting cost

### Deployment Steps

1. Go to [cloud.digitalocean.com/apps](https://cloud.digitalocean.com/apps)
2. Click "Create App"
3. Connect GitHub repository
4. Add PostgreSQL database component
5. Configure environment variables
6. Deploy

### DigitalOcean Costs

- Basic: ~$12/month minimum
- Database: Additional ~$15/month
- More expensive but more control

---

## Option 5: Traditional VPS

### Overview

- Most control, most work
- Need to manage: Nginx, systemd, Postgres, SSL
- Cheapest option (~$5/month)
- Best for learning

### Requirements

- VPS (DigitalOcean Droplet, Linode, Vultr, etc.)
- Basic Linux administration skills
- Time to set up and maintain

### Deployment Steps

#### 1. Provision VPS

- Ubuntu 22.04 LTS recommended
- Minimum 1GB RAM, 25GB disk

#### 2. Install Dependencies

```bash
sudo apt update
sudo apt install python3.11 python3.11-venv postgresql nginx certbot python3-certbot-nginx

# Create postgres database
sudo -u postgres createuser expense_user
sudo -u postgres createdb expense_db
sudo -u postgres psql -c "ALTER USER expense_user PASSWORD 'secure_password';"
```

#### 3. Deploy Application

```bash
# Clone repository
git clone YOUR_REPO /var/www/expense-tracker
cd /var/www/expense-tracker

# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Create .env file
cat > .env << EOF
SECRET_KEY=your-secret-key
DATABASE_URL=postgresql://expense_user:secure_password@localhost/expense_db
ANTHROPIC_API_KEY=your-api-key
EOF

# Initialize database
python -c "from app import app, db; app.app_context().push(); db.create_all()"
```

#### 4. Configure Systemd Service

```bash
sudo cat > /etc/systemd/system/expense-tracker.service << EOF
[Unit]
Description=Expense Tracker
After=network.target

[Service]
User=www-data
WorkingDirectory=/var/www/expense-tracker
Environment="PATH=/var/www/expense-tracker/venv/bin"
ExecStart=/var/www/expense-tracker/venv/bin/gunicorn app:app --bind 127.0.0.1:5055
Restart=always

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl enable expense-tracker
sudo systemctl start expense-tracker
```

#### 5. Configure Nginx

```bash
sudo cat > /etc/nginx/sites-available/expense-tracker << EOF
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:5055;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
    }
}
EOF

sudo ln -s /etc/nginx/sites-available/expense-tracker /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

#### 6. Enable SSL

```bash
sudo certbot --nginx -d your-domain.com
```

### VPS Costs

- Droplet: $4-6/month
- Domain: ~$10/year
- Total: ~$5-7/month

---

## Comparison Summary

| Platform | Monthly Cost | Setup Difficulty | Maintenance |
|----------|-------------|------------------|-------------|
| Railway | $5-10 | Easy | None |
| Render | $0-7 | Easy | None |
| Fly.io | $0-5 | Medium | Low |
| DigitalOcean | $25+ | Medium | Low |
| VPS | $5-7 | Hard | High |

## Recommendation

**For most users:** Start with **Railway**. It's the fastest path from code to running app with zero DevOps knowledge required.

**For cost optimization:** Try **Render's free tier** for testing, then upgrade as needed.

**For learning:** Use a **VPS** to understand the full deployment stack.

---

## Post-Deployment Checklist

- [ ] App loads at deployment URL
- [ ] Create test expense manually
- [ ] Test AI parsing (paste text, upload PDF)
- [ ] Verify stats display correctly
- [ ] Check logs for errors
- [ ] Set up monitoring/alerts (optional)
