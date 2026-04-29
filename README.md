# 📄 Tax-Ready Invoice

A full-stack web application for creative freelancers to manage clients, invoices, expenses, and generate tax reports — with AI-powered category suggestions.

## ✨ Features

- **Authentication** — Secure signup/login with bcrypt password hashing
- **Client Management** — Add, edit, delete clients
- **Invoice Management** — Create invoices with line items, multi-currency support, auto-generated invoice numbers
- **AI Categorization** — Google Gemini suggests a category (Design, Writing, Video…) based on your line item descriptions
- **Expense Tracking** — Log business expenses by category
- **Tax Reports** — Quarterly income breakdown, net income, estimated tax (25%), CSV & printable PDF download
- **Dashboard** — Summary cards + monthly income bar chart

## 🚀 Quick Start

### Prerequisites
- Python 3.10 or higher
- pip

### Setup (automatic)

```bash
git clone <your-repo>
cd tax_invoice
chmod +x setup.sh
./setup.sh
```

Then start the server:

```bash
source venv/bin/activate
uvicorn app.main:app --reload
```

Open **http://localhost:8000** in your browser.

### Setup (manual)

```bash
cd tax_invoice
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env              # Edit .env and set SECRET_KEY
uvicorn app.main:app --reload
```

## 🔑 Environment Variables

Edit the `.env` file:

| Variable | Description | Required |
|---|---|---|
| `SECRET_KEY` | Random string for JWT signing | ✅ Yes |
| `DATABASE_URL` | SQLite path (default: `sqlite:///./tax_invoice.db`) | No |
| `GEMINI_API_KEY` | Google Gemini API key for AI categories | No |

### Getting a Free Gemini API Key

1. Go to [https://makersuite.google.com/app/apikey](https://makersuite.google.com/app/apikey)
2. Sign in with your Google account
3. Click **Create API Key**
4. Paste the key into your `.env` file as `GEMINI_API_KEY=your_key_here`

> Without a Gemini key, AI categorization is disabled and invoices default to category "Other" — everything else still works perfectly.

## 📁 Project Structure

```
tax_invoice/
├── app/
│   ├── __init__.py
│   ├── main.py           # FastAPI entry point
│   ├── database.py       # SQLAlchemy engine & session
│   ├── models.py         # User, Client, Invoice, LineItem, Expense
│   ├── auth.py           # JWT auth, login/register routes
│   ├── routes/
│   │   ├── dashboard.py  # Dashboard + monthly income API
│   │   ├── clients.py    # Client CRUD
│   │   ├── invoices.py   # Invoice CRUD + AI categorization
│   │   ├── expenses.py   # Expense CRUD
│   │   └── reports.py    # Tax reports + CSV download
│   ├── templates/        # Jinja2 HTML templates
│   └── static/           # CSS & JS
├── requirements.txt
├── .env.example
├── setup.sh
└── README.md
```

## 🌐 Deploying to Render.com

1. Push your code to GitHub
2. Create a new **Web Service** on Render
3. Set **Build Command**: `pip install -r requirements.txt`
4. Set **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
5. Add environment variables in the Render dashboard

## 💡 Tax Report Notes

- The 25% estimated tax rate is a rough estimate — consult a tax professional for your actual rate
- Multi-currency invoices: the tax report only sums USD invoices; convert other currencies manually
- Download CSV for your accountant, or use the Print PDF button (Ctrl+P → Save as PDF)

## 🔒 Security Notes

- Passwords are hashed with bcrypt (never stored in plain text)
- JWT tokens are stored in httpOnly cookies (not accessible via JavaScript)
- All routes require authentication except `/login`, `/register`, `/static`
- Each user can only access their own data (enforced by `user_id` filtering)
