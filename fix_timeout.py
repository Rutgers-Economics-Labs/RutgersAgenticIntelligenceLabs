# If tests are timing out, perhaps the background task hangs?
import re
with open("packages/api/tests/test_execute_and_analysis_code.py", "r") as f:
    content = f.read()

# Make sure we don't mock it so that it hangs, let's see.
# It's probably hanging because it's waiting for the background job to finish but the event loop gets closed.
# The code runner uses `asyncio.create_task` inside the request handler.
