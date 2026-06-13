"""
Commerce Chat Agent — orchestrates product search, comparison, and purchase
through LLM-powered conversation with tool calling.
"""

import os
import json
import uuid
from typing import Optional

from .products import search_products, get_product, compare_products, get_all_categories
from .observability import Trace, log_llm_call, log_error
from .models import Intent


# System prompt defining the commerce agent's persona and capabilities
SYSTEM_PROMPT = """You are CommerceBot, an AI shopping assistant that helps customers find, compare, and purchase products.

## Your Capabilities
- Search for products across categories: Electronics, Clothing, Books, Home
- Provide detailed product information including specs and prices
- Compare multiple products side-by-side
- Help customers complete purchases through secure checkout

## Tools Available
You have access to these functions:
1. **search_products(query, category?, min_price?, max_price?)** — Search the product catalog
2. **get_product_details(product_id)** — Get full details of a specific product
3. **compare_products(product_ids)** — Compare 2-4 products side by side
4. **get_categories()** — List all product categories

## Guidelines
- Be friendly, helpful, and conversational
- When a user wants to search, use the search_products function
- When a user wants to see a specific product, use get_product_details
- When a user wants to compare, use compare_products with the relevant product IDs
- For purchase intent, guide them to use the checkout button on product cards
- Always mention prices clearly and note stock availability
- If a product is out of stock, suggest alternatives
- Keep responses concise but informative — don't overwhelm with too many products at once
- Highlight key specs that matter most for the product category
- Recommend the best value option when comparing products

## Response Format
When you use tools, the system will inject the results. Then respond naturally to the user.
Always include product IDs when mentioning products so the UI can render product cards.
Format product references like: [PRODUCT:product_id] to trigger the product card display."""


def _select_model() -> str:
    """Select which LLM to use based on available API keys."""
    if os.getenv("ANTHROPIC_API_KEY"):
        return "claude"
    elif os.getenv("OPENAI_API_KEY"):
        return "openai"
    return "mock"


def _call_claude(messages: list[dict], tools: list[dict]) -> dict:
    """Call Anthropic Claude API."""
    import anthropic

    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")

    system = messages[0]["content"] if messages[0]["role"] == "system" else None
    api_messages = [m for m in messages if m["role"] != "system"]

    # Convert our tool format to Anthropic's format
    anthropic_tools = []
    for tool in tools:
        anthropic_tools.append({
            "name": tool["name"],
            "description": tool["description"],
            "input_schema": {
                "type": "object",
                "properties": tool.get("parameters", {}).get("properties", {}),
                "required": tool.get("parameters", {}).get("required", []),
            }
        })

    kwargs = {
        "model": model,
        "messages": api_messages,
        "max_tokens": 1024,
        "tools": anthropic_tools,
    }
    if system:
        kwargs["system"] = system

    response = client.messages.create(**kwargs)

    # Extract tool calls if any
    tool_calls = []
    text_content = ""
    for block in response.content:
        if block.type == "text":
            text_content += block.text
        elif block.type == "tool_use":
            tool_calls.append({
                "id": block.id,
                "name": block.name,
                "input": block.input,
            })

    return {
        "content": text_content,
        "tool_calls": tool_calls,
        "model": model,
        "usage": {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        }
    }


def _call_openai(messages: list[dict], tools: list[dict]) -> dict:
    """Call OpenAI API."""
    from openai import OpenAI

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    base_url = os.getenv("OPENAI_BASE_URL")
    model = os.getenv("OPENAI_MODEL", "gpt-4o")

    # Convert tool format for OpenAI
    openai_tools = []
    for tool in tools:
        openai_tools.append({
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool.get("parameters", {}),
            }
        })

    response = client.chat.completions.create(
        model=model,
        messages=messages,
        tools=openai_tools or None,
        max_tokens=1024,
    )

    msg = response.choices[0].message
    tool_calls = []
    if msg.tool_calls:
        for tc in msg.tool_calls:
            tool_calls.append({
                "id": tc.id,
                "name": tc.function.name,
                "input": json.loads(tc.function.arguments),
            })

    return {
        "content": msg.content or "",
        "tool_calls": tool_calls,
        "model": model,
        "usage": {
            "input_tokens": response.usage.prompt_tokens,
            "output_tokens": response.usage.completion_tokens,
        }
    }


