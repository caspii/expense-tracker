# Expense Tracker - Overview

## Motivation

As a solo business owner, I need to know at a glance how much I've earned and spent in any given month or year—primarily to understand my tax obligations. Manually tracking expenses in spreadsheets is tedious and error-prone, especially when most financial documents arrive as emails or PDF invoices.

This app solves these problems by:

- **Quick financial overview** - See income, costs, and net profit for any time period
- **Tax-ready reporting** - Know exactly how much you owe at tax time
- **Multiple input methods** - Enter manually, paste email text, or upload PDFs
- **AI-powered extraction** - Claude API extracts structured data from unstructured documents
- **Draft review workflow** - Review and correct AI-extracted data before confirming
- **Simple interface** - Clean web UI focused on the essentials
- **Minimal maintenance** - Serverless-style hosting requires zero server management

## Goals

1. **Simplicity** - Easy to set up, easy to use, minimal features
2. **Flexibility** - Multiple ways to add expenses (manual, paste, upload)
3. **Reliability** - Store data safely in Postgres, keep PDF attachments
4. **Low cost** - Under $10/month total operating cost
5. **Personal use** - Single user, no authentication needed

## Non-Goals

- Multi-user support or authentication
- Complex accounting features (depreciation, accrual, etc.)
- Integration with accounting software
- Mobile apps (web UI works on mobile)

## Implementation Phases

### Phase 1: Manual Input (Current)
- Manual expense entry via form
- Paste email text for AI parsing
- Upload PDF for AI parsing
- Draft/confirm workflow
- Basic statistics

### Phase 2: Dashboards & Reporting (Future)
- Monthly and yearly financial summaries
- Income vs costs breakdown by time period
- Tax calculation helpers
- Filtering and search
- Charts and visualizations

### Phase 3: Email Automation (Future)
- Automatic IMAP email polling
- Background scheduler for email checks
- Email forwarding workflow

## Document Structure

| Document | Description |
|----------|-------------|
| [Architecture](02-architecture.md) | System design and technology stack |
| [Database](03-database.md) | Database schema and field descriptions |
| [Phase 1: Manual Input](04-phase-1-manual-input.md) | Manual entry, paste text, PDF upload |
| [Phase 2: Dashboards](05-phase-2-dashboards.md) | Reporting and financial summaries |
| [Phase 3: Email Automation](06-phase-3-email-automation.md) | Future IMAP integration |
| [API](07-api.md) | REST API specification |
| [UI](08-ui.md) | Web UI specification |
| [Deployment](../DEPLOYMENT.md) | Deployment options (separate document) |
| [Configuration](09-configuration.md) | Environment variables and setup |
| [Security](10-security.md) | Security considerations |
| [Troubleshooting](11-troubleshooting.md) | Common issues and solutions |
| [Future Enhancements](12-future-enhancements.md) | Planned improvements |

## Summary

This expense tracker is designed for **simplicity and personal use**. It provides flexible input methods for tracking business expenses by:

1. **Manual entry** for quick one-off expenses
2. **Paste email text** to extract expense data using Claude AI
3. **Upload PDFs** (invoices, receipts) for AI parsing
4. **Storing structured data** in Postgres with PDF attachments
5. **Providing a clean UI** for review and confirmation
6. **Generating simple stats** for financial overview

The architecture prioritizes **ease of deployment** (Railway) and **low maintenance** (serverless-style, managed services) over scalability or multi-user features.

**Total setup time:** 30-60 minutes
**Monthly cost:** $6-10
**Maintenance:** Minimal (check logs occasionally)

Perfect for freelancers, small business owners, or anyone who wants to simplify expense tracking without complex accounting software.
