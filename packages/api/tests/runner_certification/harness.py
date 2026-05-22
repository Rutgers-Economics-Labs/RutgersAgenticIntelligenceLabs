"""Runner certification harness.

The harness exposes one entry point — `certify_session_result(path,
work_order=None)` — that validates a session_result.json file against the
protocol and optionally checks consistency with the dispatching work order.

In Phase 0 the only consumer is the stub-runner test. In Phase 1+ the same
harness will be called against each real runner's output.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError

from app.runners.contracts import SessionResult, WorkOrder


@dataclass
class CertificationResult:
    """Outcome of one certification run.

    passed=True means the session_result.json validates AND is consistent
    with the work order (if provided). Any issue lands in `issues` — keep
    going past the first problem so we surface everything at once instead
    of forcing fix-test-fix cycles.
    """

    passed: bool
    issues: list[str] = field(default_factory=list)
    parsed: SessionResult | None = None

    def __bool__(self) -> bool:
        return self.passed


def certify_session_result(
    session_result_path: Path | str,
    *,
    work_order: WorkOrder | None = None,
) -> CertificationResult:
    """Validate a session_result.json against the protocol.

    Args:
        session_result_path: Path to the session_result.json on disk.
        work_order: If provided, additionally check consistency between
            the result and the dispatching work order — task_type matches,
            work_order_id is set, required outputs are present.
    """
    path = Path(session_result_path)
    issues: list[str] = []

    if not path.is_file():
        return CertificationResult(passed=False, issues=[f"session_result not found at {path}"])

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return CertificationResult(passed=False, issues=[f"session_result is not valid JSON: {exc}"])

    try:
        parsed = SessionResult.model_validate(raw)
    except ValidationError as exc:
        # Surface every field-level error, not just the first, so authors
        # can fix them in one pass.
        for err in exc.errors():
            loc = ".".join(str(part) for part in err.get("loc", ()))
            issues.append(f"schema: {loc}: {err.get('msg')}")
        return CertificationResult(passed=False, issues=issues)

    if work_order is not None:
        issues.extend(_check_work_order_consistency(parsed, work_order))

    return CertificationResult(passed=not issues, issues=issues, parsed=parsed)


def _check_work_order_consistency(result: SessionResult, work_order: WorkOrder) -> list[str]:
    """Consistency checks between a session_result and its work order.

    These are checks the schema alone can't enforce because they're
    cross-document invariants. Kept narrow: only checks that catch real
    bugs (wrong work_order_id, wrong task_type, missing required outputs),
    not style preferences.
    """
    issues: list[str] = []

    if result.work_order_id is None:
        issues.append(
            f"work_order_id is missing on session result, but a work order "
            f"({work_order.work_order_id}) was dispatched"
        )
    elif result.work_order_id != work_order.work_order_id:
        issues.append(
            f"work_order_id mismatch: result reports {result.work_order_id!r}, "
            f"work order is {work_order.work_order_id!r}"
        )

    if result.task_type != work_order.task_type:
        issues.append(
            f"task_type mismatch: result reports {result.task_type.value!r}, "
            f"work order requested {work_order.task_type.value!r}"
        )

    # Required outputs are declared in the work order; spot-check that the
    # session_result has the corresponding fields populated.
    output_checks = {
        "claims": lambda r: bool(r.claims),
        "sources": lambda r: bool(r.sources),
        "datasets": lambda r: bool(r.datasets),
        "verification_command": lambda r: r.verification is not None,
        "session_result_json": lambda _r: True,  # trivially true if we're here
    }
    for required in work_order.outputs_required:
        check = output_checks.get(required)
        if check is None:
            # Unknown output type — don't fail certification, but note it.
            # Phase 5+ may add new output types and we don't want this
            # harness to silently lock the vocabulary.
            continue
        if not check(result):
            issues.append(
                f"work order requires output {required!r} but session result "
                f"does not populate the corresponding field"
            )

    return issues
