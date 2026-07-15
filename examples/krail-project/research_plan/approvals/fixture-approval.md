---
approval_id: fixture-approval
status: pending
description: Confirm that the fixture evidence may be used for adapter verification.
workflow_run_id: fixture-run
workflow_step_id: approval
subject_digest: sha256:fixture
requested_by: fixture-bot
allow_decisions:
  - approved
  - rejected
  - changes_requested
minimum_approvals: 1
---

## Request

Approve the deterministic fixture evidence for the adapter contract suite.
