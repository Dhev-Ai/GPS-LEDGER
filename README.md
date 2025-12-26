# Neon Ledger · Expense Studio

A hyper-interactive expense tracker built with Streamlit, MySQL, Plotly, and SQLAlchemy. Features live budgets, burn-downs, rich filters, and colorful UI.

## Features

- Fast Streamlit UI with glassy gradient styling.
- MySQL-backed transactions, categories, and budgets.
- Trend bars with 7-day smooth line, category pie, and budget burndown.
- Inline forms to add transactions and monthly budgets.
- Powerful filters (date range, amount, category, payment method).

## Prerequisites

- Python 3.10+
- MySQL 8.x running locally or remotely
- A database user with create/alter privileges for the target schema

## Setup

1. Create the database and user (example):
   ```sql
   CREATE DATABASE expenses CHARACTER SET utf8mb4;
   CREATE USER 'expenses_app'@'%' IDENTIFIED BY 'strong-password';
   GRANT ALL PRIVILEGES ON expenses.* TO 'expenses_app'@'%';
   FLUSH PRIVILEGES;
   ```
2. Copy `.env.example` to `.env` and fill in credentials.
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Run the app:
   ```bash
   streamlit run app.py
   ```

## Environment variables

- `MYSQL_HOST` (default `localhost`)
- `MYSQL_PORT` (default `3306`)
- `MYSQL_USER` (default `root`)
- `MYSQL_PASSWORD`
- `MYSQL_DB` (default `expenses`)

## How it works

- On startup the app auto-creates tables (`categories`, `transactions`, `budgets`).
- Caching is used for reads to keep UI snappy; saving clears caches automatically.
- Plotly renders charts; Streamlit handles layout and theming.

## Next ideas

- Add receipt OCR and auto-tagging.
- Add savings goals and alerts via email/Slack.
- Build export/import (CSV, XLSX) and REST hooks for automation.