def _call_mock(messages: list[dict], tools: list[dict]) -> dict:
    """Mock LLM for testing without API keys. Does basic intent matching."""
    last_message = messages[-1]["content"].lower()

    # Simple intent detection — supports both English and Chinese
    greeting_words = [
        "hello", "hi", "hey", "greetings", "good morning", "good afternoon",
        "你好", "您好", "嗨", "早上好", "下午好", "晚上好", "在吗", "你是谁",
        "what are you", "who are you", "help",
    ]
    search_words = [
        "find", "search", "show", "looking for", "want", "need", "laptop",
        "phone", "book", "shoe", "shirt", "jeans", "headphone", "tv",
        "coffee", "vacuum", "mug", "light", "cheap", "budget", "under",
        "找", "搜", "搜索", "想买", "想要", "有没有", "推荐", "介绍", "看看",
        "电脑", "笔记本", "手机", "书", "耳机", "鞋", "衣服", "电视", "咖啡",
        "吸尘器", "杯子", "灯", "便宜", "预算", "多少钱", "价格", "商品",
        "产品", "有没有卖", "帮我找", "买什么", "购物", "有没有", "有卖",
    ]
    compare_words = [
        "compare", "vs", "versus", "difference", "which one", "better",
        "对比", "比较", "哪个好", "区别", "差别", "选哪个", "vs",
    ]
    buy_words = [
        "buy", "purchase", "checkout", "order", "pay", "cart",
        "买", "购买", "下单", "付款", "结账", "支付", "我要了",
    ]

    # Detect if the message contains non-trivial content (not just greetings)
    # For any message with substance, try product search first
    has_substance = len(last_message.strip()) > 3

    # Priority: search > compare > buy > greeting > default
    # This ensures "I want to buy headphones" still triggers a SEARCH first
    if any(w in last_message for w in search_words) or has_substance:
        return {
            "content": "",
            "tool_calls": [{
                "id": "mock_1",
                "name": "search_products",
                "input": {"query": last_message, "limit": 5},
            }],
            "model": "mock",
            "usage": {"input_tokens": 50, "output_tokens": 30},
        }

    if any(w in last_message for w in compare_words):
        return {
            "content": "",
            "tool_calls": [{
                "id": "mock_1",
                "name": "search_products",
                "input": {"query": last_message, "limit": 5},
            }],
            "model": "mock",
            "usage": {"input_tokens": 50, "output_tokens": 35},
        }

    if any(w in last_message for w in buy_words):
        return {
            "content": "I'd love to help you complete your purchase! "
                       "请点击产品卡片上的 \"Buy Now\" 按钮进入 Stripe 安全结账页面。"
                       "Which product would you like to buy? / 您想购买哪个商品？",
            "tool_calls": [],
            "model": "mock",
            "usage": {"input_tokens": 50, "output_tokens": 40},
        }

    if any(w in last_message for w in greeting_words):
        return {
            "content": "Hello! 👋 你好！我是 CommerceBot，您的 AI 购物助手。\n"
                       "I can help you find products, compare options, and make purchases.\n"
                       "我可以帮您搜索商品、对比产品、完成购买。\n\n"
                       "Categories / 商品分类: Electronics 电子, Clothing 服装, "
                       "Books 图书, and Home 家居。\n"
                       "What are you looking for today? / 今天想买点什么呢？",
            "tool_calls": [],
            "model": "mock",
            "usage": {"input_tokens": 50, "output_tokens": 45},
        }

    return {
        "content": "您想找什么类型的商品呢？我可以帮您搜索电子产品、服装、图书和家居用品。\n"
                   "What kind of products are you interested in? I can search across "
                   "Electronics, Clothing, Books, and Home categories.",
        "tool_calls": [],
        "model": "mock",
        "usage": {"input_tokens": 50, "output_tokens": 40},
    }


# Tool definitions the agent can use
TOOLS = [
    {
        "name": "search_products",
        "description": "Search the product catalog by keywords. Returns matching products "
                       "with prices, ratings, and key specs.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search keywords from user's description of what they want"
                },
                "category": {
                    "type": "string",
                    "description": "Optional: filter by category (Electronics, Clothing, Books, Home)"
                },
                "min_price": {
                    "type": "number",
                    "description": "Optional: minimum price filter"
                },
                "max_price": {
                    "type": "number",
                    "description": "Optional: maximum price filter"
                },
                "sort_by": {
                    "type": "string",
                    "enum": ["relevance", "price_asc", "price_desc", "rating"],
                    "description": "How to sort results"
                },
                "limit": {
                    "type": "integer",
                    "description": "Number of results to return (default 5)"
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_product_details",
        "description": "Get complete details for a specific product by its ID.",
        "parameters": {
            "type": "object",
            "properties": {
                "product_id": {
                    "type": "string",
                    "description": "The product ID to look up"
                },
            },
            "required": ["product_id"],
        },
    },
    {
        "name": "compare_products",
        "description": "Compare 2-4 products side-by-side with specs, prices, and a recommendation.",
        "parameters": {
            "type": "object",
            "properties": {
                "product_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of 2-4 product IDs to compare",
                    "minItems": 2,
                    "maxItems": 4,
                },
            },
            "required": ["product_ids"],
        },
    },
    {
        "name": "get_categories",
        "description": "Get a list of all available product categories.",
        "parameters": {
            "type": "object",
            "properties": {},
        },
    },
]


