# Jules Runbook

This runbook describes how we should hand the future work-order queue to Jules without losing control of branch state or accidentally re-running already finished foundation work.

## Preconditions

- local work for `in_progress` items is committed first
- `JULES_API_KEY` is set
- `gh` is authenticated if branch extraction from PRs is required
- the working branch is `future` unless explicitly overridden

## Runner Behavior

The Jules runner should:

- read `state/work-orders/WO-F*.md`
- parse each work order's `Status` and `Depends on` metadata
- skip `completed`
- skip `in_progress`
- default to only `pending` work orders whose dependencies are `completed`
- ask for human confirmation before creating each remote session
- pause for human input if Jules asks a question instead of auto-confirming blindly

## Recommended First Jules Batch

Once current local work is committed, the first batch should usually be:

- `WO-F2.1`
- `WO-F2.2`
- `WO-F2.3`
- `WO-F3.3`
- `WO-F3.4`
- `WO-F3.5`

## Suggested Environment Variables

- `JULES_API_KEY`
- `JULES_SOURCE`
  Default should point at the canonical GitHub repo source.
- `STARTING_BRANCH`
  Default should be `future`.
- `WORK_ORDER_IDS`
  Optional comma-separated allowlist, for example `WO-F2.1,WO-F2.2`.
- `MAX_ORDERS`
  Optional cap for a single run.
- `DRY_RUN`
  When set, print the ready queue and exit without creating sessions.
- `AUTO_APPROVE`
  When set to `1`, skip the per-session confirmation prompt.

## Safety Notes

- Keep runs sequential in V1.
- Review each PR before advancing the next baseline branch.
- Treat `AWAITING_USER_FEEDBACK` as a real interrupt that should be surfaced to a human.
- If Jules finishes without a PR, stop the chain and inspect the session before continuing.
