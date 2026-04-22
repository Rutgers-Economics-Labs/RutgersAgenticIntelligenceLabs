import textwrap

from app.services.repo_contract_service import (
    build_config_files,
    dedupe_changed_paths,
    manifest_updates_from_content,
    render_rail_manifest,
)


def test_build_config_files_emits_current_and_legacy_paths():
    files = build_config_files("apis", "fred_unemployment", "name: fred_unemployment\n")
    assert [f.path for f in files] == [
        ".ontology/sources/fred_unemployment.yaml",
        "configs/apis/fred_unemployment.yaml",
    ]


def test_manifest_updates_reads_linked_sources_and_pipeline():
    content = textwrap.dedent(
        """\
        version: 1
        project:
          name: "NJ Data"
          slug: "nj-data"
          default_branch: "main"
          description: "Economics"
        hydration:
          ontology_file: ".ontology/ontologies/nj-core.yaml"
          sources_dir: ".ontology/sources"
          pipelines_dir: ".ontology/pipelines"
          default_pipeline: "nj-hydration"
          linked_sources:
            - census_states
            - fred_unemployment
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
        """
    )
    updates = manifest_updates_from_content(content)
    assert updates["name"] == "NJ Data"
    assert updates["pipelineConfigSlug"] == "nj-hydration"
    assert updates["ontologyConfigSlug"] == "nj-core"
    assert updates["apiConfigSlugs"] == ["census_states", "fred_unemployment"]


def test_dedupe_changed_paths_prefers_current_layout():
    watched = dedupe_changed_paths([
        "configs/apis/fred.yaml",
        ".ontology/sources/fred.yaml",
        "configs/pipelines/nj.yaml",
        ".ontology/pipelines/nj.yaml",
        "rail.yaml",
    ])
    assert ".ontology/sources/fred.yaml" in watched
    assert ".ontology/pipelines/nj.yaml" in watched
    assert "configs/apis/fred.yaml" not in watched
    assert "configs/pipelines/nj.yaml" not in watched
    assert "rail.yaml" in watched


def test_render_manifest_preserves_existing_sections():
    project = {
        "name": "NJ Data",
        "slug": "nj-data",
        "description": "Economics",
        "defaultBranch": "main",
        "ontologyConfigSlug": "nj-core",
        "pipelineConfigSlug": "nj-hydration",
        "apiConfigSlugs": ["census_states"],
    }
    existing = textwrap.dedent(
        """\
        version: 1
        project:
          name: "Old"
          slug: "old"
          default_branch: "future"
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
          hydration_mode: "incremental"
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
          show_repo_tree: false
          show_task_board_snapshot: true
          default_home_view: "project_home"
        """
    )
    rendered = render_rail_manifest(project, existing)
    assert 'name: NJ Data' in rendered
    assert 'default_pipeline: nj-hydration' in rendered
    assert 'linked_sources:' in rendered
    assert 'show_repo_tree: false' in rendered
