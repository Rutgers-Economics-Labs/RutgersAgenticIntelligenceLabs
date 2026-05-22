# Planner UX And Control-Plane Problems Exposed By The Soccer Project

## Summary

The main issue is not that the planner is unintelligent. The issue is that the system makes it too hard to tell whether the planner, the runner, the repo mirror, and the active ontology all agree.

That creates long recovery loops.

## Biggest Problems

## 1. Hidden State Splits

The same task can exist in several forms:

- DB-backed live task row
- repo-backed task markdown
- mirrored `task_board.md`
- session summaries
- planner thread messages

When those disagree, the UI does not clearly tell the user which one is real.

Impact:

- work appears incomplete when it is already done
- stale tasks stay visible
- users lose confidence in whether the planner is advancing the project

## 2. Truncated Ghost Task Files

Long task ids repeatedly produced truncated duplicate files.

Impact:

- ghost rows reappeared on the board
- already-completed tasks looked backlog or ready again
- manual cleanup was required several times

This is one of the highest-severity usability problems because it silently corrupts the operator’s understanding of reality.

## 3. Stale Running Sessions

Workers and planners sometimes remained `running` long after the useful work was already finished or published.

Impact:

- autopilot thought the execution lane was occupied
- ready tasks did not launch
- humans had to manually cancel stale sessions

The UI should detect and surface this automatically.

## 4. Weak “What Is Blocking Us?” Visibility

During the soccer project, the real blocker shifted many times:

- source config incompleteness
- empty pipeline
- publish path bug
- ontology promotion bug
- stale active artifact pointer
- workflow contract mismatch
- stale runtime session
- final report approval

But the UI did not give a single current blocker view.

Impact:

- too much time spent reconstructing the true bottleneck from logs

## 5. Approval Flow Is Too Implicit

Tasks can be `awaiting_approval`, `ready`, `granted`, or implicitly runnable, but this is not obvious enough from the board alone.

Impact:

- it is not obvious whether a task needs user action, autopilot action, or manual launch
- “why didn’t this start?” is often unclear

## 6. Planner Can Occupy The Lane With Low-Value Closeout Work

Autopilot sometimes launched planner reconciliation or closeout sessions while a more important data or research task needed the lane.

Impact:

- work advanced in the wrong order
- humans had to cancel lower-priority planner sessions manually

The UI should expose execution priority and lane occupancy directly.

## 7. Hydration Success Was Not The Same As Active Ontology Success

A widened ontology could exist on disk before the project’s active ontology pointers were updated.

Impact:

- the API still showed stale counts
- the UI looked broken even though the data work had succeeded

The UI needs a separate concept for:

- `hydration artifact exists`
- `hydration artifact is active`
- `ontology endpoints are serving the new artifact`

## 8. Workflow Contracts Are Opaque

Several tasks “failed” not because the work was wrong, but because the workflow contract wanted:

- provenance
- freshness
- specific Markdown sections
- claims records
- verification metadata

Impact:

- users cannot tell whether the planner failed analytically or administratively

The UI should surface unmet workflow-contract requirements as first-class checklists.

## 9. Not Enough User Steering Primitives

The user often needed to say things like:

- stop planning and go get more leagues
- stop drifting and write the file
- do not keep researching the dead source
- prioritize the final report now

Those are common actions. They should be UI primitives, not ad hoc chat interventions.

## 10. Closeout Is Not Explicit Enough

Near the end, the project had:

- hydrated ontology
- cross-competition panel
- domestic research outputs
- cross-league linkage outputs

But the system still needed manual effort to identify the remaining open item and verify completion state.

Impact:

- finalization takes longer than it should
- users do not know when the system is “almost done” versus actually blocked

## What Would Have Saved The Most Time

If only three things were fixed, I would choose:

1. canonical task identity with duplicate-file detection
2. explicit current blocker view
3. stale-session detection with one-click reconcile or replace

Those three issues caused the largest amount of wasted operator time.

## Product Direction

The UI should evolve from a passive board viewer into an execution console.

It should help the user answer:

- What is actually happening?
- What is the single blocker?
- Which state source is authoritative?
- What one action should I take next if I want to redirect the project?

That is the right model for supervising planner-driven research execution.
