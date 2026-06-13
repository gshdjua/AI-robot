"""
Product catalog service with search, retrieval, and comparison.
"""

import json
from pathlib import Path
from typing import Optional

PRODUCTS_PATH = Path(__file__).parent.parent / "data" / "products.json"

# Load products once at module import
_products: list[dict] = []
_product_by_id: dict[str, dict] = {}

# Chinese-to-English keyword mapping for cross-language search
CN_KEYWORD_MAP = {
    # Electronics
    "电脑": "laptop macbook",
    "笔记本": "laptop macbook",
    "手机": "phone galaxy smartphone",
    "平板": "ipad tablet",
    "耳机": "headphone sony wh-1000xm",
    "电视": "tv oled lg",
    "笔记本": "laptop",
    # Clothing
    "衬衫": "shirt oxford",
    "衣服": "shirt blazer sweater jeans",
    "外套": "blazer wool",
    "西装": "blazer",
    "毛衣": "sweater cashmere",
    "鞋": "shoe ultraboost running",
    "跑鞋": "ultraboost running shoe",
    "运动鞋": "ultraboost running",
    "牛仔裤": "jeans levi 501",
    "裤子": "jeans",
    # Books
    "书": "book programming",
    "编程": "programming pragmatic clean code",
    "深度学习": "deep learning python",
    "机器学习": "deep learning data",
    "软件": "pragmatic programmer clean code",
    # Home
    "吸尘器": "dyson vacuum",
    "咖啡": "coffee nespresso",
    "咖啡机": "nespresso coffee",
    "杯子": "mug ember",
    "保温杯": "ember mug temperature",
    "灯": "light hue philips",
    "智能家居": "philips hue smart",
    "智能灯泡": "hue philips light",
    # Price / intent
    "便宜": "cheap",
    "最便宜": "cheap",
    "推荐": "best",
    "最好的": "best rated",
    "高性价比": "best value",
    # Categories
    "电子": "electronics",
    "服装": "clothing",
    "图书": "books",
    "家居": "home",
    "家电": "home",
}


# Common English stop words — filtered from keyword matching
STOP_WORDS = {
    "the", "and", "for", "are", "but", "not", "you", "all", "can",
    "had", "her", "was", "one", "our", "out", "has", "have", "get",
    "some", "than", "that", "this", "with", "your", "from", "they",
    "will", "what", "when", "where", "which", "who", "how", "about",
    "just", "like", "look", "make", "more", "over", "take", "than",
    "them", "then", "very", "want", "also", "into", "find", "give",
    "good", "help", "know", "look", "much", "need", "part", "show",
    "tell", "well", "work", "been", "being", "does", "done", "each",
    "else", "even", "ever", "look", "many", "most", "must", "only",
    "other", "said", "same", "seen", "should", "under", "were",
}

# English synonym mapping — common search terms → product keywords
EN_SYNONYM_MAP = {
    "laptop": "macbook dell xps",
    "laptops": "macbook dell xps",
    "computer": "macbook dell xps ipad",
    "notebook": "macbook dell xps",
    "phone": "galaxy smartphone",
    "smartphone": "galaxy",
    "headphones": "sony wh-1000xm",
    "headphone": "sony wh-1000xm",
    "earbuds": "sony wh-1000xm",
    "tablet": "ipad",
    "tv": "oled lg",
    "television": "oled lg",
    "monitor": "display",
    "vacuum": "dyson",
    "cleaner": "dyson",
    "coffee machine": "nespresso",
    "coffee maker": "nespresso",
    "coffee": "nespresso ember",
    "mug": "ember",
    "light": "philips hue",
    "lighting": "philips hue",
    "smart home": "philips hue ember",
    "speaker": "dolby atmos",
    "shoe": "ultraboost",
    "shoes": "ultraboost",
    "sneaker": "ultraboost",
    "running": "ultraboost",
    "shirt": "oxford",
    "blazer": "wool blazer",
    "jacket": "blazer",
    "sweater": "cashmere",
    "jeans": "levi 501",
    "pants": "jeans levi",
    "book": "programming pragmatic clean code designing data",
    "books": "programming pragmatic clean code designing data",
    "coding": "programming pragmatic clean code",
    "programming": "pragmatic clean code python designing",
    "machine learning": "deep learning python",
    "deep learning": "deep learning python",
    "ml": "deep learning python",
    "ai": "deep learning python",
    "software": "pragmatic programmer clean code",
}


def _translate_chinese_query(query: str) -> str:
    """Translate Chinese keywords in query to English for better matching."""
    result = query
    # Sort by key length (longest first) for better matching
    for cn, en in sorted(CN_KEYWORD_MAP.items(), key=lambda x: -len(x[0])):
        if cn in result:
            result = f"{result} {en}"
    return result


