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

        agents:
          roles_dir: "agents"
          default_runner: "jules"
          sequential_execution: true
          approval_required_for_write_runs: true
          planner_thread_mode: "project"
          default_planner_role: "planner"

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
                "default": "jules",
                "approval_required": True,
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

You are the only user-facing agent. Your job is to:

1. Understand the user's goal.
2. Decide whether to answer directly, update project files, create tasks, request approval, or launch a worker.
3. Keep durable project state in the Git repo, especially under `research_plan/`.
4. Use project role configs as the source of truth for runner choice, path policy, and skill access.
5. Preserve deep research, ontology, data, coding, artifact, and audit workflows through specialized workers.

## Operating Rules

- Prefer orchestration first, but you may use bash and skill files directly when needed.
- Keep one active worker run at a time.
- Use the role's default runner first; only override when necessary and record the reason in the task/session files.
- If a worker run requires approval, create or request the approval instead of bypassing it.
- Store plans, task board state, approvals, blockers, and durable session summaries in the repo.
- Use the runtime DB only as a live control plane for active projects, running agents, and secrets.
- Be concise, concrete, and action-oriented.

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
        return f"# {role.title()} Prompt\n\nProject-specific system guidance for the {role} role. Use relevant project skills from `skills/` before doing specialized work.\n"
    checklist_template = lambda role: f"# {role.title()} Checklist\n\n- follow repo contract\n- stay inside allowed paths\n- satisfy deterministic completion checks\n"

    _write(project_root / "rail.yaml", rail_yaml)
    _write(project_root / ".ontology/ontology.yaml", ontology_yaml)
    _write(project_root / "research_plan/current_plan.md", current_plan)
    _write(project_root / "research_plan/task_board.md", task_board)
    _write(
        project_root / "scripts" / "setup-workspace.sh",
        "#!/usr/bin/env bash\nset -euo pipefail\n\n"
        "# Install the RAIL engine so any cloud agent (Jules, etc.) has access to the\n"
        "# full ontology/pipeline/analysis stack.\n"
        'pip install --quiet \\\n'
        '  "git+https://github.com/Rutgers-Economics-Labs/RutgersAgenticIntelligenceLabs.git#subdirectory=packages/engine"\n\n'
        "# Common data science deps used by analysis scripts\n"
        "pip install --quiet pandas requests httpx pyyaml duckdb matplotlib statsmodels scikit-learn\n\n"
        "echo \"RAIL engine installed.\"\n"
        'python -c "import engine; print(\'engine ok\')" 2>/dev/null || echo "Note: engine import check skipped"\n',
    )
    _write(
        project_root / "scripts" / "run-verification.sh",
        "#!/usr/bin/env bash\nset -euo pipefail\n\n# Run deterministic checks for the current worker workspace.\n",
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
        "verification.md": "# Verification\n\n- prefer deterministic checks\n- do not mark tasks done without validation\n- state what was verified and what remains uncertain\n",
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
