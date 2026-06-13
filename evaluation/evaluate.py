"""
Commerce Agent Evaluation Runner

Runs RAGAS evaluation metrics and custom commerce KPIs
against test cases to measure agent performance.

Usage:
    python evaluation/evaluate.py                    # Run all evaluations
    python evaluation/evaluate.py --test-case tc-001 # Run single test case
    python evaluation/evaluate.py --model claude     # Run with specific model
"""

import json
import os
import sys
import time
from pathlib import Path
from typing import Optional

# Add backend to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.products import search_products, get_product
from evaluation.metrics import (
    compute_all_metrics,
    load_expected_results,
    product_recommendation_accuracy,
    stock_awareness,
    price_accuracy,
)


def evaluate_search(query: str, expected_product_ids: list[str],
                    category: Optional[str] = None) -> dict:
    """
    Evaluate a product search against expected results.

    Measures:
    - Product recommendation accuracy (F1)
    - Retrieval precision@k for k=5
    - Retrieval recall@k for k=5
    """
    # Run the actual product search
    results = search_products(query=query, category=category, limit=5)
    retrieved_ids = [p["id"] for p in results]

    # Calculate metrics
    accuracy = product_recommendation_accuracy(retrieved_ids, expected_product_ids)

    # Precision@5 and Recall@5
    retrieved_set = set(retrieved_ids)
    expected_set = set(expected_product_ids)

    precision = len(retrieved_set & expected_set) / max(len(retrieved_set), 1)
    recall = len(retrieved_set & expected_set) / max(len(expected_set), 1)

    return {
        "query": query,
        "retrieved_product_ids": retrieved_ids,
        "expected_product_ids": expected_product_ids,
        "product_accuracy_f1": accuracy,
        "precision_at_5": round(precision, 4),
        "recall_at_5": round(recall, 4),
        "retrieved_count": len(retrieved_ids),
        "expected_count": len(expected_product_ids),
    }


def evaluate_ragas_metrics(test_case: dict) -> dict:
    """
    Compute RAGAS-style metrics for a single test case.

    RAGAS metrics computed:
    - Faithfulness: Does response match retrieved context?
    - Answer Relevancy: Does response address the query?
    - Context Precision: How precise is the retrieved context?
    - Context Recall: How comprehensive is the retrieved context?

    Note: Full RAGAS integration requires LLM-as-judge with an
    evaluation model. This implementation provides the framework
    and computes proxy metrics that can be upgraded to full
    RAGAS when an eval LLM is configured.
    """
    query = test_case["query"]
    expected_ids = test_case.get("expected_products", [])
    expected_category = test_case.get("category", "search")

    # Retrieve context (products) for this query
    retrieved = search_products(query=query, limit=5)
    retrieved_ids = [p["id"] for p in retrieved]
    retrieved_texts = [
        f"{p['name']}: {p['description'][:200]} — ${p['price']:.2f} "
        f"(Rating: {p['rating']}/5, Stock: {p['stock']})"
        for p in retrieved
    ]

    # Proxy faithfulness: overlap between retrieved and expected
    faithfulness = product_recommendation_accuracy(retrieved_ids, expected_ids)

    # Proxy answer relevancy: keyword overlap between query and retrieved
    query_words = set(query.lower().split())
    retrieved_words = set(" ".join(retrieved_texts).lower().split())
    relevancy = len(query_words & retrieved_words) / max(len(query_words), 1)

    # Context precision: relevant items / total retrieved
    relevant_in_context = len(set(retrieved_ids) & set(expected_ids))
    context_precision = relevant_in_context / max(len(retrieved_ids), 1)

    # Context recall: relevant items retrieved / total relevant
    context_recall = relevant_in_context / max(len(expected_ids), 1)

    return {
        "test_case_id": test_case["id"],
        "query": query,
        "faithfulness": round(faithfulness, 4),
        "answer_relevancy": round(min(relevancy, 1.0), 4),
        "context_precision": round(context_precision, 4),
        "context_recall": round(context_recall, 4),
        "retrieved_products": retrieved_ids,
        "expected_products": expected_ids,
        "pass": faithfulness >= 0.5 and context_recall >= 0.5,
    }


def evaluate_with_commerce_metrics(test_case: dict) -> dict:
    """
    Full evaluation including custom commerce KPIs.
    """
    # Build a mock agent response for evaluation
    query = test_case["query"]
    results = search_products(query=query, limit=5)
    retrieved_ids = [p["id"] for p in results]

    # Simulate agent response text
    if results:
        product_lines = []
        for p in results[:3]:
            product_lines.append(
                f"[PRODUCT:{p['id']}] {p['name']} — ${p['price']:.2f} "
                f"(Rating: {p['rating']}/5, Stock: {p['stock']})"
            )
        mock_response = (
            f"Here's what I found for \"{query}\":\n\n" +
            "\n\n".join(product_lines)
        )
    else:
        mock_response = f"Sorry, I couldn't find any products matching \"{query}\"."

    # Get product stock and prices for accuracy checking
    stock = {p["id"]: p["stock"] for p in results}
    prices = {p["id"]: p["price"] for p in results}

    # Compute custom metrics
    custom_metrics = compute_all_metrics(
        agent_response=mock_response,
        retrieved_product_ids=retrieved_ids,
        expected_product_ids=test_case.get("expected_products", []),
        product_stock=stock,
        product_prices=prices,
    )

    return {
        "test_case_id": test_case["id"],
        "query": query,
        "custom_metrics": custom_metrics,
    }