def _translate_english_query(query: str) -> str:
    """Translate common English search terms to product-specific keywords.
    Uses word-boundary matching to avoid substring false positives
    (e.g., 'book' should NOT match inside 'macbook')."""
    result = query.lower()
    # Split into words for boundary-aware matching
    words = set(result.split())
    # Also check multi-word phrases against the full string
    for term, synonyms in sorted(EN_SYNONYM_MAP.items(), key=lambda x: -len(x[0])):
        # Multi-word phrase: check in original string
        if " " in term:
            if term in result:
                result = f"{result} {synonyms}"
        # Single word: check word boundaries
        else:
            if term in words:
                result = f"{result} {synonyms}"
    return result


def _load_products() -> None:
    """Load products from JSON file into memory."""
    global _products, _product_by_id
    if _products:
        return  # Already loaded

    with open(PRODUCTS_PATH, "r", encoding="utf-8") as f:
        _products = json.load(f)

    _product_by_id = {p["id"]: p for p in _products}
    print(f"[Products] Loaded {len(_products)} products across "
          f"{len(set(p['category'] for p in _products))} categories.")


def get_all_categories() -> list[str]:
    """Get list of all product categories."""
    _load_products()
    return list(set(p["category"] for p in _products))


def _extract_price_constraints(query: str) -> tuple[str, float | None, float | None]:
    """Extract price constraints from natural language queries.

    Parses patterns like:
      - "under $1000" / "under 1000" / "below $500"
      - "above $100" / "over 200"
      - "between $100 and $500" / "$100-$500"
      - "<1000" / ">50"

    Returns (cleaned_query, max_price, min_price).
    """
    import re
    max_price = None
    min_price = None
    cleaned = query

    # "between X and Y" / "between X-Y" / "X to Y dollars"
    between_pat = re.findall(
        r'(?:between\s+)?\$?(\d+(?:\.\d{2})?)\s*(?:-|to|and)\s*\$?(\d+(?:\.\d{2})?)',
        cleaned, re.IGNORECASE
    )
    if between_pat:
        min_price = float(between_pat[0][0])
        max_price = float(between_pat[0][1])
        cleaned = re.sub(
            r'(?:between\s+)?\$?\d+(?:\.\d{2})?\s*(?:-|to|and)\s*\$?\d+(?:\.\d{2})?',
            '', cleaned, flags=re.IGNORECASE
        )

    # "under $X" / "below $X" / "< $X" / "less than $X" / "cheaper than $X"
    under_pat = re.findall(
        r'(?:under|below|less\s+than|cheaper\s+than|<\s*)\s*\$?(\d+(?:\.\d{2})?)',
        cleaned, re.IGNORECASE
    )
    if under_pat and max_price is None:
        max_price = float(under_pat[0])
        cleaned = re.sub(
            r'(?:under|below|less\s+than|cheaper\s+than|<\s*)\s*\$?\d+(?:\.\d{2})?',
            '', cleaned, flags=re.IGNORECASE
        )

    # "over $X" / "above $X" / "> $X" / "more than $X"
    over_pat = re.findall(
        r'(?:over|above|more\s+than|>\s*)\s*\$?(\d+(?:\.\d{2})?)',
        cleaned, re.IGNORECASE
    )
    if over_pat and min_price is None:
        min_price = float(over_pat[0])
        cleaned = re.sub(
            r'(?:over|above|more\s+than|>\s*)\s*\$?\d+(?:\.\d{2})?',
            '', cleaned, flags=re.IGNORECASE
        )

    # "up to $X" / "max $X"
    up_to_pat = re.findall(
        r'(?:up\s+to|max(?:imum)?)\s*\$?(\d+(?:\.\d{2})?)',
        cleaned, re.IGNORECASE
    )
    if up_to_pat and max_price is None:
        max_price = float(up_to_pat[0])
        cleaned = re.sub(
            r'(?:up\s+to|max(?:imum)?)\s*\$?\d+(?:\.\d{2})?',
            '', cleaned, flags=re.IGNORECASE
        )

    # standalone "$X" at end of query (often means max price: "laptops $1000")
    standalone = re.findall(r'\$(\d+(?:\.\d{2})?)$', cleaned.strip())
    if standalone and max_price is None:
        # Only treat as max_price if it looks like a filter, not a product price
        pass  # Too ambiguous, skip

    return cleaned.strip(), max_price, min_price


