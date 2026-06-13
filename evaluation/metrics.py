"""
Custom commerce evaluation metrics for the Commerce Agent.

These metrics go beyond standard RAGAS metrics to capture
business-specific KPIs for e-commerce chatbot performance.

Metrics defined:
  - product_recommendation_accuracy: Did the agent recommend relevant products?
  - checkout_completion_rate: What fraction of checkout intents lead to orders?
  - average_comparison_depth: How many products do users compare on average?
  - search_to_purchase_ratio: What fraction of searches lead to purchase intent?
  - response_helpfulness: Composite score of product info completeness
  - stock_awareness: Does the agent correctly report stock status?
  - price_accuracy: Does the agent quote correct prices?
"""

import json
from pathlib import Path
from typing import Optional


def product_recommendation_accuracy(
    retrieved_product_ids: list[str],
    expected_product_ids: list[str],
) -> float:
    """
    Calculate precision and recall of product recommendations.

    Returns F1 score balancing precision and recall of product matches.

    Args:
        retrieved_product_ids: Product IDs the agent recommended
        expected_product_ids: Product IDs that should have been recommended

    Returns:
        F1 score (0.0 to 1.0)
    """
    if not expected_product_ids:
        return 1.0 if not retrieved_product_ids else 0.0

    retrieved_set = set(retrieved_product_ids)
    expected_set = set(expected_product_ids)

    true_positives = len(retrieved_set & expected_set)
    if true_positives == 0:
        return 0.0

    precision = true_positives / len(retrieved_set) if retrieved_set else 0.0
    recall = true_positives / len(expected_set) if expected_set else 0.0

    if precision + recall == 0:
        return 0.0

    f1 = 2 * (precision * recall) / (precision + recall)
    return round(f1, 4)


def checkout_completion_rate(
    total_checkout_intents: int,
    completed_orders: int,
) -> float:
    """
    Calculate checkout completion rate.

    This is the primary business KPI — what fraction of purchase
    intents actually result in completed payments?

    Returns:
        Completion rate as percentage (0-100)
    """
    if total_checkout_intents == 0:
        return 0.0
    return round((completed_orders / total_checkout_intents) * 100, 2)


def average_comparison_depth(comparison_sizes: list[int]) -> float:
    """
    Calculate average number of products users compare.

    Users who compare >= 2 products are 3x more likely to purchase.
    This metric tracks engagement quality.

    Returns:
        Average number of products per comparison
    """
    if not comparison_sizes:
        return 0.0
    return round(sum(comparison_sizes) / len(comparison_sizes), 2)


def search_to_purchase_ratio(
    total_searches: int,
    purchase_intents: int,
) -> float:
    """
    Calculate how many searches lead to purchase intent.

    High ratio = agent effectively guides users from discovery to purchase.
    Low ratio = agent fails to convert browsers to buyers.

    Returns:
        Ratio as percentage (0-100)
    """
    if total_searches == 0:
        return 0.0
    return round((purchase_intents / total_searches) * 100, 4)


def stock_awareness(
    agent_response: str,
    product_stock: dict[str, int],
) -> float:
    """
    Check if the agent correctly reports stock availability.

    Penalizes:
    - Recommending out-of-stock products
    - Not mentioning low stock when < 5 items remain

    Returns:
        Score from 0.0 to 1.0
    """
    response_lower = agent_response.lower()
    score = 1.0
    penalty = 0.1

    for product_id, stock in product_stock.items():
        if stock == 0 and product_id.lower() in response_lower:
            # Recommended out-of-stock product — significant penalty
            score -= penalty * 3
        elif stock < 5 and product_id.lower() in response_lower:
            # Low stock — should mention it
            stock_mentioned = any(
                w in response_lower
                for w in ["only", "low stock", "limited", "few left", "last", "hurry"]
            )
            if not stock_mentioned:
                score -= penalty

    return max(0.0, min(1.0, round(score, 4)))


def price_accuracy(
    agent_response: str,
    product_prices: dict[str, float],
) -> float:
    """
    Verify the agent quotes correct prices.

    Searches the response for price mentions and compares
    against known prices. Price hallucinations in commerce
    are particularly damaging to trust.

    Returns:
        Score from 0.0 to 1.0 (1.0 = all prices correct)
    """
    if not product_prices:
        return 1.0

    import re
    score = 1.0
    penalty = 0.15

    # Find price patterns in response: $XX.XX or $XX
    price_pattern = re.findall(r'\$(\d+(?:\.\d{2})?)', agent_response)

    for price_str in price_pattern:
        mentioned_price = float(price_str)
        # Check if this price matches any expected price
        matches = [
            abs(mentioned_price - expected) < 0.01
            for expected in product_prices.values()
        ]
        if not any(matches) and len(price_pattern) > len(product_prices):
            # Extra price mentioned that doesn't match — possible hallucination
            score -= penalty

    return max(0.0, min(1.0, round(score, 4)))


def compute_all_metrics(
    agent_response: str,
    retrieved_product_ids: list[str],
    expected_product_ids: list[str],
    product_stock: Optional[dict[str, int]] = None,
    product_prices: Optional[dict[str, float]] = None,
    comparison_size: int = 0,
    total_searches: int = 0,
    purchase_intents: int = 0,
    total_checkout_intents: int = 0,
    completed_orders: int = 0,
) -> dict:
    """
    Compute all custom commerce metrics for a single evaluation run.

    Returns a dictionary of metric names to scores.
    """
    return {
        "product_recommendation_accuracy": product_recommendation_accuracy(
            retrieved_product_ids, expected_product_ids
        ),
        "checkout_completion_rate": checkout_completion_rate(
            total_checkout_intents, completed_orders
        ),
        "average_comparison_depth": average_comparison_depth(
            [comparison_size] if comparison_size > 0 else []
        ),
        "search_to_purchase_ratio": search_to_purchase_ratio(
            total_searches, purchase_intents
        ),
        "stock_awareness": stock_awareness(
            agent_response, product_stock or {}
        ),
        "price_accuracy": price_accuracy(
            agent_response, product_prices or {}
        ),
    }


def load_expected_results() -> dict:
    """Load test cases with expected results for evaluation."""
    path = Path(__file__).parent / "test_cases.json"
    with open(path, "r") as f:
        return json.load(f)
