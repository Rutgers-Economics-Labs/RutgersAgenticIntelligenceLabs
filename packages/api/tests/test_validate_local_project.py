from __future__ import annotations

import importlib.util
from pathlib import Path

from rail.integrity import ResearchIntegrityRepo


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "validate_local_project.py"
SPEC = importlib.util.spec_from_file_location("validate_local_project", SCRIPT_PATH)
assert SPEC and SPEC.loader
validate_local_project = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validate_local_project)


def test_local_validation_repairs_verifier_source_aliases_and_claim_links(tmp_path: Path) -> None:
    scripts = tmp_path / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "verify_project_state.py").write_text(
        """
REQUIRED_SOURCE_KEYS = {
    "uez-economic-indicator-workbook",
    "consolidated-longitudinal-panel",
    "sut-zone-collections",
}
REQUIRED_CLAIM_KEYS = {
    "claim-sut-post-reform-positive",
}
""",
        encoding="utf-8",
    )

    repo = ResearchIntegrityRepo(tmp_path)
    repo.ensure_files_exist()
    repo.upsert_source(
        {
            "source_key": "project-slug-uez-economic-indicator-database",
            "source_type": "dataset",
            "title": "UEZ Economic Indicator Database",
            "url_or_path": "https://example.test/uez.xlsb",
        }
    )
    repo.upsert_source(
        {
            "source_key": "project-slug-consolidated-panel",
            "source_type": "dataset",
            "title": "Consolidated panel",
            "url_or_path": "topics/data/processed/longitudinal_panel.csv",
        }
    )
    repo.upsert_source(
        {
            "source_key": "project-slug-sut-collections-by-zone",
            "source_type": "dataset",
            "title": "SUT collections by zone",
            "url_or_path": "https://example.test/sut.csv",
        }
    )
    repo.upsert_claim(
        {
            "claim_key": "claim-sut-post-reform-positive",
            "claim_text": "Post-reform SUT collections increased in the observed window.",
            "evidence_paths": [],
            "source_keys": [],
            "caveats": ["Observed window only."],
        }
    )

    validate_local_project._repair_local_project_state_before_verification(tmp_path)

    sources = {source.source_key: source for source in repo.load_sources()}
    assert "uez-economic-indicator-workbook" in sources
    assert sources["uez-economic-indicator-workbook"].provenance["alias_of"] == "project-slug-uez-economic-indicator-database"
    assert "consolidated-longitudinal-panel" in sources
    assert "sut-zone-collections" in sources

    [claim] = repo.load_claims()
    assert claim.source_keys == [
        "sut-zone-collections",
        "uez-economic-indicator-workbook",
        "consolidated-longitudinal-panel",
    ]
