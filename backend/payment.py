"""
Stripe payment integration for the Commerce Agent.
Handles checkout session creation, webhooks, and payment status tracking.
"""

import os
import uuid
from typing import Optional

try:
    import stripe
    stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "sk_test_placeholder")
    _STRIPE_AVAILABLE = True
except ImportError:
    stripe = None
    _STRIPE_AVAILABLE = False

from .database import create_order, update_order_status, get_order_by_session
from .products import get_product

# Stripe configuration — uses test mode by default
if _STRIPE_AVAILABLE:
    stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "sk_test_placeholder")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "whsec_placeholder")

# Base URL for success/cancel redirects
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")

# Stripe test card documentation reference
TEST_CARDS = {
    "success": "4242 4242 4242 4242",
    "auth_required": "4000 0027 6000 3184",
    "declined": "4000 0000 0000 0002",
}


def create_checkout_session(
   
    product_id: str,
    quantity: int = 1,
    conversation_id: Optional[str] = None,
) -> dict:
    """
    Create a Stripe Checkout Session for purchasing a product.

    Uses Stripe Checkout Sessions (hosted payment page) for a secure,
    PCI-compliant payment flow with minimal integration effort.

    Args:
        product_id: ID of the product to purchase
        quantity: Number of units
        conversation_id: Associated conversation for tracking

    Returns:
        Dict with order_id and checkout_url
    """
    secret_key = os.getenv("STRIPE_SECRET_KEY")
    print(f"[DEBUG] secret_key = {secret_key}")
    print(f"[DEBUG] _STRIPE_AVAILABLE = {_STRIPE_AVAILABLE}")
    use_mock = not _STRIPE_AVAILABLE or not secret_key or secret_key == "sk_test_placeholder"
    print(f"[DEBUG] use_mock = {use_mock}")
    product = get_product(product_id)
    if not product:
        raise ValueError(f"Product not found: {product_id}")

    if product["stock"] < quantity:
        raise ValueError(
            f"Insufficient stock for {product['name']}: "
            f"requested {quantity}, available {product['stock']}"
        )

    order_id = f"order-{uuid.uuid4().hex[:12]}"
    amount = round(product["price"] * quantity, 2)
    secret_key = os.getenv("STRIPE_SECRET_KEY")

    # For testing/demo without actual Stripe keys, return a mock checkout
    if not _STRIPE_AVAILABLE or not secret_key or secret_key == "sk_test_placeholder":
        mock_url = (f"{BASE_URL}/static/checkout-demo.html"
                    f"?order_id={order_id}"
                    f"&product={product['name']}"
                    f"&amount={amount}")
        create_order(
            order_id=order_id,
            conversation_id=conversation_id or "anonymous",
            product_id=product_id,
            product_name=product["name"],
            quantity=quantity,
            amount=amount,
            stripe_session_id=f"mock_session_{order_id}",
        )
        return {
            "order_id": order_id,
            "checkout_url": mock_url,
            "product_name": product["name"],
            "amount": amount,
            "currency": "usd",
            "test_mode": True,
        }

    # Real Stripe integration
    stripe.api_key = secret_key
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "product_data": {
                        "name": product["name"],
                        "description": product["description"][:200],
                        "images": [product.get("image_url", "")],
                    },
                    "unit_amount": int(product["price"] * 100),  # cents
                },
                "quantity": quantity,
            }],
            mode="payment",
            success_url=f"{BASE_URL}/static/checkout-success.html"
                        f"?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{BASE_URL}/static/checkout-cancel.html"
                       f"?product_id={product_id}",
            metadata={
                "order_id": order_id,
                "product_id": product_id,
                "conversation_id": conversation_id or "anonymous",
            },
        )

        # Record the order in our database
        create_order(
            order_id=order_id,
            conversation_id=conversation_id or "anonymous",
            product_id=product_id,
            product_name=product["name"],
            quantity=quantity,
            amount=amount,
            stripe_session_id=session.id,
        )

        return {
            "order_id": order_id,
            "checkout_url": session.url,
            "product_name": product["name"],
            "amount": amount,
            "currency": "usd",
            "stripe_session_id": session.id,
        }

    except (stripe.error.StripeError if _STRIPE_AVAILABLE else Exception) as e:
        raise RuntimeError(f"Stripe checkout creation failed: {str(e)}")


def handle_webhook(payload: bytes, sig_header: str) -> dict:
    """
    Handle Stripe webhook events for payment status updates.

    Processes checkout.session.completed events to update order status.
    """
    if (not _STRIPE_AVAILABLE
            or not os.getenv("STRIPE_WEBHOOK_SECRET")
            or STRIPE_WEBHOOK_SECRET == "whsec_placeholder"):
        return {"status": "skipped", "reason": "Webhook secret not configured"}

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        return {"status": "error", "reason": "Invalid payload"}
    except stripe.error.SignatureVerificationError:
        return {"status": "error", "reason": "Invalid signature"}

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        stripe_session_id = session["id"]

        # Update order status
        order = get_order_by_session(stripe_session_id)
        if order:
            update_order_status(order["id"], "paid")
            return {
                "status": "processed",
                "order_id": order["id"],
                "event": "payment_completed",
            }

    elif event["type"] == "checkout.session.expired":
        session = event["data"]["object"]
        stripe_session_id = session["id"]
        order = get_order_by_session(stripe_session_id)
        if order:
            update_order_status(order["id"], "cancelled")
            return {
                "status": "processed",
                "order_id": order["id"],
                "event": "session_expired",
            }

    return {"status": "ignored", "event_type": event["type"]}


def get_test_card_info() -> dict:
    """Return Stripe test card numbers for the demo."""
    return {
        "description": "Use these test card numbers to simulate different payment scenarios",
        "cards": TEST_CARDS,
        "generic_test": {
            "number": "4242 4242 4242 4242",
            "expiry": "Any future date (MM/YY)",
            "cvc": "Any 3 digits",
            "zip": "Any 5 digits",
        },
        "docs_url": "https://docs.stripe.com/testing",
    }
