"""
Langfuse observability integration for the Commerce Agent.
Provides tracing, monitoring, and KPI tracking for all LLM interactions.
"""

import os
import time
import uuid
from contextlib import contextmanager
from typing import Optional

# Langfuse will be initialized with environment variables or fall back to local logging
# LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST
_langfuse_client = None


def get_langfuse_client():
    """Get or initialize the Langfuse client.
    Returns None if Langfuse credentials are not configured,
    in which case tracing is logged locally.
    """
    global _langfuse_client
    if _langfuse_client is not None:
        return _langfuse_client

    public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY")
    host = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")

    if public_key and secret_key:
        try:
            from langfuse import Langfuse
            _langfuse_client = Langfuse(
                public_key=public_key,
                secret_key=secret_key,
                host=host
            )
            print(f"[Observability] Langfuse initialized: {host}")
            return _langfuse_client
        except Exception as e:
            print(f"[Observability] Langfuse initialization failed: {e}")
            print("[Observability] Falling back to local logging.")
            return None
    else:
        print("[Observability] Langfuse not configured. Using local logging.")
        print("[Observability] Set LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY to enable.")
        return None


class TraceSpan:
    """Represents a single span within a trace for observability."""

    def __init__(self, name: str, trace_id: str, metadata: dict = None):
        self.name = name
        self.trace_id = trace_id
        self.span_id = str(uuid.uuid4())[:8]
        self.metadata = metadata or {}
        self.start_time = time.time()
        self.end_time = None
        self.input_data = None
        self.output_data = None
        self.error = None
        self.tokens_used = 0

    def end(self, output=None, error=None, tokens_used=0) -> dict:
        """End the span and return span data."""
        self.end_time = time.time()
        self.output_data = output
        self.error = error
        self.tokens_used = tokens_used
        return self.to_dict()

    def to_dict(self) -> dict:
        """Convert span to dictionary for logging/storage."""
        duration_ms = ((self.end_time or time.time()) - self.start_time) * 1000
        return {
            "span_id": self.span_id,
            "trace_id": self.trace_id,
            "name": self.name,
            "duration_ms": round(duration_ms, 2),
            "metadata": self.metadata,
            "input": str(self.input_data)[:500] if self.input_data else None,
            "output": str(self.output_data)[:500] if self.output_data else None,
            "error": self.error,
            "tokens_used": self.tokens_used,
        }


class Trace:
    """Represents a full trace for a single request through the system."""

    def __init__(self, name: str = "chat-request", user_id: str = "anonymous",
                 session_id: str = None):
        self.trace_id = str(uuid.uuid4())
        self.name = name
        self.user_id = user_id
        self.session_id = session_id or str(uuid.uuid4())[:12]
        self.spans: list[TraceSpan] = []
        self.start_time = time.time()
        self._langfuse_trace = None

        # Initialize Langfuse trace if available
        client = get_langfuse_client()
        if client:
            try:
                self._langfuse_trace = client.trace(
                    id=self.trace_id,
                    name=name,
                    user_id=user_id,
                    session_id=self.session_id,
                )
                print(f"[Observability] Trace created: {self.trace_id[:8]}... "
                      f"(session: {self.session_id})")
            except Exception as e:
                print(f"[Observability] WARNING: Langfuse trace creation failed: {e}")
                self._langfuse_trace = None

    def span(self, name: str, metadata: dict = None) -> TraceSpan:
        """Create a new span within this trace."""
        s = TraceSpan(name=name, trace_id=self.trace_id, metadata=metadata)
        self.spans.append(s)
        return s

    def end(self) -> dict:
        """End the trace, log all spans, and return trace summary."""
        total_duration = (time.time() - self.start_time) * 1000
        total_tokens = sum(s.tokens_used for s in self.spans)
        error_spans = [s for s in self.spans if s.error]

        # Log to Langfuse if available
        if self._langfuse_trace:
            try:
                for s in self.spans:
                    gen = self._langfuse_trace.generation(
                        name=s.name,
                        model=s.metadata.get("model", "unknown"),
                        input=s.input_data,
                        output=s.output_data,
                        usage={"total": s.tokens_used} if s.tokens_used else None,
                        metadata=s.metadata,
                    )
                    gen.end()
                self._langfuse_trace.update(
                    output={"total_tokens": total_tokens, "spans": len(self.spans)}
                )
            except Exception as e:
                print(f"[Observability] Langfuse logging error: {e}")

        # Flush to ensure data is sent to Langfuse cloud
        client = get_langfuse_client()
        if client:
            try:
                client.flush()
                print(f"[Observability] Flushed trace {self.trace_id[:8]}... "
                      f"({len(self.spans)} spans, {total_tokens} tokens) → Langfuse cloud")
            except Exception as e:
                print(f"[Observability] WARNING: Langfuse flush failed: {e}")

        return {
            "trace_id": self.trace_id,
            "duration_ms": round(total_duration, 2),
            "span_count": len(self.spans),
            "total_tokens": total_tokens,
            "error_count": len(error_spans),
            "spans": [s.to_dict() for s in self.spans],
        }


def log_llm_call(trace: Trace, span_name: str, model: str,
                 input_text: str, output_text: str,
                 tokens_used: int = 0, metadata: dict = None) -> dict:
    """Convenience function to log an LLM call as a span within a trace."""
    span = trace.span(span_name, metadata={
        "model": model,
        **(metadata or {})
    })
    span.input_data = input_text
    return span.end(output=output_text, tokens_used=tokens_used)


def log_error(trace: Trace, span_name: str, error: str,
              metadata: dict = None) -> dict:
    """Log an error as a span within a trace."""
    span = trace.span(span_name, metadata=metadata)
    return span.end(error=error)
