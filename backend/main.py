"""
Commerce Agent — FastAPI Application
Main entry point for the backend server.
"""

import os
import uuid
from pathlib import Path
from .observability import get_langfuse_client

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

from .models import (
    ChatRequest, ChatResponse, CheckoutRequest, CheckoutResponse,
    OrderStatus, MetricsResponse, ErrorResponse,
)
from .agent import chat as agent_chat
from .database import (
    init_db, create_conversation, save_message, get_conversation,
    get_order as db_get_order, get_metrics_summary, record_metric,
    create_order,
)
from .payment import create_checkout_session, handle_webhook, get_test_card_info
from .products import search_products, get_product, compare_products

# Initialize FastAPI app
app = FastAPI(
    title="Commerce Agent API",
    description="AI-powered shopping assistant with product search, comparison, and purchase",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

# CORS — allow frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files
STATIC_DIR = Path(__file__).parent.parent
app.mount("/static", StaticFiles(directory=str(STATIC_DIR / "frontend")), name="static")
app.mount("/dashboards", StaticFiles(directory=str(STATIC_DIR / "dashboards")), name="dashboards")


@app.on_event("startup")
async def startup():
    """Initialize database on startup."""
    init_db()
    print("=" * 60)
    print("  Commerce Agent API starting...")
    print(f"  API Docs: http://localhost:8000/api/docs")
    print(f"  Chat UI:  http://localhost:8000/static/index.html")
    print(f"  Dashboards: http://localhost:8000/dashboards/observability.html")
    print("=" * 60)


@app.get("/")
async def root():
    """Redirect to chat interface."""
    return FileResponse(str(STATIC_DIR / "frontend" / "index.html"))


# ── Chat Endpoint ──────────────────────────────────────────────────

@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    """
    Process a chat message through the Commerce Agent.

    Returns the agent's response along with any products mentioned,
    comparisons, or checkout URLs.
    """
    conversation_id = request.conversation_id or f"conv-{uuid.uuid4().hex[:12]}"
    is_new = not request.conversation_id

    try:
        # Get conversation history
        history = []
        if not is_new:
            db_history = get_conversation(conversation_id)
            history = [{"role": h["role"], "content": h["content"]}
                       for h in db_history]
        else:
            create_conversation(conversation_id)

        # Save user message
        save_message(conversation_id, "user", request.message)

        # Process through agent
        result = agent_chat(request.message, history)

        # Save assistant message
        intent = result.get("intent")
        save_message(
            conversation_id,
            "assistant",
            result["message"],
            intent=intent,
            metadata={"products": [p["id"] for p in result.get("products", [])],
                      "trace": result.get("trace_summary", {})},
        )

        # Record metrics
        record_metric("message_processed", 1, {"intent": intent})
        if result.get("trace_summary"):
            ts = result["trace_summary"]
            record_metric("llm_latency_ms", ts.get("duration_ms", 0))
            record_metric("llm_tokens", ts.get("total_tokens", 0))

        response = ChatResponse(
            message=result["message"],
            conversation_id=conversation_id,
            intent=intent,
            products=result.get("products", []),
            comparison=result.get("comparison"),
            checkout_url=result.get("checkout_url"),
        )

        # Log trace summary
        if "trace_summary" in result:
            ts = result["trace_summary"]
            print(f"[Trace {ts['trace_id'][:8]}] {ts['span_count']} spans, "
                  f"{ts['duration_ms']:.1f}ms, {ts['total_tokens']} tokens")
            
        langfuse_client = get_langfuse_client()
        if langfuse_client:
            langfuse_client.flush()

        return response

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Product Endpoints ──────────────────────────────────────────────

@app.get("/products")
async def list_products(
    query: str = "",
    category: str = None,
    min_price: float = None,
    max_price: float = None,
    limit: int = 20,
):
    """Search and list products with optional filters."""
    return search_products(
        query=query,
        category=category,
        min_price=min_price,
        max_price=max_price,
        limit=limit,
    )


@app.get("/products/{product_id}")
async def product_detail(product_id: str):
    """Get detailed information about a specific product."""
    product = get_product(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@app.post("/products/compare")
async def compare_endpoint(product_ids: list[str]):
    """Compare multiple products side-by-side."""
    if len(product_ids) < 2:
        raise HTTPException(
            status_code=400,
            detail="At least 2 product IDs required for comparison"
        )
    return compare_products(product_ids)


# ── Checkout / Payment Endpoints ───────────────────────────────────

@app.post("/checkout", response_model=CheckoutResponse)
async def checkout_endpoint(request: CheckoutRequest):
    """Create a Stripe checkout session for purchasing a product."""
    try:
        result = create_checkout_session(
            product_id=request.product_id,
            quantity=request.quantity,
            conversation_id=request.conversation_id,
        )
        record_metric("checkout_created", 1, {"product_id": request.product_id})

        return CheckoutResponse(
            order_id=result["order_id"],
            checkout_url=result["checkout_url"],
            product_name=result["product_name"],
            amount=result["amount"],
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/orders/{order_id}")
async def order_status(order_id: str):
    """Check the status of an order."""
    order = db_get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    checkout_url = None
    if order["stripe_session_id"]:
        checkout_url = (f"https://dashboard.stripe.com/test/payments/"
                        f"{order['stripe_session_id']}")

    return OrderStatus(
        order_id=order["id"],
        status=order["status"],
        product_name=order["product_name"],
        amount=order["amount"],
        checkout_url=checkout_url,
    )


@app.post("/webhook")
async def stripe_webhook(request: Request):
    """Handle Stripe webhook events."""
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")
    result = handle_webhook(payload, sig_header)

    if result["status"] == "processed":
        record_metric("payment_completed", 1)
        return JSONResponse(result)
    elif result["status"] == "error":
        raise HTTPException(status_code=400, detail=result["reason"])
    return JSONResponse(result)


@app.get("/payments/test-cards")
async def test_cards():
    """Get Stripe test card information for the demo."""
    return get_test_card_info()


# ── Metrics & Dashboard Endpoints ──────────────────────────────────

@app.get("/metrics", response_model=MetricsResponse)
async def metrics():
    """Get aggregated metrics for the observability dashboard."""
    return get_metrics_summary()


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "service": "commerce-agent"}