def search_products(
    query: str = "",
    category: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    sort_by: str = "relevance",
    limit: int = 5,
) -> list[dict]:
    """
    Search products by keyword with optional filters.

    The search uses a scoring algorithm:
    1. Keyword match in name (weight: 3x)
    2. Keyword match in description (weight: 2x)
    3. Keyword match in category (weight: 1x)
    4. Partial word matches (weight: 0.5x)
    5. Rating boost

    Args:
        query: Search keywords
        category: Filter by category
        min_price: Minimum price filter
        max_price: Maximum price filter
        sort_by: Sorting method ('relevance', 'price_asc', 'price_desc', 'rating')
        limit: Max number of results (default k=5)

    Returns:
        List of matching products sorted by relevance
    """
    _load_products()
    # Extract price constraints from natural language (e.g., "under $1000", "< 500")
    query, extracted_max, extracted_min = _extract_price_constraints(query)
    if max_price is None and extracted_max is not None:
        max_price = extracted_max
    if min_price is None and extracted_min is not None:
        min_price = extracted_min
    # Translate Chinese keywords to English for cross-language matching
    query = _translate_chinese_query(query)
    # Translate common English search terms to product-specific keywords
    query = _translate_english_query(query)
    query_lower = query.lower().strip()
    query_words = query_lower.split()

    results = []
    for product in _products:
        # Apply category filter
        if category and product["category"].lower() != category.lower():
            continue

        # Apply price filters
        if min_price is not None and product["price"] < min_price:
            continue
        if max_price is not None and product["price"] > max_price:
            continue

        # Calculate relevance score
        score = 0.0
        name_lower = product["name"].lower()
        desc_lower = product["description"].lower()
        cat_lower = product["category"].lower()

        for word in query_words:
            if not word or len(word) < 3:
                continue
            # Skip common English stop words that match too broadly
            if word in STOP_WORDS:
                continue

            # Check for whole-word match in name (higher weight)
            name_words = name_lower.split()
            if word in name_words:
                score += 3.0
                if name_lower == word:
                    score += 2.0
            elif word in name_lower:
                # Substring match (e.g., "book" in "MacBook") — lower weight
                score += 1.0

            # Check for whole-word match in description
            desc_words = desc_lower.split()
            if word in desc_words:
                score += 2.0
            elif word in desc_lower:
                score += 0.5

            # Category match — higher weight to disambiguate (e.g., "book" -> Books)
            if word in cat_lower:
                score += 2.0
                # Strong boost when category name is a whole-word match
                if word == cat_lower:
                    score += 2.0
            # Partial match bonus
            for name_word in name_words:
                if word in name_word and word != name_word:
                    score += 0.3

        # Rating boost (normalize to 0-1)
        score += product["rating"] / 10.0

        # Price boosts — cheaper items get slight relevance boost
        # (users searching generic terms tend to prefer affordable options)
        if product["price"] < 100:
            score += 0.2
        elif product["price"] < 500:
            score += 0.1

        if score > 0 or not query_lower:
            results.append({
                **product,
                "_score": round(score, 2)
            })

    # Sort results
    if sort_by == "price_asc":
        results.sort(key=lambda p: p["price"])
    elif sort_by == "price_desc":
        results.sort(key=lambda p: p["price"], reverse=True)
    elif sort_by == "rating":
        results.sort(key=lambda p: p["rating"], reverse=True)
    else:  # relevance
        results.sort(key=lambda p: p["_score"], reverse=True)

    # Filter out results with very low relevance (no keyword matches)
    if results and query_lower:
        top_score = results[0]["_score"]
        # Threshold: max(absolute 2.0, 30% of top score) — keeps only meaningful matches
        min_score = max(2.0, top_score * 0.3) if top_score > 0 else 0
        results = [r for r in results if r["_score"] >= min_score]

    # Return top-k results without internal _score
    top_results = results[:limit]
    for r in top_results:
        r.pop("_score", None)

    return top_results


def get_product(product_id: str) -> dict | None:
    """Get a single product by ID."""
    _load_products()
    return _product_by_id.get(product_id)


def get_products_by_ids(product_ids: list[str]) -> list[dict]:
    """Get multiple products by their IDs."""
    _load_products()
    return [p for pid in product_ids if (p := _product_by_id.get(pid))]


def compare_products(product_ids: list[str]) -> dict:
    """
    Compare products side-by-side.
    Returns product info and a specs comparison matrix.
    """
    products = get_products_by_ids(product_ids)

    if len(products) < 2:
        return {
            "products": products,
            "specs_comparison": {},
            "price_comparison": {},
            "recommendation": None,
        }

    # Build specs comparison matrix
    all_spec_keys = set()
    for p in products:
        all_spec_keys.update(p.get("specs", {}).keys())

    specs_comparison = {}
    for key in sorted(all_spec_keys):
        specs_comparison[key] = {
            p["id"]: p.get("specs", {}).get(key, "N/A")
            for p in products
        }

    # Price comparison
    prices = [(p["id"], p["name"], p["price"]) for p in products]
    cheapest = min(prices, key=lambda x: x[2])

    # Best rated
    best_rated = max(products, key=lambda p: p["rating"])

    return {
        "products": products,
        "specs_comparison": specs_comparison,
        "price_comparison": {
            p["id"]: p["price"] for p in products
        },
        "recommendation": {
            "best_value": cheapest[1],
            "best_value_id": cheapest[0],
            "best_value_price": cheapest[2],
            "best_rated": best_rated["name"],
            "best_rated_id": best_rated["id"],
            "best_rated_rating": best_rated["rating"],
        },
    }
