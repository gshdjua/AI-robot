# 🛍️ CommerceBot — AI Shopping Assistant

An AI-powered commerce chatbot that helps customers **search**, **compare**, and **purchase** products — with full observability, evaluation, and Stripe payment integration.

Built for the [GenAI Course Project](PROJECT.MD).

---

## ✨ Features

- **🤖 AI Chat Agent** — Natural language product search, comparison, and purchase flow
- **🔍 Product Search** — Semantic + keyword search across 20 products in 4 categories
- **📊 Product Comparison** — Side-by-side spec comparison with best-value recommendations
- **💳 Stripe Checkout** — Secure payment via Stripe Checkout Sessions (test mode)
- **📈 Observability Dashboard** — Real-time KPIs, latency tracking, token usage, intent distribution
- **🧪 Evaluation Dashboard** — RAGAS metrics (faithfulness, relevancy, precision, recall) + commerce KPIs
- **🔗 Langfuse Integration** — Full LLM tracing and observability (configurable)

---

## 🏗️ Architecture

```
Frontend (HTML/CSS/JS) ←→ Backend (FastAPI) ←→ LLM (Claude/GPT)
                              ↓
                    ┌─────────┼──────────┐
                    ↓         ↓           ↓
              Products    Stripe      Langfuse
              (JSON)     (Payments)   (Traces)
```

### Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **k=5 product retrieval** | Balances choice satisfaction vs. decision paralysis (Iyengar & Lepper, 2000) |
| **RAGAS evaluation** | Gold standard for RAG quality: faithfulness, relevancy, precision, recall |
| **Stripe Checkout Sessions** | Hosted payment page — minimal PCI burden, polished UX |
| **Langfuse** | Open-source, purpose-built for LLM observability with evaluation support |
| **FastAPI** | Async streaming, auto-generated docs, strong ML/AI ecosystem |

### Evaluation Metrics

- **Faithfulness** — Prevents hallucinated prices/specs (critical for commerce trust)
- **Answer Relevancy** — Ensures agent stays on shopping intent
- **Context Precision/Recall** — Validates retrieval quality at k=5
- **Conversion Rate** — Primary business KPI: conversations → purchases
- **Average Comparison Depth** — Engagement quality proxy (comparing ≥2 = 3x purchase likelihood)

---

## 🚀 Quick Start

### Prerequisites

- Python 3.10+
- (Optional) Anthropic or OpenAI API key for LLM features
- (Optional) Stripe test account for real checkout
- (Optional) Langfuse account for observability

### Installation

```bash
# Clone or navigate to project directory
cd project

# Install dependencies
pip install -r backend/requirements.txt

# Run the server
python run.py
```

### Configuration (Optional)

Set environment variables for full functionality:

```bash
# LLM (at least one required for AI chat; falls back to mock mode)
export ANTHROPIC_API_KEY="sk-ant-..."    # For Claude
export OPENAI_API_KEY="sk-..."           # For GPT

# Stripe (for real checkout; falls back to demo mode)
export STRIPE_SECRET_KEY="sk_test_..."

# Langfuse (for observability; falls back to local logging)
export LANGFUSE_PUBLIC_KEY="pk-..."
export LANGFUSE_SECRET_KEY="sk-..."
```

### Usage

1. Open **http://localhost:8000** — the chat interface loads
2. Try: *"Show me laptops under $1500"* or *"Compare MacBook Air M4 vs Dell XPS 15"*
3. Click **Buy Now** on any product card to test Stripe checkout
4. View **Observability Dashboard** at `/dashboards/observability.html`
5. View **Evaluation Dashboard** at `/dashboards/evaluation.html`
6. Run evaluation suite: `python evaluation/evaluate.py`

---

## 📁 Project Structure

```
project/
├── backend/
│   ├── main.py              # FastAPI app, routes, middleware
│   ├── agent.py             # Chat agent with LLM orchestration & tool calling
│   ├── products.py          # Product search, retrieval, comparison
│   ├── payment.py           # Stripe checkout session management
│   ├── models.py            # Pydantic request/response schemas
│   ├── database.py          # SQLite persistence (orders, conversations, metrics)
│   ├── observability.py     # Langfuse tracing integration
│   └── requirements.txt     # Python dependencies
├── frontend/
│   ├── index.html           # Main chat interface
│   ├── style.css            # Styling (dark theme, responsive)
│   ├── app.js               # Chat logic, product cards, checkout flow
│   ├── checkout-demo.html   # Demo checkout page (no Stripe key needed)
│   ├── checkout-success.html# Payment success page
│   └── checkout-cancel.html # Payment cancel page
├── dashboards/
│   ├── observability.html   # KPI dashboard with Chart.js visualizations
│   └── evaluation.html      # RAGAS + commerce metrics dashboard
├── evaluation/
│   ├── evaluate.py          # RAGAS evaluation runner
│   ├── metrics.py           # Custom commerce KPIs
│   └── test_cases.json      # Ground-truth test cases
├── data/
│   └── products.json        # 20-product catalog (4 categories)
├── run.py                   # Application entry point
├── PROJECT.MD               # Course project specification
└── README.md                # This file
```

---

## 🧪 Testing

### Test Cards (Stripe Test Mode)

| Scenario | Card Number |
|----------|-------------|
| Success | `4242 4242 4242 4242` |
| Auth Required | `4000 0027 6000 3184` |
| Declined | `4000 0000 0000 0002` |

Use any future expiry date and any 3-digit CVC.

### Evaluation Suite

```bash
python evaluation/evaluate.py
```

Runs 12 test cases across RAGAS metrics and custom commerce KPIs.

---

## 📋 Presentation Notes

### 10-Minute Demo Flow

1. **Intro (1 min)** — CommerceBot solves product discovery + purchase in chat
2. **Live Demo (4 min)** — Search → Compare → Buy flow
3. **Design Decisions (2 min)** — Why k=5, why these metrics, why Stripe Checkout
4. **Dashboards (2 min)** — Observability (traces, latency, tokens) + Evaluation (RAGAS scores)
5. **Q&A / Next Steps (1 min)** — What we'd add with more time

### "With More Time, We Would..."

- Add semantic embedding search (FAISS/Chroma) for better retrieval
- Implement true LLM-as-judge RAGAS evaluation with GPT-4/Claude
- Add A/B testing framework for prompt iteration
- Deploy Langfuse self-hosted for production observability
- Add Stripe webhook handling for real payment status updates
- Implement user authentication and order history
- Add multi-language support (Chinese, Spanish, etc.)
- Integrate real product APIs (Shopify, Amazon, etc.)
