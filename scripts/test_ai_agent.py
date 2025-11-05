#!/usr/bin/env python3
"""
Quick script to validate the Azure AI agent end-to-end using DefaultAzureCredential.

Usage:
  python scripts/test_ai_agent.py "<your question>"

Requirements:
  - PROJECT_CONNECTION_STRING_AI must be set (in env or .env)
  - Local auth via Azure CLI (az login) or env vars for service principal
"""

import os
import sys
import json
import logging
from pathlib import Path
from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential  # noqa: F401  (ensure SDK present)

# Ensure project root on sys.path so `src` resolves regardless of CWD
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.ai_agent import GrowattAIAgent  # noqa: E402


def main():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    logger = logging.getLogger("test_ai_agent")

    # Load env
    load_dotenv()

    # Validate required config
    pcs = os.getenv("PROJECT_CONNECTION_STRING_AI")
    if not pcs:
        logger.error("PROJECT_CONNECTION_STRING_AI is missing. Set it in your environment or .env file.")
        sys.exit(1)

    # Determine query
    if len(sys.argv) > 1:
        user_query = sys.argv[1]
    else:
        user_query = "Analyze yesterday's solar generation disruptions for inverter CLJACLR001."

    # Optional demo context
    context = {
        "device_sn": "CLJACLR001",
        "date": "2024-07-15"
    }

    try:
        logger.info("Initializing GrowattAIAgent...")
        agent = GrowattAIAgent()
        logger.info("Agent initialized. Sending test query...")

        # process_query is async; run via asyncio if needed
        import asyncio

        async def run_test():
            return await agent.process_query(user_query=user_query, context=context)

        result = asyncio.run(run_test())

        logger.info("Agent response received. Printing JSON result:")
        print(json.dumps(result, indent=2, ensure_ascii=False))

    except Exception as e:
        logger.error(f"AI agent test failed: {e}")
        sys.exit(2)


if __name__ == "__main__":
    main()


