# Public Release Checklist

Use this before making RAIL public, tagging a release, or publishing a fork.

## Source scope

- [ ] Platform source code is included: `apps/`, `packages/`, `scripts/`, core docs, tests.
- [ ] Large generated projects are not tracked.
- [ ] Validation runs, local sessions, audit traces, ontology databases, and cache files are not tracked.
- [ ] Public examples live under `examples/` and are small enough to review.
- [ ] Any submodules are intentional and documented.

## Secrets

- [ ] `.env` is absent from `git status --short`.
- [ ] Local key files such as `uploaded_key`, `*.pem`, and `*.key` are absent.
- [ ] Any previously exposed keys have been rotated.
- [ ] Git history has been reviewed before making a private repo public.

Suggested scan:

```bash
git grep -n -I -E 'AKIA[0-9A-Z]{16}|sk-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9_]{20,}|PRIVATE KEY' -- ':!apps/web/package-lock.json'
```

## Fresh clone test

- [ ] `./scripts/install-rail.sh` completes on a clean machine.
- [ ] `cp .env.example .env` gives a clear config path.
- [ ] `make run` starts API and web UI.
- [ ] `rail --help` works after install.
- [ ] `curl -s http://localhost:8000/health` returns healthy status.

## Documentation

- [ ] README explains what RAIL is in the first screen.
- [ ] README has a working quick start.
- [ ] `SECURITY.md` explains vulnerability reporting and secret handling.
- [ ] `CONTRIBUTING.md` explains repo hygiene and tests.
- [ ] Release docs describe the current install path.

## Release

- [ ] Version numbers are updated where applicable.
- [ ] Release workflow has permission to create releases.
- [ ] Release assets do not include ignored local workspaces.
- [ ] Optional PyPI settings are configured only if publishing packages.
