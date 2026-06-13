"""
SQLite database setup for Commerce Agent.
Stores orders, conversations, and messages for observability and analytics.
"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "commerce.db"


def get_connection() -> sqlite3.Connection:
    """Get a database connection with row factory enabled."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    """Initialize database tables if they don't exist."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            user_id TEXT DEFAULT 'anonymous',
            status TEXT DEFAULT 'active'
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system')),
            content TEXT NOT NULL,
            intent TEXT,
            metadata TEXT DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (conversation_id) REFERENCES conversations(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id TEXT PRIMARY KEY,
            conversation_id TEXT,
            product_id TEXT NOT NULL,
            product_name TEXT NOT NULL,
            quantity INTEGER NOT NULL DEFAULT 1,
            amount REAL NOT NULL,
            currency TEXT DEFAULT 'usd',
            stripe_session_id TEXT,
            status TEXT DEFAULT 'pending'
                CHECK(status IN ('pending', 'checkout_created', 'paid', 'fulfilled', 'cancelled', 'failed')),
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            metric_name TEXT NOT NULL,
            metric_value REAL NOT NULL,
            labels TEXT DEFAULT '{}',
            recorded_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)

    conn.commit()
    conn.close()


def create_conversation(conversation_id: str) -> None:
    """Create a new conversation record."""
    conn = get_connection()
    conn.execute(
        "INSERT INTO conversations (id) VALUES (?)",
        (conversation_id,)
    )
    conn.commit()
    conn.close()


def save_message(conversation_id: str, role: str, content: str,
                 intent: str = None, metadata: dict = None) -> int:
    """Save a message and return its ID."""
    conn = get_connection()
    cursor = conn.execute(
        """INSERT INTO messages (conversation_id, role, content, intent, metadata)
           VALUES (?, ?, ?, ?, ?)""",
        (conversation_id, role, content, intent, json.dumps(metadata or {}))
    )
    conn.execute(
        "UPDATE conversations SET updated_at = datetime('now') WHERE id = ?",
        (conversation_id,)
    )
    conn.commit()
    message_id = cursor.lastrowid
    conn.close()
    return message_id


def create_order(order_id: str, conversation_id: str, product_id: str,
                 product_name: str, quantity: int, amount: float,
                 stripe_session_id: str = None) -> None:
    """Create a new order record."""
    conn = get_connection()
    conn.execute(
        """INSERT INTO orders (id, conversation_id, product_id, product_name,
           quantity, amount, stripe_session_id, status)
           VALUES (?, ?, ?, ?, ?, ?, ?, 'checkout_created')""",
        (order_id, conversation_id, product_id, product_name, quantity,
         amount, stripe_session_id)
    )
    conn.commit()
    conn.close()


def update_order_status(order_id: str, status: str) -> None:
    """Update the status of an order."""
    conn = get_connection()
    conn.execute(
        "UPDATE orders SET status = ?, updated_at = datetime('now') WHERE id = ?",
        (status, order_id)
    )
    conn.commit()
    conn.close()


def get_conversation(conversation_id: str) -> list[dict]:
    """Get all messages in a conversation."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT role, content, intent, metadata, created_at FROM messages "
        "WHERE conversation_id = ? ORDER BY id ASC",
        (conversation_id,)
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_order(order_id: str) -> dict | None:
    """Get an order by ID."""
    conn = get_connection()
    row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_order_by_session(stripe_session_id: str) -> dict | None:
    """Get an order by Stripe session ID."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM orders WHERE stripe_session_id = ?",
        (stripe_session_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_metrics_summary() -> dict:
    """Get aggregated metrics for the dashboard."""
    conn = get_connection()

    total_conversations = conn.execute(
        "SELECT COUNT(*) FROM conversations"
    ).fetchone()[0]

    total_messages = conn.execute(
        "SELECT COUNT(*) FROM messages"
    ).fetchone()[0]

    total_orders = conn.execute(
        "SELECT COUNT(*) FROM orders"
    ).fetchone()[0]

    completed_orders = conn.execute(
        "SELECT COUNT(*) FROM orders WHERE status = 'paid'"
    ).fetchone()[0]

    total_revenue = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM orders WHERE status = 'paid'"
    ).fetchone()[0]

    intents = conn.execute(
        "SELECT intent, COUNT(*) as count FROM messages "
        "WHERE intent IS NOT NULL GROUP BY intent ORDER BY count DESC"
    ).fetchall()

    conn.close()

    return {
        "total_conversations": total_conversations,
        "total_messages": total_messages,
        "total_orders": total_orders,
        "completed_orders": completed_orders,
        "conversion_rate": (completed_orders / total_conversations * 100)
        if total_conversations > 0 else 0,
        "total_revenue": round(total_revenue, 2),
        "intent_distribution": {row["intent"]: row["count"] for row in intents},
    }


def record_metric(metric_name: str, metric_value: float, labels: dict = None) -> None:
    """Record a custom metric for analytics."""
    conn = get_connection()
    conn.execute(
        "INSERT INTO metrics (metric_name, metric_value, labels) VALUES (?, ?, ?)",
        (metric_name, metric_value, json.dumps(labels or {}))
    )
    conn.commit()
    conn.close()
