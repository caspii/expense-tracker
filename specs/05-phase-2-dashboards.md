# Phase 2: Dashboards & Reporting (Future)

This phase adds comprehensive reporting and visualization features to help track income, expenses, and tax obligations over time.

**Status:** Not yet implemented. This document describes the planned functionality.

## Overview

```
┌─────────────────────────────────────────────────────────────┐
│  📊 Expense Tracker - Dashboard                             │
├─────────────────────────────────────────────────────────────┤
│  Period: [2024 ▼]  [January ▼]  [All Categories ▼]         │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐           │
│  │   INCOME    │ │    COSTS    │ │     NET     │           │
│  │  €12,500    │ │   €4,200    │ │   €8,300    │           │
│  └─────────────┘ └─────────────┘ └─────────────┘           │
├─────────────────────────────────────────────────────────────┤
│  Costs by Category          │  Monthly Trend               │
│  ┌────────────────────────┐ │  ┌────────────────────────┐  │
│  │ ████████ Operations    │ │  │     📈                 │  │
│  │ ████ Freelancers       │ │  │   Income vs Costs      │  │
│  │ ██ Equipment           │ │  │   over time            │  │
│  │ █ Other                │ │  │                        │  │
│  └────────────────────────┘ │  └────────────────────────┘  │
├─────────────────────────────────────────────────────────────┤
│  Tax Summary                                                │
│  Estimated tax (19%): €1,577                               │
│  Net after tax: €6,723                                     │
└─────────────────────────────────────────────────────────────┘
```

## Features

### Time Period Selection

- **Year selector** - View full year summaries
- **Month selector** - Drill down to specific months
- **Custom date range** - Select arbitrary start/end dates
- **Quick filters** - "This month", "Last month", "This quarter", "YTD"

### Financial Summaries

| Metric | Description |
|--------|-------------|
| Total Income | Sum of all confirmed income for period |
| Total Costs | Sum of all confirmed costs for period |
| Net Profit | Income minus costs |
| By Category | Costs broken down by operations/freelancers/equipment/other |

### Tax Calculation

- **Configurable tax rate** - User sets their tax rate (e.g., 19%)
- **Estimated tax** - Net profit × tax rate
- **Net after tax** - Net profit minus estimated tax
- **Quarterly estimates** - For quarterly tax payments

### Visualizations

#### Costs by Category (Pie/Bar Chart)
- Visual breakdown of spending by category
- Shows percentage and absolute amounts
- Click to filter expense list

#### Monthly Trend (Line Chart)
- Income vs costs over time
- Net profit trend line
- Compare to previous year (optional)

#### Top Vendors
- Highest spending vendors
- Sortable by total or count
- Click to see all expenses from vendor

### Filtering & Search

- **By category** - operations, freelancers, equipment, other
- **By vendor** - Filter to specific vendor
- **By amount** - Min/max range
- **By status** - Draft or confirmed
- **Text search** - Search in explanation, vendor name, tags

### Export Options

- **CSV export** - Download filtered expenses as spreadsheet
- **PDF report** - Generate printable financial summary
- **Copy to clipboard** - Quick copy of summary stats

## API Endpoints

### GET /api/reports/summary
Get financial summary for a time period.

**Query Parameters:**
- `year` (required) - Year to report on
- `month` (optional) - Specific month (1-12), omit for full year
- `start_date` (optional) - Custom start date (YYYY-MM-DD)
- `end_date` (optional) - Custom end date (YYYY-MM-DD)

**Response:**
```json
{
  "period": {
    "start": "2024-01-01",
    "end": "2024-01-31",
    "label": "January 2024"
  },
  "income": {
    "total": 12500.00,
    "count": 5
  },
  "costs": {
    "total": 4200.00,
    "count": 23,
    "by_category": {
      "operations": 2100.00,
      "freelancers": 1500.00,
      "equipment": 400.00,
      "other": 200.00
    }
  },
  "net": 8300.00,
  "tax": {
    "rate": 0.19,
    "estimated": 1577.00,
    "net_after_tax": 6723.00
  }
}
```

