"""
Pydantic models for the Commerce Agent API.
"""

from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


class Intent(str, Enum):
    GREETING = "greeting"
    SEARCH = "search"
    COMPARE = "compare"
    ASK_DETAILS = "ask_details"
    PURCHASE = "purchase"
    GENERAL = "general"


class ChatRequest(BaseModel):
    """Request body for /chat endpoint."""
    message: str = Field(..., min_length=1, max_length=2000,
                         description="User's chat message")
    conversation_id: Optional[str] = Field(
        default=None,
        description="Existing conversation ID for continuing a chat. "
                    "If not provided, a new conversation will be created."
    )


class ProductInfo(BaseModel):
    """Product information returned in chat responses."""
    id: str
    name: str
    category: str
    price: float
    description: str
    image_url: str
    stock: int
    rating: float


class ProductComparison(BaseModel):
    """Product comparison data."""
    products: list[ProductInfo]
    specs_comparison: dict = Field(
        default_factory=dict,
        description="Key: spec name, Value: dict of product_id -> spec value"
    )


class ChatResponse(BaseModel):
    """Response from /chat endpoint."""
    message: str = Field(..., description="Assistant's text response")
    conversation_id: str
    intent: Optional[Intent] = None
    products: list[ProductInfo] = Field(
        default_factory=list,
        description="Products mentioned/recommended in the response"
    )
    comparison: Optional[ProductComparison] = None
    checkout_url: Optional[str] = Field(
        default=None,
        description="Stripe checkout URL for purchase intent"
    )
    error: Optional[str] = None


class CheckoutRequest(BaseModel):
    """Request body for /checkout endpoint."""
    product_id: str = Field(..., description="Product ID to purchase")
    quantity: int = Field(default=1, ge=1, le=10,
                          description="Quantity to purchase")
    conversation_id: Optional[str] = None


class CheckoutResponse(BaseModel):
    """Response from /checkout endpoint."""
    order_id: str
    checkout_url: str
    product_name: str
    amount: float
    currency: str = "usd"


class OrderStatus(BaseModel):
    """Order status response."""
    order_id: str
    status: str
    product_name: str
    amount: float
    checkout_url: str | None = None


class MetricsResponse(BaseModel):
    """Aggregated metrics for dashboard."""
    total_conversations: int = 0
    total_messages: int = 0
    total_orders: int = 0
    completed_orders: int = 0
    conversion_rate: float = 0.0
    total_revenue: float = 0.0
    intent_distribution: dict[str, int] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    """Standard error response."""
    error: str
    detail: Optional[str] = None
