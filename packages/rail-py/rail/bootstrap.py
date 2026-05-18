from __future__ import annotations

from pathlib import Path
import textwrap
import yaml


def _slugify(value: str) -> str:
    slug = "".join(ch.lower() if ch.isalnum() else "-" for ch in value)
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-")


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def bootstrap_future_project(
    target_dir: str | Path,
    *,
    name: str,
    slug: str | None = None,
    default_branch: str = "main",
) -> Path:
    project_root = Path(target_dir).resolve()
    project_slug = slug or _slugify(name)

    dirs = [
        ".ontology/sources",
        ".ontology/pipelines",
        ".ontology/transforms",
        ".rail/workspaces",
        "topics",
        "specs",
        "research_plan/graph",
        "research_plan/state",
        "research_plan/tasks",
        "agents/prompts",
        "agents/checklists",
        "skills",
        "artifacts",
        "scripts",
    ]
    for rel in dirs:
        (project_root / rel).mkdir(parents=True, exist_ok=True)

    rail_yaml = textwrap.dedent(
        f"""\
        version: 1

        project:
          name: "{name}"
          slug: "{project_slug}"
          default_branch: "{default_branch}"
          description: "RAIL future project"
          mode: "ontology_first"

        repo_contract:
          required_paths:
            - ".ontology"
            - "specs"
            - "research_plan"
            - "topics"
            - "agents"
            - "skills"
          flexible_paths:
            - "artifacts"
            - "topics/**"
          source_of_truth: "git"

        paths:
          ontology_root: ".ontology"
          topics_root: "topics"
          specs_root: "specs"
          plan_root: "research_plan"
          agents_root: "agents"
          skills_root: "skills"
          artifacts_root: "artifacts"

        hydration:
          ontology_file: ".ontology/ontology.yaml"
          sources_dir: ".ontology/sources"
          pipelines_dir: ".ontology/pipelines"
          transforms_dir: ".ontology/transforms"
          hydration_mode: "full"

        research:
          brief_path: "topics/brief.md"
          spec_path: "specs/research_question.yaml"
          question_policy:
            allow_follow_up_generation: true
            allow_midstream_direction_change: true
            require_question_classification: true
            allowed_classifications:
              - "answerable_now"
              - "answerable_after_requery"
              - "answerable_after_expansion"
              - "blocked_by_data"

        planner:
          current_plan_path: "research_plan/current_plan.md"
          task_root: "research_plan/tasks"
          approval_root: "research_plan/approvals"
          decision_root: "research_plan/decisions"
          require_audit_before_advance: true
          lane_policy: "single_active_worker"

        agents:
          roles_dir: "agents"
          default_runner: "codex_cli"
          sequential_execution: true
          planner_thread_mode: "project"
          default_planner_role: "planner"

        auditors:
          enabled: true
          order:
            - "session"
            - "planner"
            - "ontology"
            - "integrity"
            - "closeout"
          fail_closed: true

        autonomy:
          mode: "assisted"
          require_human_for:
            - "publish_changes"
            - "destructive_delete"
            - "missing_source_data"
            - "low_confidence_claims"
            - "methodology_change_with_material_effect"
          allow_without_human:
            - "plan_decomposition"
            - "source_discovery"
            - "data_ingestion"
            - "analysis_scripts"
            - "artifact_generation"
            - "verification"
            - "assumption_recording"
          max_runtime_minutes: 180
          max_cost_usd: 20
          max_retries_per_task: 3

        integrity:
          allow_synthetic_data: false
          require_source_for_datasets: true
          require_lineage_for_final_artifacts: true
          require_evidence_for_report_claims: true
          stale_outputs_block_promotion: true

        verification:
          deterministic_command: "scripts/run-verification.sh"
          require_integrity_gate_for:
            - "artifact_generation"
            - "closeout"
          require_ontology_health_before:
            - "research"
            - "artifact"
          required_artifact_lineage: true
          required_claim_evidence: true

        secrets:
          project_scope: true
          per_agent_allowlists: true
          inject_at_session_start_only: true
          allowed: {{}}

        lifecycle:
          phases:
            - "brief"
            - "scoped"
            - "source_discovery"
            - "config_ready"
            - "hydration_ready"
            - "hydrated"
            - "ontology_healthy"
            - "research_active"
            - "synthesis_ready"
            - "closed"
          closeout_requires:
            - "no_active_agents"
            - "no_non_done_required_tasks"
            - "clean_integrity_gate"
            - "final_artifacts_present"

        workspaces:
          mode: "isolated"
          root: ".rail/workspaces"
          setup_script: "scripts/setup-workspace.sh"
          verification_script: "scripts/run-verification.sh"
          archive_script: "scripts/archive-workspace.sh"
          nonconcurrent_run: true
          checkpoint_mode: "git-ref"

        frontend:
          topic_index_mode: "filesystem"
          artifact_index_mode: "filesystem"
          show_repo_tree: true
          show_task_board_snapshot: true
          default_home_view: "project_home"
        """
    )

    ontology_yaml = textwrap.dedent(
        """\
        uri: http://rail.rutgers.edu/ontology/project
        classes: []
        data_properties: []
        object_properties: []
        """
    )

    current_plan = textwrap.dedent(
        f"""\
        # Current Plan

        Project: {name}

        ## Objective

        Define the first approved plan for this project.

        ## Next Steps

        - refine project requirements
        - create initial tasks
        - approve the first worker run
        """
    )

    task_board = textwrap.dedent(
        """\
        # Task Board

        ## Backlog

        - Define first execution plan

        ## Ready

        None yet.

        ## Awaiting Approval

        None yet.

        ## Running

        None.

        ## Blocked

        None.

        ## Review

        None.

        ## Done

        None.
        """
    )

    def role_template(role: str, purpose: str, read: list[str], write: list[str], secrets: list[str], tools: list[str]) -> str:
        payload = {
            "role": role,
            "label": f"{role.title()} Agent",
            "purpose": purpose,
            "runner": {
                "default": "codex_cli",
                "approval_required": role == "planner",
                "max_retries": 3,
                "timeout_minutes": 20,
                "bash_access": True,
            },
            "threading": {
                "mode": "project_scoped" if role == "planner" else "task_scoped",
            },
            "permissions": {
                "read": read,
                "write": write,
                "deny": [],
            },
            "secrets": {
                "allow": secrets,
            },
            "skills": {
                "allow_use": True,
                "root": "skills",
            },
            "tools": {
                "allow": tools,
                "deny": [],
            },
            "prompts": {
                "system": f"agents/prompts/{role}.md",
                "checklist": f"agents/checklists/{role}.md",
            },
            "completion": {
                "requires": ["task_documented"],
            },
        }
        return yaml.safe_dump(payload, sort_keys=False)

    def prompt_template(role: str) -> str:
        if role == "planner":
            return """# RAIL Planner Prompt

You are the planner for the RAIL project `{{project_name}}` (`{{project_slug}}`).

You are the only user-facing agent and the control loop for the project.
Your job is to:

1. Understand the user's desired state and compare it with the repo's current state.
2. Write and maintain durable project state in Git, especially under `research_plan/`.
3. Decide whether to answer directly, update project files, create tasks, request approval, or launch a worker.
4. Use project role configs as the source of truth for runner choice, path policy, and skill access.
5. Preserve deep research, ontology, data, coding, artifact, and audit workflows through specialized workers.
6. Re-run the planning loop after every worker result until the project is materially closer to the desired state.

## Operating Rules

- Prefer orchestration first, but you may use bash and skill files directly when needed.
- Keep one active worker run at a time.
- Use the role's default runner first; only override when necessary and record the reason in the task/session files.
- If a worker run requires approval, create or request the approval instead of bypassing it.
- Store plans, task board state, approvals, blockers, and durable session summaries in the repo.
- Use the runtime DB only as a live control plane for active projects, running agents, and secrets.
- Be concise, concrete, and action-oriented.

## Integrity Rules

- Treat the repo as the durable source of truth.
- Record plans, assumptions, decisions, blockers, and dataset status in Markdown files committed in Git.
- Do not treat placeholder ontology sources as ready data.
- Do not allow analysis tasks to pass if required datasets are missing, estimated without disclosure, or lack provenance.
- Distinguish observed, derived, estimated, synthetic, and missing data explicitly.
- Require the project to document both current state and remaining gaps before claiming progress.
- Prefer ontology-backed datasets and transforms over ad hoc scripts or undocumented spreadsheets.

## Control Loop

On each turn:

1. Read the scope, current plan, task board, blockers, assumptions, and relevant ontology/source files.
2. Compare the current state to the desired state.
3. Write down missing requirements, integrity gaps, and next actions in repo-backed files.
4. Create or update the smallest high-leverage task for the right specialized role.
5. Launch or advance exactly one worker when appropriate.
6. After the worker finishes, inspect outputs, verification, and repo state.
7. Update the plan and repeat until the gaps are closed or a blocker is explicitly recorded.

## Available Role Configs

{{role_lines}}

## Available Project Skills

{{skill_lines}}
"""
        if role == "research":
            return """# Research Prompt

You are the research worker for this RAIL project.

Use the project skill files in `skills/` as your operating playbook. For research tasks:

1. Read the relevant skill files before searching or writing.
2. Prefer primary sources, official datasets, peer-reviewed work, and regulator/agency documents.
3. Record exact source URLs, access dates when useful, and retrieval limits.
4. Separate facts, estimates, interpretation, and open questions.
5. Save durable findings under `topics/` or requested artifacts under `artifacts/`.

Do not treat web snippets as evidence. Open and inspect the source.
"""
        if role == "health":
            return """# Health Agent Prompt

You are the research integrity and repo health auditor for this RAIL project.

Your mission is to ensure that all research outputs are auditable, verified, and grounded in evidence.

## Responsibilities

1.  **Integrity Auditing**: Run semantic verification between generated reports (`artifacts/`) and the evidence ledger (`research_plan/state/`).
2.  **Repo Hygiene**: Cleanup temporary debris, broken symlinks, or redundant test artifacts.
3.  **Dependency Tracking**: Ensure `artifact_lineage.json` is accurate and up-to-date.
4.  **Verification Runs**: Execute `scripts/run-verification.sh` and record the results in `research_plan/state/verification_runs.json`.
5.  **Semantic Cross-Referencing**: Use the `semantic-auditing` skill to verify that claims in artifacts are supported by the recorded sources and claims.

Do not mark an artifact as verified if there is a semantic gap between the claim and the source evidence.
"""
        return f"# {role.title()} Prompt\n\nProject-specific system guidance for the {role} role. Use relevant project skills from `skills/` before doing specialized work.\n"
    def checklist_template(role: str) -> str:
        if role == "planner":
            return (
                "# Planner Checklist\n\n"
                "- follow repo contract\n"
                "- stay inside allowed paths\n"
                "- compare desired state vs current state before acting\n"
                "- read the latest project audit and current blocker before advancing work\n"
                "- keep plans, assumptions, decisions, and blockers in markdown under research_plan\n"
                "- use role checklists as the approval contract before creating or launching worker tasks\n"
                "- require ontology-backed source configs for required datasets\n"
                "- flag placeholder, estimated, synthetic, or missing data explicitly\n"
                "- do not advance a task until verification, publish status, and audited repo state agree\n"
                "- launch the smallest next worker task and then re-plan from updated repo state\n"
                "- satisfy deterministic completion checks\n"
            )
        if role == "research":
            return (
                "# Research Checklist\n\n"
                "- follow repo contract\n"
                "- stay inside allowed paths\n"
                "- use primary or clearly admissible sources and record exact URLs or paths\n"
                "- separate facts, interpretations, and open questions explicitly in markdown outputs\n"
                "- do not cite snippets or summaries without inspecting the underlying source\n"
                "- write claim candidates only when the supporting evidence is recorded in repo state\n"
                "- satisfy deterministic completion checks\n"
            )
        if role == "data":
            return (
                "# Data Checklist\n\n"
                "- follow repo contract\n"
                "- stay inside allowed paths\n"
                "- prefer repo-backed source configs, transforms, and pipelines over ad hoc local scripts\n"
                "- record provenance and freshness for every dataset output before handoff\n"
                "- mark synthetic, estimated, missing, or blocked data explicitly\n"
                "- rerun hydration or verification when source or transform changes affect outputs\n"
                "- satisfy deterministic completion checks\n"
            )
        if role == "coding":
            return (
                "# Coding Checklist\n\n"
                "- follow repo contract\n"
                "- stay inside allowed paths\n"
                "- declare analysis inputs, scripts, and verification commands for produced artifacts\n"
                "- avoid unstated assumptions or hidden data munging in notebooks or scripts\n"
                "- save outputs in repo-backed paths with reproducible commands when possible\n"
                "- satisfy deterministic completion checks\n"
            )
        if role == "artifact":
            return (
                "# Artifact Checklist\n\n"
                "- follow repo contract\n"
                "- stay inside allowed paths\n"
                "- keep evidence links, assumptions, and caveats attached to reports and dashboards\n"
                "- do not elevate unsupported claims into polished narrative form\n"
                "- prefer tables, figures, and captions that can be traced to repo-backed evidence\n"
                "- satisfy deterministic completion checks\n"
            )
        if role == "health":
            return (
                "# Health Checklist\n\n"
                "- follow repo contract\n"
                "- stay inside allowed paths\n"
                "- verify repo hygiene, integrity ledger state, and workflow-contract compliance\n"
                "- distinguish stale sessions, stale artifacts, and real data-quality blockers explicitly\n"
                "- write actionable remediation steps, not just failure summaries\n"
                "- satisfy deterministic completion checks\n"
            )
        return f"# {role.title()} Checklist\n\n- follow repo contract\n- stay inside allowed paths\n- satisfy deterministic completion checks\n"

    research_plan_files = {
        "current_plan.md": current_plan,
        "task_board.md": task_board,
        "assumptions.md": "# Assumptions\n\n",
        "target_state.md": "# Target State\n\nDescribe the desired end state for the project, including required datasets, analysis outputs, integrity gates, and final deliverables.\n",
        "source_registry.md": "# Source Registry\n\nTrack required sources, ontology config paths, status, provenance, and gaps.\n",
        "data_gaps.md": "# Data Gaps\n\nRecord missing datasets, unresolved provenance issues, incomplete controls, and blockers that prevent trusted analysis.\n",
        "decisions.md": "# Decisions\n\n",
        "methodology.md": "# Methodology\n\n",
        "provenance.md": "# Provenance\n\n",
        "claim_evidence.md": "# Claim Evidence\n\n",
        "open_questions.md": "# Open Questions\n\n",
        "rerun_options.md": "# Rerun Options\n\n",
        "verification_summary.md": "# Verification Summary\n\n",
    }
    research_plan_state_files = {
        "assumptions.json": "[]\n",
        "sources.json": "[]\n",
        "claims.json": "[]\n",
        "source_candidates.json": "[]\n",
        "claim_candidates.json": "[]\n",
        "entity_candidates.json": "[]\n",
        "conflicts.json": "[]\n",
        "artifact_lineage.json": "[]\n",
        "verification_runs.json": "[]\n",
    }

    _write(project_root / "rail.yaml", rail_yaml)
    _write(project_root / ".ontology/ontology.yaml", ontology_yaml)
    for filename, content in research_plan_files.items():
        _write(project_root / "research_plan" / filename, content)
    for filename, content in research_plan_state_files.items():
        _write(project_root / "research_plan" / "state" / filename, content)
    _write(
        project_root / "scripts" / "setup-workspace.sh",
        textwrap.dedent(
            f"""\
            #!/usr/bin/env bash
            set -euo pipefail

            # 1. Install the RAIL engine. 
            # We prefer local installation if we're in the monorepo, 
            # otherwise we fall back to the remote GitHub package.
            LOCAL_ENGINE="$RAIL_PROJECT_ROOT/../../packages/engine"
            if [ -d "$LOCAL_ENGINE" ]; then
              echo "→ Installing engine from local path: $LOCAL_ENGINE"
              pip install --quiet -e "$LOCAL_ENGINE"
            else
              echo "→ Installing engine from GitHub..."
              pip install --quiet \\
                "git+https://github.com/Rutgers-Economics-Labs/RutgersAgenticIntelligenceLabs.git#subdirectory=packages/engine"
            fi

            LOCAL_RAIL_PY="$RAIL_PROJECT_ROOT/../../packages/rail-py"
            if [ -d "$LOCAL_RAIL_PY" ]; then
              echo "→ Installing rail-py from local path: $LOCAL_RAIL_PY"
              pip install --quiet -e "$LOCAL_RAIL_PY"
            else
              echo "→ Installing rail-py from GitHub..."
              pip install --quiet \\
                "git+https://github.com/Rutgers-Economics-Labs/RutgersAgenticIntelligenceLabs.git#subdirectory=packages/rail-py"
            fi

            # 2. Common data science deps used by analysis scripts
            pip install --quiet pandas requests httpx pyyaml duckdb matplotlib statsmodels scikit-learn

            echo "RAIL engine and CLI installed."
            python -c "import engine; print('engine ok')" 2>/dev/null || echo "Note: engine import check skipped"
            rail --help >/dev/null 2>&1 || echo "Note: rail CLI check skipped"
            """
        ),
    )
    _write(
        project_root / "scripts" / "run-verification.sh",
        "#!/usr/bin/env bash\nset -euo pipefail\n\n# Run deterministic checks for the current worker workspace.\npython3 scripts/verify_project_state.py\n",
    )
    _write(
        project_root / "scripts" / "verify_project_state.py",
        textwrap.dedent(
            """\
            #!/usr/bin/env python3
            from __future__ import annotations

            import csv
            import sys
            from pathlib import Path

            import yaml


            ROOT = Path(__file__).resolve().parents[1]

            REQUIRED_LEDGERS = [
                "research_plan/current_plan.md",
                "research_plan/task_board.md",
                "research_plan/assumptions.md",
                "research_plan/target_state.md",
                "research_plan/source_registry.md",
                "research_plan/data_gaps.md",
            ]

            PLACEHOLDER_MARKERS = [
                "example.com",
                "review-required",
                "missing_auth_or_manual",
                "draft source for review",
            ]


            def read_text(path: Path) -> str:
                return path.read_text(encoding="utf-8") if path.exists() else ""


            def fail(message: str, failures: list[str]) -> None:
                failures.append(message)


            def require_ledgers(failures: list[str]) -> None:
                for rel in REQUIRED_LEDGERS:
                    path = ROOT / rel
                    if not path.exists() or not read_text(path).strip():
                        fail(f"Missing or empty required ledger: {rel}", failures)


            def check_sources(failures: list[str]) -> None:
                for path in sorted((ROOT / ".ontology" / "sources").glob("*.yaml")):
                    raw = read_text(path)
                    lowered = raw.lower()
                    for marker in PLACEHOLDER_MARKERS:
                        if marker in lowered:
                            fail(f"Placeholder or review-only ontology source: {path.relative_to(ROOT)} ({marker})", failures)
                            break
                    try:
                        data = yaml.safe_load(raw) or {}
                    except Exception as exc:
                        fail(f"Invalid source YAML: {path.relative_to(ROOT)} ({exc})", failures)
                        continue
                    if not isinstance(data, dict):
                        fail(f"Source config root must be a mapping: {path.relative_to(ROOT)}", failures)
                        continue
                    if not (data.get("url") or data.get("path")):
                        fail(f"Source config missing url/path: {path.relative_to(ROOT)}", failures)
                    fields = data.get("fields")
                    if not isinstance(fields, list) or not fields:
                        fail(f"Source config missing field mappings: {path.relative_to(ROOT)}", failures)


            def required_outcomes() -> list[str]:
                brief = read_text(ROOT / "topics" / "brief.md").lower()
                spec = read_text(ROOT / "specs" / "research_question.yaml").lower()
                text = brief + "\\n" + spec
                outcomes: list[str] = []
                if "employment" in text:
                    outcomes.append("employment")
                if "unemployment" in text:
                    outcomes.append("unemployment")
                if "income" in text:
                    outcomes.append("income")
                return outcomes


            def load_panel_rows() -> tuple[list[str], list[dict[str, str]]]:
                panel = ROOT / "topics" / "data" / "processed" / "longitudinal_panel.csv"
                if not panel.exists():
                    return [], []
                with panel.open("r", encoding="utf-8", newline="") as handle:
                    reader = csv.DictReader(handle)
                    rows = list(reader)
                    return list(reader.fieldnames or []), rows


            def check_panel(failures: list[str]) -> None:
                columns, rows = load_panel_rows()
                if not columns or not rows:
                    fail("Missing processed longitudinal panel dataset: topics/data/processed/longitudinal_panel.csv", failures)
                    return

                lower_cols = [c.lower() for c in columns]

                if "treated" in lower_cols:
                    treated_col = columns[lower_cols.index("treated")]
                    treated_values = {str(row.get(treated_col, "")).strip() for row in rows if str(row.get(treated_col, "")).strip()}
                    if treated_values == {"1"}:
                        fail("Panel contains treated=1 for all rows; a real control group is still missing.", failures)

                outcomes = required_outcomes()
                for outcome in outcomes:
                    if outcome == "employment":
                        present = any("employment" in c or "employed" in c for c in lower_cols)
                    elif outcome == "unemployment":
                        present = any("unemp" in c for c in lower_cols)
                    else:
                        present = any("income" in c for c in lower_cols)
                    if not present:
                        fail(f"Required outcome missing from processed panel: {outcome}", failures)

                source_cols = [c for c in columns if "source" in c.lower() or "provenance" in c.lower()]
                for source_col in source_cols:
                    seen = {str(row.get(source_col, "")).strip().lower() for row in rows}
                    if any("synthetic" in value for value in seen if value):
                        fail(f"Synthetic data detected in panel column {source_col} while integrity.allow_synthetic_data is false.", failures)


            def main() -> int:
                failures: list[str] = []
                require_ledgers(failures)
                check_sources(failures)
                check_panel(failures)

                if failures:
                    print("VERIFICATION FAILED")
                    for item in failures:
                        print(f"- {item}")
                    return 1

                print("VERIFICATION PASSED")
                return 0


            if __name__ == "__main__":
                raise SystemExit(main())
            """
        ),
    )
    _write(
        project_root / "scripts" / "archive-workspace.sh",
        "#!/usr/bin/env bash\nset -euo pipefail\n\n# Archive or clean temporary worker workspace resources.\n",
    )
    _write(project_root / "README.md", f"# {name}\n")

    roles = {
        "planner": {
            "purpose": "Gather requirements, write plans, create tasks, and coordinate workers.",
            "read": [".ontology", "topics", "specs", "research_plan", "skills", "agents"],
            "write": ["specs", "research_plan", "agents"],
            "secrets": [],
            "tools": ["read_repo", "write_repo", "create_task", "request_approval"],
        },
        "research": {
            "purpose": "Gather external information and organize project knowledge.",
            "read": [".ontology", "topics", "specs", "research_plan", "skills"],
            "write": ["topics", "artifacts"],
            "secrets": [],
            "tools": ["read_repo", "write_repo", "web_research", "grepai_search"],
        },
        "data": {
            "purpose": "Author and validate ontology-backed ingestion configs.",
            "read": [".ontology", "topics", "specs", "research_plan", "skills"],
            "write": [".ontology/sources", ".ontology/pipelines", ".ontology/transforms", "topics"],
            "secrets": ["FRED_API_KEY"],
            "tools": ["read_repo", "write_repo", "validate_yaml", "run_hydration_dry_run", "grepai_search"],
        },
        "coding": {
            "purpose": "Write scripts that operate on hydrated ontology data and topic context.",
            "read": [".ontology", "topics", "specs", "research_plan", "skills", "artifacts"],
            "write": ["topics", "artifacts"],
            "secrets": [],
            "tools": ["read_repo", "write_repo", "execute_python", "query_ontology", "grepai_search"],
        },
        "artifact": {
            "purpose": "Generate presentation-ready artifacts and dashboards.",
            "read": [".ontology", "topics", "specs", "research_plan", "artifacts"],
            "write": ["artifacts", "topics"],
            "secrets": [],
            "tools": ["read_repo", "write_repo", "render_artifact", "grepai_search"],
        },
        "health": {
            "purpose": "Audit repo hygiene, cleanup generated debris, and verify outputs.",
            "read": [".ontology", "topics", "specs", "research_plan", "skills", "artifacts", "agents"],
            "write": ["research_plan", "skills"],
            "secrets": [],
            "tools": ["read_repo", "write_repo", "verify_paths", "verify_outputs", "grepai_search"],
        },
    }

    for role, cfg in roles.items():
        _write(
            project_root / "agents" / f"{role}.yaml",
            role_template(role, cfg["purpose"], cfg["read"], cfg["write"], cfg["secrets"], cfg["tools"]),
        )
        _write(project_root / "agents" / "prompts" / f"{role}.md", prompt_template(role))
        _write(project_root / "agents" / "checklists" / f"{role}.md", checklist_template(role))

    starter_skills = {
        "repo-contract.md": "# Repo Contract\n\n- keep top-level structure stable\n- keep generated work inside allowed paths\n",
        "rail-platform.md": textwrap.dedent(
            """\
            # RAIL Platform

            Use this skill whenever the project requires data queries, analysis, hydration, or integrity checks.

            This project is backed by the RAIL platform. Prefer RAIL MCP tools over manual scripting when working with project data.

            ## Adding the MCP server

            ### Option 1 — Local install (stdio)

            Install once:

            ```bash
            pip install -e packages/mcp-server   # from monorepo
            # or: pip install rail-mcp           # from PyPI when published
            ```

            Add to the project `.mcp.json` (or `~/.claude/claude_desktop_config.json` for Claude Desktop):

            ```json
            {
              "mcpServers": {
                "rail": {
                  "command": "rail-mcp",
                  "env": {
                    "RAIL_PROJECT": "your-project-slug",
                    "RAIL_API_URL": "http://localhost:8000/api/v1"
                  }
                }
              }
            }
            ```

            For a local repo checkout instead of a running API:

            ```json
            {
              "mcpServers": {
                "rail": {
                  "command": "rail-mcp",
                  "args": ["--local", "--path", "/path/to/project"],
                  "env": {}
                }
              }
            }
            ```

            ### Option 2 — Remote URL (SSE / streamable-http)

            When RAIL is deployed as a hosted service, the MCP server can run in HTTP mode:

            ```bash
            rail-mcp --transport sse --host 0.0.0.0 --port 8001 --project your-slug
            # or for the newer transport:
            rail-mcp --transport streamable-http --port 8001 --project your-slug
            ```

            Agents then connect by URL — no local install needed:

            ```json
            {
              "mcpServers": {
                "rail": {
                  "url": "http://your-rail-host:8001/sse"
                }
              }
            }
            ```

            For streamable-http:

            ```json
            {
              "mcpServers": {
                "rail": {
                  "url": "http://your-rail-host:8001/mcp"
                }
              }
            }
            ```

            ## Available tools

            | Tool | When to use |
            |---|---|
            | `list_classes` | First step — discover entity types in the ontology |
            | `get_entities(class_name, limit)` | Browse instances of a class |
            | `search_entities(query)` | Full-text search across all entities |
            | `get_series(series_id)` | Fetch a named time-series |
            | `query_sql(sql)` | DuckDB SQL against the artifact database |
            | `execute_python(code)` | Run analysis; sandbox has pandas, statsmodels, duckdb |
            | `run_analysis(plugin_slug)` | Run a registered analysis plugin |
            | `search_registry(query)` | Find available datasets in the data catalog |
            | `discover_templates(query)` | Find connector templates to add new data sources |
            | `hydrate(pipeline_slug)` | Refresh project data from upstream sources |
            | `integrity_status` | Full integrity report before publishing |
            | `integrity_assumptions` | Check recorded assumptions |
            | `integrity_sources` | List evidence sources |
            | `integrity_claims` | List empirical claims and their evidence |
            | `integrity_rerun_plan` | See what needs re-running after an assumption changes |
            | `list_secrets` | Check which API keys are configured |
            | `set_secret(key, value)` | Store a new API key |

            ## Typical workflow

            ```
            1. list_classes                    → discover what data exists
            2. get_entities("ClassName")       → inspect a sample
            3. query_sql("SELECT ...")         → explore or aggregate
            4. integrity_status()              → verify data quality before analysis
            5. execute_python("import ...")    → run analysis in the sandbox
            6. search_registry("...")          → find additional datasets if needed
            7. hydrate()                       → refresh data when sources update
            ```
            """
        ),
        "verification.md": textwrap.dedent(
            """\
            # Verification

            Use this skill when validating project outputs.

            ## Deterministic Verification
            Run `scripts/run-verification.sh` to perform structural and data integrity checks. This includes row count validations, schema checks, file existence checks, placeholder-source detection, required-ledger checks, and analysis-readiness checks.

            ## Semantic Verification
            Perform a manual (agentic) review of the content. Cross-check the "Claim Evidence" (`research_plan/claim_evidence.md`) against the final report. Ensure that no claim is made without a corresponding evidence record.

            ## State Transitions
            - If verification passes: update `artifact_lineage.json` status to `verified` or `partially_verified`.
            - If verification fails: mark as `blocked` and record the specific failure reason in `verification_runs.json`.

            ## Required Ledgers
            Keep these repo-backed files current:
            - `research_plan/assumptions.md`
            - `research_plan/target_state.md`
            - `research_plan/source_registry.md`
            - `research_plan/data_gaps.md`
            """
        ),
        "semantic-auditing.md": textwrap.dedent(
            """\
            # Semantic Auditing

            Use this skill to verify that generated reports and artifacts accurately reflect the evidence in the integrity ledger.

            ## Workflow

            1.  **Extract Claims**: Identify the primary empirical claims in the artifact.
            2.  **Cross-Reference**: For each claim, find the corresponding `ClaimRecord` in `research_plan/state/claims.json`.
            3.  **Trace Evidence**: Verify that the `evidence_paths` and `source_keys` for that claim actually support the statement made in the artifact.
            4.  **Check for Hallucinations**: Ensure no numbers or specific findings in the report are missing from the underlying sources.
            5.  **Audit Citations**: Confirm that every citation in the report exists in `research_plan/state/sources.json`.

            ## Output

            Record a `VerificationRunRecord` in `research_plan/state/verification_runs.json` with a check of type `semantic_audit`.
            """
        ),
        "citations.md": "# Citations\n\n- cite sources for research outputs when applicable\n- prefer source title, publisher, URL, and access date for web sources\n- distinguish primary sources from secondary summaries\n- never cite a source that was not opened or otherwise inspected\n",
        "web-research.md": textwrap.dedent(
            """\
            # Web Research

            Use this skill when a task requires finding current or external information.

            ## Workflow

            1. Turn the question into 3-7 targeted search queries.
            2. Search for primary sources first: official agencies, datasets, filings, standards, papers, and original reports.
            3. Open candidate sources and inspect their content before using them.
            4. Capture the citation, relevant facts, date range, geography, and caveats.
            5. Cross-check high-impact claims with at least two independent sources when possible.
            6. Save notes in `topics/` with a source table and a short synthesis.

            ## Source Quality

            Prefer official public records, data portals, peer-reviewed papers, regulator filings, and market/operator reports. Use news and blogs mainly to discover leads, not as final evidence.

            ## Output

            Include:

            - answer or finding
            - evidence table
            - confidence level
            - gaps and next searches
            """
        ),
        "source-inventory.md": textwrap.dedent(
            """\
            # Source Inventory

            Use this skill when building a data inventory for a research project.

            For each source, record:

            - name and publisher
            - URL or access path
            - data format and access method
            - geography and time coverage
            - update frequency
            - key fields
            - licensing or access constraints
            - expected joins to project entities
            - known quality issues

            Mark each source as `candidate`, `validated`, `blocked`, or `rejected`.
            """
        ),
        "literature-review.md": textwrap.dedent(
            """\
            # Literature Review

            Use this skill for academic, policy, and technical literature reviews.

            ## Search

            Search across scholar indexes, agency reports, working papers, regulator documents, and domain-specific institutions.

            ## Extraction

            For each important work, capture:

            - research question
            - data and sample period
            - identification strategy
            - main findings
            - limitations
            - relevance to this project

            ## Synthesis

            Group findings by claim or mechanism. Highlight agreement, disagreement, and missing evidence.
            """
        ),
        "policy-analysis.md": textwrap.dedent(
            """\
            # Policy Analysis

            Use this skill when research outputs need regulatory or public-sector recommendations.

            Separate:

            - empirical finding
            - affected stakeholders
            - statutory or regulatory context
            - policy options
            - implementation constraints
            - distributional impacts
            - risks and unintended consequences

            Recommendations should follow from evidence and include uncertainty.
            """
        ),
        "econometric-design.md": textwrap.dedent(
            """\
            # Econometric Design

            Use this skill when a task requires causal inference, forecasting evaluation, or model comparison.

            Before modeling, define:

            - unit of observation
            - treatment and control groups
            - treatment timing
            - outcome variables
            - identifying assumption
            - confounders and controls
            - fixed effects
            - robustness checks
            - falsification or placebo tests

            Do not make causal claims from descriptive comparisons alone.
            """
        ),
        "data-provenance.md": textwrap.dedent(
            """\
            # Data Provenance

            Use this skill whenever data is downloaded, transformed, or analyzed.

            Record:

            - source URL or API endpoint
            - retrieval date
            - query parameters
            - raw file path or cache key
            - transformation script
            - output file path
            - row counts and key validation checks

            Keep raw data and derived outputs distinguishable.
            """
        ),
    }
    for filename, content in starter_skills.items():
        _write(project_root / "skills" / filename, content)

    return project_root
