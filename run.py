#!/usr/bin/env python3
"""
Commerce Agent - Application Launcher

Starts the FastAPI backend server for the Commerce Agent chatbot.

Usage:
    python run.py                  # Start server (default: localhost:8000)
    python run.py --port 8080      # Start on custom port
    python run.py --host 0.0.0.0   # Bind to all interfaces
    python run.py --reload         # Enable auto-reload for development

Environment Variables:
    ANTHROPIC_API_KEY    - Anthropic API key for Claude models
    OPENAI_API_KEY       - OpenAI API key for GPT models
    STRIPE_SECRET_KEY    - Stripe secret key (test mode)
    STRIPE_WEBHOOK_SECRET- Stripe webhook signing secret
    LANGFUSE_PUBLIC_KEY  - Langfuse public key for observability
    LANGFUSE_SECRET_KEY  - Langfuse secret key for observability
    LANGFUSE_HOST        - Langfuse host URL (default: cloud.langfuse.com)
    BASE_URL             - Public base URL for Stripe redirects
"""
from dotenv import load_dotenv
load_dotenv()   
import argparse
import os
import sys
import uvicorn



def main():
    parser = argparse.ArgumentParser(
        description="Commerce Agent - AI Shopping Assistant Server"
    )
    parser.add_argument(
        "--host", default="127.0.0.1",
        help="Host to bind to (default: 127.0.0.1)"
    )
    parser.add_argument(
        "--port", type=int, default=8000,
        help="Port to bind to (default: 8000)"
    )
    parser.add_argument(
        "--reload", action="store_true",
        help="Enable auto-reload for development"
    )
    args = parser.parse_args()

    # Print banner
    
    print("  CommerceBot -- AI Shopping Assistant")
    
    print()

    # Check configuration
    config_ok = True
    if os.getenv("ANTHROPIC_API_KEY"):
        print("  [OK] Anthropic API key configured -- using Claude")
    elif os.getenv("OPENAI_API_KEY"):
        print("  [OK] OpenAI API key configured -- using GPT")
    else:
        print("  [!!] No LLM API key found -- using mock mode")
        print("       Set ANTHROPIC_API_KEY or OPENAI_API_KEY for AI-powered chat")
        config_ok = False

    if os.getenv("STRIPE_SECRET_KEY"):
        print("  [OK] Stripe secret key configured -- real checkout enabled")
    else:
        print("  [!!] No Stripe key found -- using demo checkout mode")
        print("       Set STRIPE_SECRET_KEY for real Stripe payments")

    if os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"):
        print("  [OK] Langfuse configured -- observability enabled")
    else:
        print("  [i]  Langfuse not configured -- local logging only")
        print("       Set LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY to enable")

    print()
    print(f"  Starting server at http://{args.host}:{args.port}")
    print(f"  Chat UI:     http://{args.host}:{args.port}/")
    print(f"  API Docs:    http://{args.host}:{args.port}/api/docs")
    print(f"  Dashboards:  http://{args.host}:{args.port}/dashboards/observability.html")
    print()
    print("  Press Ctrl+C to stop")
    print("=" * 60)

    # Run the server
    try:
        uvicorn.run(
            "backend.main:app",
            host=args.host,
            port=args.port,
            reload=args.reload,
            log_level="info",
        )
    except SystemExit:
        pass
    except Exception as e:
        # Check if it's a port-in-use error
        if "10048" in str(e) or "bind" in str(e).lower() or "address" in str(e).lower():
            print()
            print(f"  [ERROR] Port {args.port} is already in use!")
            print(f"  Run this to free it:")
            print(f"    taskkill //F //IM python.exe")
            print()
            print(f"  Or use a different port:")
            print(f"    python run.py --port 8001")
        else:
            raise


if __name__ == "__main__":
    main()
