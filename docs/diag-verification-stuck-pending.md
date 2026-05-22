# Diagnostic Report: Workspace Verification Stuck in Pending

## 1. Files, Line Numbers, and Functions Involved

The tracking and update of the `workspace_verification` check involves the following components in the codebase:

### Check Creation and Defaults
- **File:** `packages/api/app/services/session_files.py`
  - **Function:** `ensure_session_root(...)`
  - **Line 94:** Initializes `"verification_status": None` when creating the `state.json` file for a new agent session.
- **File:** `packages/api/app/runners/session_lifecycle.py`
  - **Function:** `_normalize_completion_summary(...)`
  - **Line 812:** Reads `verification_status` from the session state.
  - **Lines 823–829:** Dynamically constructs the `checks` array and populates the `workspace_verification` check with `"status": verification_status or "pending"`. Because the initial value is `None`, it defaults to `"pending"`.

### Check Execution and State Updates
- **File:** `packages/api/app/runners/session_lifecycle.py`
  - **Function:** `_finalize_workspace_review(...)`
  - **Lines 1977–1983:** Evaluates `should_rerun_verification`. It only triggers verification if `terminal_status == "completed"` and no publishing errors exist (`not publish_error`).
  - **Lines 1985–1994:** Runs `_run_workspace_verification(...)` if the above condition is met.
  - **Function:** `_run_workspace_verification(...)`
  - **Line 1845:** Invokes `_run_workspace_hook(...)` with `state_prefix="verification"`.
  - **Function:** `_run_workspace_hook(...)`
  - **Lines 1681–1691:** Executes the verification script (usually `scripts/run-verification.sh`) and updates the state on disk using `session_files.update_state(session_root, **{f"{state_prefix}_status": status})`, transitioning `verification_status` to a terminal status (`"passed"`, `"failed"`, or `"skipped"`).

### Post-Run Auditing
- **File:** `packages/api/app/services/audit_service.py`
  - **Function:** `write_post_run_audit(...)`
  - **Line 431:** Builds the post-run audit JSON structure using `"verificationStatus": state.get("verification_status") or "pending"`, which persists the `"pending"` value to the audit certificate.

---

## 2. Sequence of Events Leading to Check Remaining "pending"

1. **Session Failure:** An agent session fails during execution, causing the session lifecycle manager to mark the session with `status = "failed"`.
2. **Review Finalization:** The runner executes the finalization workflow by calling `_finalize_workspace_review(...)` with `terminal_status = "failed"`.
3. **Skipping Verification Rerun:** Because `terminal_status` is not `"completed"` (or because a `publish_error` was caught during the publish step), `should_rerun_verification` evaluates to `False`. The code branch calling `_run_workspace_verification(...)` is skipped entirely.
4. **State Preservation:** The session `verification_status` remains `None` inside `state.json` (its initial bootstrap value).
5. **Constructing the Summary:** `_normalize_completion_summary(...)` is called. It retrieves the `verification_status` from the state. Since the status is `None`, the `workspace_verification` check is appended to the completion summary with the status `"pending"`.
6. **Durable Audit Creation:** `write_post_run_audit(...)` writes the completion summary directly to the session's audit JSON and Markdown files. The closeout and integrity gates read this file, see that a verification run is `"pending"`, and block the project promotion indefinitely.

---

## 3. Proposed Fix

In `packages/api/app/runners/session_lifecycle.py` inside `_finalize_workspace_review`, we should explicitly update the session's `verification_status` to `"failed"` when a session does not complete successfully or fails to publish. By setting `session_files.update_state(session_root, verification_status="failed")` when `terminal_status in {"failed", "cancelled"}` or when a `publish_error` occurs, we ensure that the session's verification status is transitioned to a terminal `"failed"` state. This prevents verification from remaining stuck as `"pending"`, allows auditors to immediately recognize that the run failed, and yields clean, actionable error states in the research integrity ledger.
