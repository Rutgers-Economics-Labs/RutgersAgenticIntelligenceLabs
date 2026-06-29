# Task: Discover Net-New Organizations

## Goal

Find organizations that are not already present in the active REL KB and are worth adding to the pipeline.

## Runner

- role: `research`
- runner: `codex_cli`
- model: `gpt-5.4`

## Search priorities

Prioritize:
- New Jersey public-interest organizations
- policy research organizations
- redevelopment and community-development groups
- housing, transportation, energy, workforce, and public-data institutions
- civic-corporate organizations with clear local or economic-analysis relevance

Avoid promoting:
- prestige-only targets with no clear REL angle
- generic companies with no public-interest research lane
- organizations already captured in the active shortlist unless the task is specifically to deepen them

## Required outputs

1. A memo under `topics/findings/` with:
   - Facts
   - Interpretation
   - Open Questions
   - Recommended additions
2. A shortlist of 3-10 net-new organizations
3. A one-sentence project angle for each
4. Official evidence URLs for each recommendation

## Closeout rule

This task is not complete unless the memo clearly distinguishes net-new additions from already-known targets.
