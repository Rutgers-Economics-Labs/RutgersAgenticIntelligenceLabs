import asyncio
import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).parent.parent.parent))

from app.services.subprocess_code_runner import run_user_code


@pytest.mark.asyncio
async def test_code_streaming(tmp_path):
    # run_user_code requires a DuckDB; create a trivial one so the smoke check
    # actually executes the subprocess instead of bailing on the early return.
    import duckdb

    db_path = tmp_path / "smoke.duckdb"
    conn = duckdb.connect(str(db_path))
    conn.execute("CREATE TABLE IF NOT EXISTS smoke(id INTEGER)")
    conn.close()

    code = (
        "print('Step 1: Initializing...')\n"
        "print('Step 2: Processing data...')\n"
        "print('Step 3: Done!')\n"
    )
    result = await run_user_code(code, timeout_seconds=10, duckdb_path=db_path)
    stdout = result.get("stdout") or ""
    assert "Step 1" in stdout
    assert "Step 3" in stdout
    assert not result.get("error")


if __name__ == "__main__":
    asyncio.run(test_code_streaming())
