#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parents[1]
RAIL_PY_ROOT = REPO_ROOT / "packages" / "rail-py"
if str(RAIL_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(RAIL_PY_ROOT))

from rail.integrity import ResearchIntegrityRepo  # noqa: E402


REQUIRED_ARTIFACTS = {
    "artifacts/federal_research_grants_report.md",
    "artifacts/funding_dashboard.csv",
    "artifacts/departmental_performance_profiles.md",
    "artifacts/source_quality_notes.md",
    "topics/data/processed/federal_awards_rutgers_fy2021_fy2025.csv",
}
REQUIRED_SOURCES = {
    "usaspending-rutgers-federal-assistance",
    "nsf-award-search-rutgers",
    "rutgers-office-research-financial-reports",
}
REQUIRED_CLAIMS = {
    "claim-public-awards-panel-built",
    "claim-largest-observed-agency",
    "claim-department-crosswalk-required",
}
PLACEHOLDER_MARKERS = {
    "example.com/review-required",
    "draft source for review",
    "missing_auth_or_manual",
    "placeholder",
}


def fail(message: str, failures: list[str]) -> None:
    failures.append(message)


def read_json(rel: str) -> list[dict]:
    path = ROOT / rel
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else []


def check_artifacts(failures: list[str]) -> None:
    for rel in sorted(REQUIRED_ARTIFACTS):
        path = ROOT / rel
        if not path.exists() or path.stat().st_size == 0:
            fail(f"Missing or empty artifact: {rel}", failures)
            continue
        text = path.read_text(encoding="utf-8", errors="ignore").lower()
        if rel.endswith(".md"):
            for marker in PLACEHOLDER_MARKERS:
                if marker in text:
                    fail(f"Placeholder marker in artifact {rel}: {marker}", failures)

    panel = ROOT / "topics/data/processed/federal_awards_rutgers_fy2021_fy2025.csv"
    if panel.exists():
        with panel.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        if len(rows) < 10:
            fail("Processed federal awards panel should contain at least 10 rows.", failures)
        agencies = {row.get("agency", "").strip() for row in rows if row.get("agency", "").strip()}
        if len(agencies) < 2:
            fail("Processed federal awards panel should include at least two agency groupings.", failures)

    dashboard = ROOT / "artifacts/funding_dashboard.csv"
    if dashboard.exists():
        with dashboard.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        if not rows:
            fail("Funding dashboard contains no rows.", failures)
        if not any(float(row.get("total_amount") or 0) > 0 for row in rows):
            fail("Funding dashboard has no positive funding totals.", failures)


def check_truth_state(failures: list[str]) -> None:
    repo = ResearchIntegrityRepo(ROOT)
    repo.ensure_files_exist()
    repo.rebuild_integrity_edges()

    sources = {item.get("source_key"): item for item in read_json("research_plan/state/sources.json")}
    missing_sources = sorted(REQUIRED_SOURCES - set(sources))
    if missing_sources:
        fail(f"Missing source records: {', '.join(missing_sources)}", failures)
    for key in REQUIRED_SOURCES.intersection(sources):
        source = sources[key]
        if not source.get("url_or_path"):
            fail(f"Source {key} missing url_or_path", failures)
        if source.get("quality_status") in {"blocked", "rejected"}:
            fail(f"Source {key} is not usable: {source.get('quality_status')}", failures)

    claims = {item.get("claim_key"): item for item in read_json("research_plan/state/claims.json")}
    missing_claims = sorted(REQUIRED_CLAIMS - set(claims))
    if missing_claims:
        fail(f"Missing claim records: {', '.join(missing_claims)}", failures)
    for key in REQUIRED_CLAIMS.intersection(claims):
        claim = claims[key]
        if not claim.get("source_keys"):
            fail(f"Claim {key} missing source_keys", failures)
        if not claim.get("evidence_paths"):
            fail(f"Claim {key} missing evidence_paths", failures)
        if not claim.get("caveats"):
            fail(f"Claim {key} missing caveats", failures)

    lineage = {item.get("artifact_path"): item for item in read_json("research_plan/state/artifact_lineage.json")}
    missing_lineage = sorted(REQUIRED_ARTIFACTS - set(lineage))
    if missing_lineage:
        fail(f"Missing artifact lineage: {', '.join(missing_lineage)}", failures)
    for rel in REQUIRED_ARTIFACTS.intersection(lineage):
        record = lineage[rel]
        if record.get("promotion_state") not in {"partially_verified", "verified"}:
            fail(f"Artifact {rel} is not promoted enough for closeout: {record.get('promotion_state')}", failures)
        if not record.get("verification_runs"):
            fail(f"Artifact {rel} missing verification_runs", failures)
        if not record.get("scripts"):
            fail(f"Artifact {rel} missing script lineage", failures)

    runs = {item.get("run_id"): item for item in read_json("research_plan/state/verification_runs.json")}
    run = runs.get("federal-grants-local-build-001")
    if not run or run.get("status") != "passed":
        fail("Missing passed verification run federal-grants-local-build-001", failures)


def main() -> int:
    failures: list[str] = []
    check_artifacts(failures)
    check_truth_state(failures)
    if failures:
        print("VERIFICATION FAILED")
        for message in failures:
            print(f"- {message}")
        return 1
    print("VERIFICATION PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
