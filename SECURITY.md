# Security Policy

## Supported versions

RAIL is pre-1.0. Security fixes are applied to the default branch first. Tagged releases may receive follow-up fixes when a release asset is affected.

## Reporting a vulnerability

Please do not open a public issue for secrets, credential exposure, sandbox escapes, auth bypasses, or remote execution risks.

Report privately to the maintainers through the repository owner's preferred security contact. If GitHub private vulnerability reporting is enabled for this repository, use that channel.

Include:

- affected commit, tag, or release
- reproduction steps
- impact and affected component
- whether credentials, private data, or remote execution are involved

## Secret handling

RAIL should never require committing secrets. Use `.env` locally and project secret storage in cloud mode.

Never commit:

- `.env`
- Convex deploy keys
- GitHub App private keys
- OpenAI, Anthropic, Google, FRED, or other provider API keys
- private key files such as `*.pem`, `*.key`, `*.p12`, or `*.pfx`

If a secret may have been committed or shared:

1. Revoke or rotate it at the provider.
2. Remove it from the current tree.
3. Inspect Git history before publishing.
4. Use history rewriting only on branches where every collaborator agrees.

## Local execution risks

RAIL includes tools for running project code and agent workflows. Treat untrusted project workspaces as code:

- review `rail.yaml`, scripts, and agent prompts before running
- keep `RAIL_EXECUTE_ENABLED=false` unless code execution is needed
- prefer sandboxed execution for untrusted projects
- do not inject broad secret sets into agent sessions

## Public release checklist

Before making a repository public or cutting a release:

```bash
git status --short
git grep -n -I -E 'AKIA[0-9A-Z]{16}|sk-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9_]{20,}|PRIVATE KEY' -- ':!apps/web/package-lock.json'
```

Also check that large local workspaces remain ignored:

```bash
git ls-files docs/validation generated_projects
```