def run_full_evaluation() -> dict:
    """Run the complete evaluation suite against all test cases."""
    print("=" * 70)
    print("  Commerce Agent — Full Evaluation Suite")
    print("  Metrics: RAGAS + Custom Commerce KPIs")
    print("=" * 70)
    print()

    data = load_expected_results()
    test_cases = data["test_cases"]

    ragas_results = []
    commerce_results = []
    search_eval_results = []

    total_start = time.time()

    for tc in test_cases:
        print(f"  Evaluating [{tc['id']}]: {tc['query'][:60]}...")

        # RAGAS evaluation
        ragas_result = evaluate_ragas_metrics(tc)
        ragas_results.append(ragas_result)

        # Commerce metrics evaluation
        commerce_result = evaluate_with_commerce_metrics(tc)
        commerce_results.append(commerce_result)

        # Search evaluation
        if tc.get("category") == "search":
            search_result = evaluate_search(
                tc["query"], tc["expected_products"]
            )
            search_eval_results.append(search_result)

    total_time = time.time() - total_start

    # Aggregate results
    avg_ragas = {
        "faithfulness": round(
            sum(r["faithfulness"] for r in ragas_results) / len(ragas_results), 4
        ),
        "answer_relevancy": round(
            sum(r["answer_relevancy"] for r in ragas_results) / len(ragas_results), 4
        ),
        "context_precision": round(
            sum(r["context_precision"] for r in ragas_results) / len(ragas_results), 4
        ),
        "context_recall": round(
            sum(r["context_recall"] for r in ragas_results) / len(ragas_results), 4
        ),
    }

    avg_search = {
        "product_accuracy_f1": round(
            sum(r["product_accuracy_f1"] for r in search_eval_results)
            / max(len(search_eval_results), 1), 4
        ),
        "precision_at_5": round(
            sum(r["precision_at_5"] for r in search_eval_results)
            / max(len(search_eval_results), 1), 4
        ),
        "recall_at_5": round(
            sum(r["recall_at_5"] for r in search_eval_results)
            / max(len(search_eval_results), 1), 4
        ),
    } if search_eval_results else {}

    pass_rate = sum(1 for r in ragas_results if r["pass"]) / len(ragas_results)

    summary = {
        "evaluation_time_seconds": round(total_time, 2),
        "test_cases_count": len(test_cases),
        "pass_rate": round(pass_rate, 4),
        "ragas_metrics_avg": avg_ragas,
        "search_metrics_avg": avg_search,
        "ragas_results": ragas_results,
        "commerce_results": commerce_results,
        "search_results": search_eval_results,
    }

    # Print summary
    print()
    print("─" * 70)
    print("  EVALUATION SUMMARY")
    print("─" * 70)
    print(f"  Test Cases:        {len(test_cases)}")
    print(f"  Pass Rate:         {pass_rate:.1%}")
    print(f"  Evaluation Time:   {total_time:.2f}s")
    print()
    print("  RAGAS Metrics (Average):")
    print(f"    Faithfulness:        {avg_ragas['faithfulness']:.4f}")
    print(f"    Answer Relevancy:    {avg_ragas['answer_relevancy']:.4f}")
    print(f"    Context Precision:   {avg_ragas['context_precision']:.4f}")
    print(f"    Context Recall:      {avg_ragas['context_recall']:.4f}")
    if avg_search:
        print()
        print("  Search Metrics (Average @ k=5):")
        print(f"    Product Accuracy F1: {avg_search['product_accuracy_f1']:.4f}")
        print(f"    Precision@5:         {avg_search['precision_at_5']:.4f}")
        print(f"    Recall@5:            {avg_search['recall_at_5']:.4f}")
    print()
    print("─" * 70)
    print("  Detailed results per test case:")
    for r in ragas_results:
        status = "✅ PASS" if r["pass"] else "❌ FAIL"
        print(f"  {status} | {r['test_case_id']}: {r['query'][:55]}...")
        print(f"          Faithfulness={r['faithfulness']:.3f} "
              f"Relevancy={r['answer_relevancy']:.3f} "
              f"Precision={r['context_precision']:.3f} "
              f"Recall={r['context_recall']:.3f}")
    print("=" * 70)

    # Save results to file
    output_path = Path(__file__).parent / "evaluation_results.json"
    with open(output_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\n  Results saved to: {output_path}")

    return summary


if __name__ == "__main__":
    run_full_evaluation()