def execute_tool(tool_name: str, tool_input: dict) -> dict:
    """Execute a tool call and return the result."""
    if tool_name == "search_products":
        return {
            "products": search_products(
                query=tool_input.get("query", ""),
                category=tool_input.get("category"),
                min_price=tool_input.get("min_price"),
                max_price=tool_input.get("max_price"),
                sort_by=tool_input.get("sort_by", "relevance"),
                limit=tool_input.get("limit", 5),
            )
        }
    elif tool_name == "get_product_details":
        product = get_product(tool_input.get("product_id", ""))
        return {"product": product} if product else {"error": "Product not found"}
    elif tool_name == "compare_products":
        return compare_products(tool_input.get("product_ids", []))
    elif tool_name == "get_categories":
        return {"categories": get_all_categories()}
    else:
        return {"error": f"Unknown tool: {tool_name}"}


def _format_search_results_as_text(results: dict) -> str:
    """Format search results as text for the LLM to consume."""
    products = results.get("products", [])
    if not products:
        return "[Search returned no products matching the query]"

    lines = [f"Found {len(products)} products:"]
    for i, p in enumerate(products, 1):
        lines.append(
            f"{i}. {p['name']} [{p['id']}] — ${p['price']:.2f} — "
            f"Rating: {p['rating']}/5 — Stock: {p['stock']} — {p['category']}\n"
            f"   {p['description'][:150]}..."
        )
    return "\n".join(lines)


def detect_intent(user_message: str, assistant_response: str,
                  tool_calls: list) -> Intent:
    """Detect the intent of the current interaction."""
    msg_lower = user_message.lower()

    greeting_words = ["hello", "hi", "hey", "greetings", "good morning",
                      "good afternoon", "good evening", "thanks", "thank you"]
    if any(msg_lower.startswith(w) or msg_lower == w for w in greeting_words):
        return Intent.GREETING

    if tool_calls:
        for tc in tool_calls:
            if tc["name"] == "search_products":
                return Intent.SEARCH
            elif tc["name"] == "compare_products":
                return Intent.COMPARE
            elif tc["name"] == "get_product_details":
                return Intent.ASK_DETAILS

    buy_words = ["buy", "purchase", "checkout", "order", "pay", "i'll take",
                 "i want to buy", "get it", "grab it"]
    if any(w in msg_lower for w in buy_words):
        return Intent.PURCHASE

    search_hints = ["find", "search", "show me", "looking for", "do you have",
                    "recommend", "suggest"]
    if any(w in msg_lower for w in search_hints):
        return Intent.SEARCH

    return Intent.GENERAL


def _build_conversation_messages(history: list[dict], system_prompt: str,
                                 user_message: str) -> list[dict]:
    """Build the message list for the LLM call from conversation history."""
    messages = [{"role": "system", "content": system_prompt}]

    for msg in history[-10:]:  # Last 10 messages for context window management
        messages.append({
            "role": msg["role"],
            "content": msg["content"],
        })

    # Add current user message
    messages.append({"role": "user", "content": user_message})

    return messages


