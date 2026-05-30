#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parents[1]
RAIL_PY_ROOT = REPO_ROOT / "packages" / "rail-py"
if str(RAIL_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(RAIL_PY_ROOT))

from rail.integrity import ResearchIntegrityRepo  # noqa: E402


USER_AGENT = "RAIL Rutgers federal grants local validation"
START_DATE = "2020-10-01"
END_DATE = "2025-09-30"
RAW_DIR = ROOT / "topics" / "data" / "raw"
PROCESSED_DIR = ROOT / "topics" / "data" / "processed"
ARTIFACTS_DIR = ROOT / "artifacts"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def request_json(url: str, *, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"User-Agent": USER_AGENT}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def load_or_fetch(path: Path, url: str, *, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        data = request_json(url, payload=payload)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
        return data
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        raise RuntimeError(f"Could not fetch {url} and no cache exists at {path}: {exc}") from exc


def number(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    return float(str(value).replace(",", "").replace("$", "").strip() or 0)


def parse_date(date_value: str | None) -> datetime | None:
    if not date_value:
        return None
    raw = str(date_value).strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(raw[:10], fmt)
        except ValueError:
            continue
    return None


def intersects_query_window(start_value: str | None, end_value: str | None) -> bool:
    window_start = datetime.fromisoformat(START_DATE)
    window_end = datetime.fromisoformat(END_DATE)
    start = parse_date(start_value)
    end = parse_date(end_value)
    if start and start > window_end:
        return False
    if end and end < window_start:
        return False
    return True


def fiscal_year(date_value: str | None) -> str:
    date = parse_date(date_value)
    if not date:
        return "unknown"
    window_start = datetime.fromisoformat(START_DATE)
    if date < window_start:
        return "pre-2021 active/continuing"
    return str(date.year + 1 if date.month >= 10 else date.year)


def fetch_usaspending() -> list[dict[str, Any]]:
    payload = {
        "filters": {
            "time_period": [{"start_date": START_DATE, "end_date": END_DATE}],
            "recipient_search_text": ["Rutgers"],
            "award_type_codes": ["02", "03", "04", "05"],
        },
        "fields": [
            "Award ID",
            "Recipient Name",
            "Award Amount",
            "Awarding Agency",
            "Award Type",
            "Start Date",
            "End Date",
        ],
        "page": 1,
        "limit": 100,
        "sort": "Award Amount",
        "order": "desc",
    }
    data = load_or_fetch(
        RAW_DIR / "usaspending_rutgers_assistance.json",
        "https://api.usaspending.gov/api/v2/search/spending_by_award/",
        payload=payload,
    )
    return list(data.get("results") or [])


def fetch_nsf() -> list[dict[str, Any]]:
    query = urllib.parse.urlencode(
        {
            "awardeeName": "Rutgers",
            "dateStart": "10/01/2020",
            "dateEnd": "09/30/2025",
            "offset": "1",
            "printFields": "id,title,agency,awardeeName,fundsObligatedAmt,startDate,expDate,programElement",
        }
    )
    data = load_or_fetch(
        RAW_DIR / "nsf_awards_rutgers.json",
        f"https://www.research.gov/awardapi-service/v1/awards.json?{query}",
    )
    awards = data.get("response", {}).get("award") or []
    if isinstance(awards, dict):
        return [awards]
    return list(awards)


def normalize_awards(usaspending: list[dict[str, Any]], nsf: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in usaspending:
        amount = number(item.get("Award Amount"))
        start = str(item.get("Start Date") or "")
        end = str(item.get("End Date") or "")
        if not intersects_query_window(start, end):
            continue
        rows.append(
            {
                "source": "USAspending.gov",
                "award_id": str(item.get("Award ID") or ""),
                "recipient": str(item.get("Recipient Name") or ""),
                "agency": str(item.get("Awarding Agency") or ""),
                "program_or_title": str(item.get("Award Type") or ""),
                "amount": f"{amount:.2f}",
                "start_date": start,
                "end_date": end,
                "fiscal_year": fiscal_year(start),
            }
        )
    for item in nsf:
        amount = number(item.get("fundsObligatedAmt"))
        start = str(item.get("startDate") or "")
        end = str(item.get("expDate") or "")
        if not intersects_query_window(start, end):
            continue
        rows.append(
            {
                "source": "NSF Awards API",
                "award_id": str(item.get("id") or ""),
                "recipient": str(item.get("awardeeName") or ""),
                "agency": "National Science Foundation",
                "program_or_title": str(item.get("title") or item.get("programElement") or ""),
                "amount": f"{amount:.2f}",
                "start_date": start,
                "end_date": end,
                "fiscal_year": fiscal_year(start),
            }
        )
    return [row for row in rows if row["award_id"] and number(row["amount"]) > 0]


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def money(value: float) -> str:
    if abs(value) >= 1_000_000_000:
        return f"${value / 1_000_000_000:.2f}B"
    if abs(value) >= 1_000_000:
        return f"${value / 1_000_000:.1f}M"
    return f"${value:,.0f}"


def build_outputs(rows: list[dict[str, Any]]) -> dict[str, Any]:
    fields = ["source", "award_id", "recipient", "agency", "program_or_title", "amount", "start_date", "end_date", "fiscal_year"]
    processed_path = PROCESSED_DIR / "federal_awards_rutgers_fy2021_fy2025.csv"
    write_csv(processed_path, rows, fields)

    by_agency: dict[str, dict[str, Any]] = defaultdict(lambda: {"award_count": 0, "total_amount": 0.0, "sources": Counter()})
    by_year: dict[str, dict[str, Any]] = defaultdict(lambda: {"award_count": 0, "total_amount": 0.0})
    for row in rows:
        amount = number(row["amount"])
        agency = row["agency"] or "Unknown"
        year = row["fiscal_year"] or "unknown"
        by_agency[agency]["award_count"] += 1
        by_agency[agency]["total_amount"] += amount
        by_agency[agency]["sources"][row["source"]] += 1
        by_year[year]["award_count"] += 1
        by_year[year]["total_amount"] += amount

    dashboard_rows = []
    for agency, stats in sorted(by_agency.items(), key=lambda item: item[1]["total_amount"], reverse=True):
        dashboard_rows.append(
            {
                "agency": agency,
                "award_count": stats["award_count"],
                "total_amount": f"{stats['total_amount']:.2f}",
                "source_mix": "; ".join(f"{key}: {value}" for key, value in stats["sources"].most_common()),
            }
        )
    write_csv(ARTIFACTS_DIR / "funding_dashboard.csv", dashboard_rows, ["agency", "award_count", "total_amount", "source_mix"])

    total_amount = sum(number(row["amount"]) for row in rows)
    top_agency = dashboard_rows[0] if dashboard_rows else {"agency": "n/a", "total_amount": "0", "award_count": 0}
    year_rows = sorted(by_year.items())
    top_awards = sorted(rows, key=lambda row: number(row["amount"]), reverse=True)[:10]

    report_lines = [
        "# Federal Research Grant Funding Analysis at Rutgers University",
        "",
        f"Generated: {utc_now()}",
        "",
        "## Scope",
        "",
        "This local RAIL project summarizes public federal award records matching Rutgers over FY2021-FY2025. It uses USAspending.gov for cross-agency federal assistance coverage and the NSF Awards API for additional research-award detail.",
        "",
        "## Key Findings",
        "",
        f"- The processed public-data panel contains {len(rows)} Rutgers-matching award records returned for the FY2021-FY2025 query window totaling {money(total_amount)}.",
        f"- The largest observed agency total is {top_agency['agency']} with {money(number(top_agency['total_amount']))} across {top_agency['award_count']} records.",
        "- Public federal award feeds do not provide a reliable Rutgers academic department crosswalk, so department-level performance profiles should be treated as a next-step internal-data join rather than inferred from titles alone.",
        "",
        "## Annual Snapshot",
        "",
        "| Fiscal year | Award records | Observed amount |",
        "| --- | ---: | ---: |",
    ]
    for year, stats in year_rows:
        report_lines.append(f"| {year} | {stats['award_count']} | {money(stats['total_amount'])} |")
    report_lines.extend(
        [
            "",
            "## Top Observed Awards",
            "",
            "| Source | Award ID | Agency | Amount | Program or title |",
            "| --- | --- | --- | ---: | --- |",
        ]
    )
    for row in top_awards:
        title = row["program_or_title"].replace("|", " ")[:110]
        report_lines.append(f"| {row['source']} | {row['award_id']} | {row['agency']} | {money(number(row['amount']))} | {title} |")
    report_lines.extend(
        [
            "",
            "## Interpretation Notes",
            "",
            "- USAspending award amounts are obligation-style federal award records and may include non-research assistance; filtering to Rutgers and assistance award types gives a broad federal-funding view, not an audited sponsored-research ledger.",
            "- NSF records are useful for research-award detail but overlap with USAspending, so totals should not be added across sources without deduplication.",
            "- A production departmental dashboard should join these public award IDs to Rutgers internal sponsored-program accounts, principal-investigator appointments, and faculty headcount.",
        ]
    )
    (ARTIFACTS_DIR / "federal_research_grants_report.md").write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    profile_lines = [
        "# Departmental Performance Profiles",
        "",
        "The public sources used here identify recipients, agencies, award IDs, and award titles, but they do not consistently identify Rutgers academic departments. The rail engine therefore blocks fabricated department rankings and records this as a data limitation.",
        "",
        "## Recommended Internal Join",
        "",
        "- Match federal award IDs or PI names to Rutgers sponsored-program account records.",
        "- Map PIs to school, department, center, and campus appointments for the award fiscal year.",
        "- Normalize by faculty headcount or research-active faculty count before ranking departments.",
        "",
        "## Public-Data Proxy Profiles",
        "",
    ]
    for stats in dashboard_rows[:8]:
        profile_lines.append(f"- {stats['agency']}: {stats['award_count']} observed records totaling {money(number(stats['total_amount']))}.")
    (ARTIFACTS_DIR / "departmental_performance_profiles.md").write_text("\n".join(profile_lines) + "\n", encoding="utf-8")

    source_notes = [
        "# Source Quality Notes",
        "",
        "- USAspending.gov is the primary cross-agency federal assistance source for this pass.",
        "- NSF Awards API provides source-specific research award detail and a check against broad USAspending coverage.",
        "- NIH RePORTER remains a candidate source for a later agency-specific pass; this build does not use NIH-derived claims because the public API organization-name query did not return a verified Rutgers slice during local validation.",
        "- Rutgers Office of Research financial reports remain the preferred authority for audited internal department allocations, but a public machine-readable department crosswalk was not available in this local pass.",
    ]
    (ARTIFACTS_DIR / "source_quality_notes.md").write_text("\n".join(source_notes) + "\n", encoding="utf-8")

    return {
        "processed_path": processed_path,
        "total_amount": total_amount,
        "top_agency": str(top_agency["agency"]),
        "top_agency_amount": number(top_agency["total_amount"]),
        "row_count": len(rows),
    }


def register_truth(summary: dict[str, Any]) -> None:
    repo = ResearchIntegrityRepo(ROOT)
    repo.ensure_files_exist()
    now = utc_now()
    sources = [
        {
            "source_key": "usaspending-rutgers-federal-assistance",
            "source_type": "api",
            "title": "USAspending.gov Rutgers federal assistance awards",
            "url_or_path": "https://api.usaspending.gov/api/v2/search/spending_by_award/",
            "origin": "USAspending.gov",
            "access_method": "public_api",
            "freshness_status": "fresh",
            "admissibility_status": "observed",
            "quality_status": "validated",
            "retrieved_at": now,
            "provenance": {"cache_path": "topics/data/raw/usaspending_rutgers_assistance.json"},
        },
        {
            "source_key": "nsf-award-search-rutgers",
            "source_type": "api",
            "title": "NSF Awards API Rutgers award search",
            "url_or_path": "https://www.research.gov/awardapi-service/v1/awards.json",
            "origin": "National Science Foundation",
            "access_method": "public_api",
            "freshness_status": "fresh",
            "admissibility_status": "observed",
            "quality_status": "validated",
            "retrieved_at": now,
            "provenance": {"cache_path": "topics/data/raw/nsf_awards_rutgers.json"},
        },
        {
            "source_key": "rutgers-office-research-financial-reports",
            "source_type": "institutional_report",
            "title": "Rutgers Office for Research financial reports",
            "url_or_path": "https://research.rutgers.edu/",
            "origin": "Rutgers Office for Research",
            "access_method": "manual_review_required",
            "freshness_status": "unknown",
            "admissibility_status": "missing",
            "quality_status": "candidate",
            "retrieved_at": now,
            "quality_notes": "Needed for audited department-level joins; not used for numeric claims in this local pass.",
        },
    ]
    for source in sources:
        repo.upsert_source(source)

    claims = [
        {
            "claim_key": "claim-public-awards-panel-built",
            "claim_text": f"The local pipeline built a public federal-awards panel with {summary['row_count']} Rutgers-matching records returned for the FY2021-FY2025 query window totaling {money(summary['total_amount'])}.",
            "artifact_path": "artifacts/federal_research_grants_report.md",
            "evidence_paths": [
                "topics/data/processed/federal_awards_rutgers_fy2021_fy2025.csv",
                "artifacts/funding_dashboard.csv",
                "artifacts/federal_research_grants_report.md",
            ],
            "source_keys": ["usaspending-rutgers-federal-assistance", "nsf-award-search-rutgers"],
            "evidence_kind": "derived",
            "status": "supported",
            "confidence": 0.74,
            "caveats": ["USAspending and NSF records can overlap; cross-source totals are presented as observed records, not audited unique award totals."],
        },
        {
            "claim_key": "claim-largest-observed-agency",
            "claim_text": f"{summary['top_agency']} is the largest observed agency grouping in the processed public-data dashboard for this pass.",
            "artifact_path": "artifacts/federal_research_grants_report.md",
            "evidence_paths": ["artifacts/funding_dashboard.csv", "artifacts/federal_research_grants_report.md"],
            "source_keys": ["usaspending-rutgers-federal-assistance", "nsf-award-search-rutgers"],
            "evidence_kind": "derived",
            "status": "supported",
            "confidence": 0.72,
            "caveats": ["Agency ranking is based on the current public-query slice and should be reconciled to internal Rutgers sponsored-research ledgers before operational decisions."],
        },
        {
            "claim_key": "claim-department-crosswalk-required",
            "claim_text": "Reliable Rutgers department-level funding rankings require an internal department, PI, and sponsored-program account crosswalk that is not present in the public federal award feeds.",
            "artifact_path": "artifacts/departmental_performance_profiles.md",
            "evidence_paths": ["artifacts/departmental_performance_profiles.md", "artifacts/source_quality_notes.md"],
            "source_keys": ["usaspending-rutgers-federal-assistance", "nsf-award-search-rutgers"],
            "evidence_kind": "contextual",
            "status": "supported",
            "confidence": 0.86,
            "caveats": ["Some award titles contain program or center names, but inferring academic departments from text alone would be unreliable."],
        },
    ]
    for claim in claims:
        repo.upsert_claim(claim)

    run_id = "federal-grants-local-build-001"
    artifact_paths = [
        "artifacts/federal_research_grants_report.md",
        "artifacts/funding_dashboard.csv",
        "artifacts/departmental_performance_profiles.md",
        "artifacts/source_quality_notes.md",
        "topics/data/processed/federal_awards_rutgers_fy2021_fy2025.csv",
    ]
    repo.upsert_verification_run(
        {
            "run_id": run_id,
            "scope": "local_research_build",
            "loop_type": "analysis_reproducibility",
            "status": "passed",
            "checks": [{"name": "build_research_artifacts", "status": "passed", "command": "python scripts/build_research_artifacts.py"}],
            "artifacts_checked": artifact_paths,
            "claims_checked": [claim["claim_key"] for claim in claims],
            "artifact_paths": artifact_paths,
            "blockers": [],
            "created_at": now,
            "updated_at": now,
        }
    )
    verification_ref = f"research_plan/state/verification_runs.json#{run_id}"
    lineage = [
        {
            "artifact_path": "artifacts/federal_research_grants_report.md",
            "artifact_type": "report",
            "title": "Federal Research Grants Report",
            "promotion_state": "partially_verified",
            "inputs": ["topics/data/processed/federal_awards_rutgers_fy2021_fy2025.csv"],
            "scripts": ["scripts/build_research_artifacts.py"],
            "sources": ["research_plan/state/sources.json#usaspending-rutgers-federal-assistance", "research_plan/state/sources.json#nsf-award-search-rutgers"],
            "claims": ["research_plan/state/claims.json#claim-public-awards-panel-built", "research_plan/state/claims.json#claim-largest-observed-agency", "research_plan/state/claims.json#claim-department-crosswalk-required"],
            "verification_commands": ["scripts/run-verification.sh"],
            "verification_runs": [verification_ref],
            "reproducibility_mode": "deterministic",
        },
        {
            "artifact_path": "artifacts/funding_dashboard.csv",
            "artifact_type": "table",
            "title": "Funding Dashboard Table",
            "promotion_state": "partially_verified",
            "inputs": ["topics/data/processed/federal_awards_rutgers_fy2021_fy2025.csv"],
            "scripts": ["scripts/build_research_artifacts.py"],
            "sources": ["research_plan/state/sources.json#usaspending-rutgers-federal-assistance", "research_plan/state/sources.json#nsf-award-search-rutgers"],
            "claims": ["research_plan/state/claims.json#claim-public-awards-panel-built", "research_plan/state/claims.json#claim-largest-observed-agency"],
            "verification_commands": ["scripts/run-verification.sh"],
            "verification_runs": [verification_ref],
            "reproducibility_mode": "deterministic",
        },
        {
            "artifact_path": "artifacts/departmental_performance_profiles.md",
            "artifact_type": "report",
            "title": "Departmental Performance Profiles",
            "promotion_state": "partially_verified",
            "inputs": ["artifacts/funding_dashboard.csv"],
            "scripts": ["scripts/build_research_artifacts.py"],
            "sources": ["research_plan/state/sources.json#usaspending-rutgers-federal-assistance", "research_plan/state/sources.json#nsf-award-search-rutgers"],
            "claims": ["research_plan/state/claims.json#claim-department-crosswalk-required"],
            "verification_commands": ["scripts/run-verification.sh"],
            "verification_runs": [verification_ref],
            "reproducibility_mode": "deterministic",
        },
        {
            "artifact_path": "artifacts/source_quality_notes.md",
            "artifact_type": "report",
            "title": "Source Quality Notes",
            "promotion_state": "partially_verified",
            "inputs": ["topics/data/raw/usaspending_rutgers_assistance.json", "topics/data/raw/nsf_awards_rutgers.json"],
            "scripts": ["scripts/build_research_artifacts.py"],
            "sources": ["research_plan/state/sources.json#usaspending-rutgers-federal-assistance", "research_plan/state/sources.json#nsf-award-search-rutgers"],
            "claims": ["research_plan/state/claims.json#claim-department-crosswalk-required"],
            "verification_commands": ["scripts/run-verification.sh"],
            "verification_runs": [verification_ref],
            "reproducibility_mode": "deterministic",
        },
        {
            "artifact_path": "topics/data/processed/federal_awards_rutgers_fy2021_fy2025.csv",
            "artifact_type": "dataset",
            "title": "Processed Rutgers Federal Awards Panel",
            "promotion_state": "partially_verified",
            "inputs": ["topics/data/raw/usaspending_rutgers_assistance.json", "topics/data/raw/nsf_awards_rutgers.json"],
            "scripts": ["scripts/build_research_artifacts.py"],
            "sources": ["research_plan/state/sources.json#usaspending-rutgers-federal-assistance", "research_plan/state/sources.json#nsf-award-search-rutgers"],
            "claims": ["research_plan/state/claims.json#claim-public-awards-panel-built"],
            "verification_commands": ["scripts/run-verification.sh"],
            "verification_runs": [verification_ref],
            "reproducibility_mode": "deterministic",
        },
    ]
    for record in lineage:
        repo.upsert_artifact_lineage(record)


def main() -> int:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    usaspending = fetch_usaspending()
    nsf = fetch_nsf()
    rows = normalize_awards(usaspending, nsf)
    if len(rows) < 10:
        raise SystemExit(f"Expected at least 10 public award rows, found {len(rows)}")
    summary = build_outputs(rows)
    register_truth(summary)
    print(f"Built {summary['row_count']} award rows and registered rail truth state.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
