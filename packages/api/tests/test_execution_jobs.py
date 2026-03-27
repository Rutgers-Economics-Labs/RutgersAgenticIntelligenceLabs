import asyncio
import os
import sys
from pathlib import Path

# Add app to path
sys.path.append(str(Path(__file__).parent.parent.parent))

from app.services.subprocess_code_runner import run_user_code
from app.services.convex_client import convex

async def test_code_streaming():
    print("Starting code streaming test...")
    # This assumes a mock job_id or a valid one if we want to check Convex
    # For local verification, we'll just check if it runs without error and logs to stdout locally
    
    code = """
import time
print("Step 1: Initializing...")
time.sleep(1)
print("Step 2: Processing data...")
time.sleep(1)
print("Step 3: Done!")
"""
    
    result = await run_user_code(code, timeout_seconds=10)
    print("\nResult:")
    print(f"Stdout: {result.get('stdout')}")
    print(f"Error: {result.get('error')}")

if __name__ == "__main__":
    asyncio.run(test_code_streaming())