def chat(user_message: str, conversation_history: list[dict] = None) -> dict:
    """
    Process a chat message through the commerce agent.

    Args:
        user_message: The user's latest message
        conversation_history: Previous messages in the conversation

    Returns:
        Response dict with agent reply, products, comparison, and checkout info
    """
    trace = Trace(name="chat-request", session_id=str(uuid.uuid4())[:12])
    history = conversation_history or []
    model_name = _select_model()

    try:
        # Build messages for LLM
        messages = _build_conversation_messages(history, SYSTEM_PROMPT, user_message)

        # Step 1: Initial LLM call — may include tool calls
        span1 = trace.span("llm-initial", {"model": model_name})

        if model_name == "claude":
            result = _call_claude(messages, TOOLS)
        elif model_name == "openai":
            result = _call_openai(messages, TOOLS)
        else:
            result = _call_mock(messages, TOOLS)

        total_tokens = result["usage"]["input_tokens"] + result["usage"]["output_tokens"]
        span1.input_data = user_message
        span1.end(
            output=result["content"][:200],
            tokens_used=total_tokens,
        )

        # Step 2: Execute tool calls if any
        tool_results = []
        all_products = []
        comparison_data = None

        if result["tool_calls"]:
            for tc in result["tool_calls"]:
                tool_span = trace.span(f"tool-{tc['name']}", {"tool": tc["name"]})
                tool_result = execute_tool(tc["name"], tc["input"])
                tool_results.append({
                    "tool_call_id": tc["id"],
                    "name": tc["name"],
                    "result": tool_result,
                })
                tool_span.end(output=str(tool_result)[:300])

                # Collect products from search results
                if tc["name"] == "search_products":
                    for p in tool_result.get("products", []):
                        if p["id"] not in [ep["id"] for ep in all_products]:
                            all_products.append(p)

                # Collect comparison data
                if tc["name"] == "compare_products":
                    all_products.extend(
                        p for p in tool_result.get("products", [])
                        if p["id"] not in [ep["id"] for ep in all_products]
                    )
                    comparison_data = tool_result

            # Step 3: Follow-up call with tool results
            # Add assistant's tool-use message and tool results to messages
            if model_name != "mock":
                follow_up_span = trace.span("llm-followup", {"model": model_name})

                # Add assistant message with tool calls
                tool_call_content = f"I'll use the {result['tool_calls'][0]['name']} function to help with that."
                messages.append({"role": "assistant", "content": tool_call_content})

                # Add tool results as user messages (simplified — in production
                # you'd use proper tool message format)
                for tr in tool_results:
                    if tr["name"] == "search_products":
                        formatted = _format_search_results_as_text(tr["result"])
                    elif tr["name"] == "compare_products":
                        comp = tr["result"]
                        formatted = json.dumps({
                            "products": [{"name": p["name"], "id": p["id"],
                                          "price": p["price"]} for p in comp.get("products", [])],
                            "recommendation": comp.get("recommendation"),
                        })
                    elif tr["name"] == "get_product_details":
                        product = tr["result"].get("product", {})
                        formatted = json.dumps(product)
                    else:
                        formatted = json.dumps(tr["result"])
                    messages.append({"role": "user", "content": f"Tool result for {tr['name']}: {formatted}"})

                messages.append({
                    "role": "user",
                    "content": "Please provide a natural, helpful response to the user based on these results. "
                               f"Format product references as [PRODUCT:product_id]. {user_message}"
                })

                if model_name == "claude":
                    follow_up = _call_claude(messages, TOOLS)
                else:
                    follow_up = _call_openai(messages, TOOLS)

                follow_up_span.input_data = "tool results + follow-up prompt"
                follow_up_span.end(
                    output=follow_up["content"][:200],
                    tokens_used=follow_up["usage"]["input_tokens"]
                    + follow_up["usage"]["output_tokens"],
                )
                total_tokens += (follow_up["usage"]["input_tokens"]
                                 + follow_up["usage"]["output_tokens"])
                result["content"] = follow_up["content"]

        # Step 4: If mock mode and search results exist, format a nice response
        if model_name == "mock" and all_products:
            # Detect if user message is primarily Chinese
            chinese_chars = sum(1 for c in user_message if '一' <= c <= '鿿')
            is_chinese = chinese_chars > len(user_message) * 0.3

            product_lines = []
            for p in all_products[:5]:
                product_lines.append(
                    f"[PRODUCT:{p['id']}] **{p['name']}** — ${p['price']:.2f} "
                    f"(Rating: {p['rating']}/5)\n{p['description'][:120]}..."
                )

            if is_chinese:
                result["content"] = (
                    f"为您找到以下与 \"{user_message}\" 相关的商品：\n\n"
                    + "\n\n".join(product_lines)
                    + f"\n\n共找到 {len(all_products)} 件商品。"
                    f"您想了解哪个商品的详细信息，或者对比几个商品吗？"
                )
            else:
                result["content"] = (
                    f"Here's what I found for \"{user_message}\":\n\n"
                    + "\n\n".join(product_lines)
                    + f"\n\nI found {len(all_products)} products. Would you like to see "
                    f"more details about any of these, or would you like to compare a few?"
                )

        # Detect intent
        intent = detect_intent(user_message, result["content"], result["tool_calls"])

        # Build response
        response = {
            "message": result["content"] or "I've found some products for you!",
            "intent": intent.value if isinstance(intent, Intent) else intent,
            "products": all_products,
            "comparison": comparison_data,
            "checkout_url": None,
            "trace_summary": trace.end(),
        }

        return response

    except Exception as e:
        log_error(trace, "chat-error", str(e))
        return {
            "message": "I apologize, but I encountered an error processing your request. "
                       "Please try again.",
            "intent": "general",
            "products": [],
            "comparison": None,
            "checkout_url": None,
            "error": str(e),
            "trace_summary": trace.end(),
        }