### GET /api/reports/trend
Get monthly trend data for charts.

**Query Parameters:**
- `year` (required) - Year to report on
- `compare_year` (optional) - Previous year to compare

**Response:**
```json
{
  "year": 2024,
  "months": [
    {
      "month": 1,
      "label": "Jan",
      "income": 12500.00,
      "costs": 4200.00,
      "net": 8300.00
    },
    {
      "month": 2,
      "label": "Feb",
      "income": 8000.00,
      "costs": 3100.00,
      "net": 4900.00
    }
  ],
  "compare_year": null
}
```

### GET /api/reports/vendors
Get top vendors by spending.

**Query Parameters:**
- `year` (optional) - Filter by year
- `month` (optional) - Filter by month
- `limit` (optional) - Number of vendors (default 10)
- `cost_category` (optional) - Filter by category

**Response:**
```json
{
  "vendors": [
    {
      "name": "AWS",
      "total": 1200.00,
      "count": 12,
      "category": "operations"
    },
    {
      "name": "John Doe (Freelancer)",
      "total": 800.00,
      "count": 2,
      "category": "freelancers"
    }
  ]
}
```

### GET /api/settings/tax
Get tax settings.

**Response:**
```json
{
  "tax_rate": 0.19,
  "currency": "EUR"
}
```

### PUT /api/settings/tax
Update tax settings.

**Request:**
```json
{
  "tax_rate": 0.19,
  "currency": "EUR"
}
```

## UI Components

### Period Selector

```
┌──────────────────────────────────────────────────────┐
│ Year: [2024 ▼]  Month: [All ▼]  Category: [All ▼]   │
│ Quick: [This Month] [Last Month] [This Quarter] [YTD]│
└──────────────────────────────────────────────────────┘
```

### Summary Cards

```
┌─────────────┐ ┌─────────────┐ ┌─────────────┐
│   INCOME    │ │    COSTS    │ │     NET     │
│  €12,500    │ │   €4,200    │ │   €8,300    │
│   5 items   │ │  23 items   │ │             │
│   +15% ↑    │ │   -8% ↓     │ │   +25% ↑    │
└─────────────┘ └─────────────┘ └─────────────┘
    (green)        (red)          (blue)
```

- Optional: Show comparison to previous period

### Tax Summary Card

```
┌─────────────────────────────────────────┐
│  TAX SUMMARY                            │
│  ─────────────────────────────────────  │
│  Tax rate:           19%                │
│  Estimated tax:      €1,577             │
│  Net after tax:      €6,723             │
│                                         │
│  [⚙ Settings]                          │
└─────────────────────────────────────────┘
```

### Category Breakdown

```
┌─────────────────────────────────────────┐
│  COSTS BY CATEGORY                      │
│  ─────────────────────────────────────  │
│  ████████████████ Operations   €2,100   │
│  ████████████ Freelancers      €1,500   │
│  ████ Equipment                €400     │
│  ██ Other                      €200     │
└─────────────────────────────────────────┘
```

## Database Changes

### Settings Table (New)

```sql
CREATE TABLE settings (
    key VARCHAR(50) PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Default settings
INSERT INTO settings (key, value) VALUES
    ('tax_rate', '0.19'),
    ('currency', 'EUR');
```

## Configuration

### New Environment Variables

```bash
# Default tax rate (can be changed in UI)
DEFAULT_TAX_RATE=0.19

# Default currency for display
DEFAULT_CURRENCY=EUR
```

## Testing Checklist

- [ ] Year selector shows correct totals
- [ ] Month selector filters correctly
- [ ] Category breakdown matches expense list
- [ ] Tax calculation is accurate
- [ ] Trend chart renders correctly
- [ ] Export CSV contains correct data
- [ ] Settings persist after reload
- [ ] Comparison to previous period works
- [ ] Quick filters work correctly
