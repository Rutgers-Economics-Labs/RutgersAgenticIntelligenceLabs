"""Runner certification test harness.

Phase 0 deliverable from docs/future-spec-runner-protocol.md.

The harness is what lets us answer "does this runner satisfy the RAIL
protocol?" with a yes/no, not "we wired up the adapter." It runs three
classes of tests:

1. Contract validation — schemas accept good payloads, reject bad ones.
2. Stub-runner certification — a fake runner emits a known-good
   session_result.json against a fixture work order; harness verifies.
3. (Phases 1+) Live-runner certification — same harness, real CLI.
"""
