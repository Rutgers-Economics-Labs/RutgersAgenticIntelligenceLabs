# Security Policy

Report sandbox escapes, path-policy bypasses, unauthorized execution, secret exposure, or
cross-project access privately through GitHub Security Advisories.

## Trust model

A registered KRAIL project may contain untrusted workflows and files. RAIL therefore:

- canonicalizes managed and linked workspace paths;
- permits linked paths only below configured `RAIL_LINKED_PROJECT_ROOTS`;
- keeps dirty, unborn, and non-Git linked projects read-only;
- selects immutable server-owned permission profiles by name;
- disables full access unless `RAIL_FULL_ACCESS_ENABLED=true`;
- uses exact argv execution and requires an enforcing sandbox for restricted commands;
- filters environments and does not expose secret values through platform DTOs;
- isolates concurrent mutations in Git worktrees and validates before integration.

The local macOS restricted backend uses Apple-deprecated `sandbox-exec`. It is a compatibility
backend, not a hosted Linux security boundary. Linux hosting requires a bwrap/container provider.

## Operator guidance

- Review projects before registration and grant the smallest linked root possible.
- Do not enable full access for untrusted workflows.
- Bind the local API to loopback unless a real authentication/reverse-proxy layer is configured.
- Protect `.rail/platform-projects.json` and `.rail/platform-runs.json` as operational metadata.
- Keep API/provider keys outside Git and inject only names required by an approved profile.

RAIL does not currently claim multi-user or internet-facing authorization. The supported release is
local single-node operation.
