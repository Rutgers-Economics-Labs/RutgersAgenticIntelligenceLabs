# Task: Verify Contact Route And Draft Email

## Goal

For one shortlisted organization, verify the best contact route and leave behind an outreach-ready artifact.

## Runner

- role: `research`
- runner: `codex_cli`
- model: `gpt-5.4`

## Contact workflow

Use this order:
1. official staff or leadership page
2. official research or program page
3. official contact or partnership page
4. official report or announcement naming staff
5. official fallback inbox or contact form

## Required outputs

1. A memo under `topics/findings/` with these sections:
   - Facts
   - Interpretation
   - Open Questions
   - Recommended Contact Route
   - Draft Email
2. At least one draft email under `artifacts/emails/`
3. One next-step recommendation
4. One or two named people when supported by official public evidence
5. At least one verified official fallback route even if no named person is public

## Closeout rule

This task fails if any of the following are missing:
- a verified contact route
- a draft email
- a next step
