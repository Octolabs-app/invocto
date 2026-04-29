#!/bin/bash
# ─────────────────────────────────────────────────────────────────
# Tax-Ready Invoice — One-click Setup Script
# ─────────────────────────────────────────────────────────────────
set -e

echo "🚀 Setting up Tax-Ready Invoice..."

# 1. Create virtual environment
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# 2. Activate virtual environment
source venv/bin/activate

# 3. Upgrade pip
pip install --upgrade pip -q

# 4. Install dependencies
echo "📥 Installing dependencies..."
pip install -r requirements.txt -q

# 5. Create .env if it doesn't exist
if [ ! -f ".env" ]; then
    echo "🔑 Creating .env from template..."
    cp .env.example .env
    # Auto-generate a SECRET_KEY
    SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    sed -i "s/change-me-to-a-long-random-string/$SECRET/" .env
    echo "✅ .env created with a random SECRET_KEY"
    echo "👉 Add your GEMINI_API_KEY to .env for AI categorization (optional)"
fi

echo ""
echo "✅ Setup complete!"
echo ""
echo "▶  To start the server:"
echo "   source venv/bin/activate"
echo "   uvicorn app.main:app --reload"
echo ""
echo "🌐 Then open: http://localhost:8000"
