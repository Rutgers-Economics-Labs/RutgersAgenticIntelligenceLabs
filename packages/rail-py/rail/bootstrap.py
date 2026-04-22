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
        "topics",
        "specs",
        "research_plan/graph",
        "research_plan/tasks",
        "agents/prompts",
        "agents/checklists",
        "skills",
        "artifacts",
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
                "allow_use": role == "planner",
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

    prompt_template = lambda role: f"# {role.title()} Prompt\n\nProject-specific system guidance for the {role} role.\n"
    checklist_template = lambda role: f"# {role.title()} Checklist\n\n- follow repo contract\n- stay inside allowed paths\n- satisfy deterministic completion checks\n"

    _write(project_root / "rail.yaml", rail_yaml)
    _write(project_root / ".ontology/ontology.yaml", ontology_yaml)
    _write(project_root / "research_plan/current_plan.md", current_plan)
    _write(project_root / "research_plan/task_board.md", task_board)
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
        "verification.md": "# Verification\n\n- prefer deterministic checks\n- do not mark tasks done without validation\n",
        "citations.md": "# Citations\n\n- include sources for research outputs when applicable\n",
    }
    for filename, content in starter_skills.items():
        _write(project_root / "skills" / filename, content)

    return project_root
