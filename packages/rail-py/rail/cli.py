import argparse
import json
import os
import sys
from typing import Any

import rail

def _print_json(data: Any):
    print(json.dumps(data, indent=2))

def _get_project(args: argparse.Namespace) -> rail.Project:
    if args.local:
        return rail.local(path=args.path)
    
    slug = args.project or os.environ.get("RAIL_PROJECT")
    if not slug:
        print("Error: --project or RAIL_PROJECT env var is required", file=sys.stderr)
        sys.exit(1)
        
    return rail.connect(
        slug=slug,
        api_url=args.api_url,
        api_key=args.api_key,
    )

def cmd_search(project: rail.Project, args: argparse.Namespace):
    _print_json(project.search(args.query))

def cmd_query(project: rail.Project, args: argparse.Namespace):
    if args.command == "sql":
        _print_json(project.query(args.sql).to_dict(orient="records"))
    elif args.command == "classes":
        _print_json(project.classes())
    elif args.command == "entities":
        _print_json(project.entities(args.class_name, limit=args.limit).to_dict(orient="records"))

def cmd_hydrate(project: rail.Project, args: argparse.Namespace):
    _print_json(project.hydrate(pipeline_slug=args.pipeline))

def cmd_reconcile(project: rail.Project, args: argparse.Namespace):
    _print_json(project.reconcile())

def cmd_series(project: rail.Project, args: argparse.Namespace):
    _print_json(project.series(args.series_id).to_dict(orient="records"))

def cmd_secrets(project: rail.Project, args: argparse.Namespace):
    if args.command == "list":
        _print_json(project.list_secrets())
    elif args.command == "set":
        _print_json(project.set_secret(args.key, args.value))

def cmd_integrity(project: rail.Project, args: argparse.Namespace):
    if args.command == "status":
        _print_json(project.integrity_status())
    elif args.command == "assumptions":
        _print_json(project.integrity_assumptions())
    elif args.command == "sources":
        _print_json(project.integrity_sources())
    elif args.command == "claims":
        _print_json(project.integrity_claims())
    elif args.command == "rerun":
        if args.apply:
            _print_json(project.apply_integrity_rerun_plan(args.assumption_key))
        else:
            _print_json(project.integrity_rerun_plan(args.assumption_key))

def cmd_work_order(project: rail.Project, args: argparse.Namespace):
    """Fetch and print the current work order."""
    wo_id = getattr(args, "id", None)
    _print_json(project.get_work_order(work_order_id=wo_id))

def cmd_result(project: rail.Project, args: argparse.Namespace):
    """Submit a session result."""
    if not args.file:
        print("Error: --file is required", file=sys.stderr)
        sys.exit(1)
    with open(args.file) as f:
        result = json.load(f)
    _print_json(project.submit_session_result(result, session_id=getattr(args, "session", None)))

def cmd_ask(project: rail.Project, args: argparse.Namespace):
    """Ask a question."""
    if not args.question:
        print("Error: --question is required", file=sys.stderr)
        sys.exit(1)
    _print_json(project.ask(args.question, session_id=getattr(args, "session", None)))

def main():
    parser = argparse.ArgumentParser(prog="rail", description="RAIL CLI")
    parser.add_argument("--project", help="Project slug (overrides RAIL_PROJECT)")
    parser.add_argument("--api-url", help="API URL (overrides RAIL_API_URL)")
    parser.add_argument("--api-key", help="API Key (overrides RAIL_API_KEY)")
    parser.add_argument("--local", action="store_true", help="Load from local path")
    parser.add_argument("--path", default=".", help="Local project path")

    subparsers = parser.add_subparsers(dest="command")

    # Search
    s_parser = subparsers.add_parser("search", help="Search ontology entities")
    s_parser.add_argument("query", help="Search query")

    # Query
    q_parser = subparsers.add_parser("query", help="Query the project knowledge graph")
    q_subs = q_parser.add_subparsers(dest="query_command")
    
    sql_p = q_subs.add_parser("sql", help="Run SQL query")
    sql_p.add_argument("sql", help="SQL statement")
    
    cls_p = q_subs.add_parser("classes", help="List classes")
    
    ent_p = q_subs.add_parser("entities", help="List entities of a class")
    ent_p.add_argument("class_name", help="Class name")
    ent_p.add_argument("--limit", type=int, default=20)

    # Hydrate
    h_parser = subparsers.add_parser("hydrate", help="Trigger hydration")
    h_parser.add_argument("--pipeline", help="Pipeline slug")

    # Reconcile
    subparsers.add_parser("reconcile", help="Reconcile repo-backed planner/session/control-plane state")

    # Series
    ts_parser = subparsers.add_parser("series", help="Fetch time-series data")
    ts_parser.add_argument("series_id", help="Series identifier")

    # Secrets
    sec_parser = subparsers.add_parser("secrets", help="Manage project secrets")
    sec_subs = sec_parser.add_subparsers(dest="command")
    sec_subs.add_parser("list", help="List secret keys")
    set_sec = sec_subs.add_parser("set", help="Set a secret")
    set_sec.add_argument("key", help="Secret name")
    set_sec.add_argument("value", help="Secret value")

    # Integrity
    i_parser = subparsers.add_parser("integrity", help="Research integrity tools")
    i_subs = i_parser.add_subparsers(dest="command")
    i_subs.add_parser("status", help="Show integrity status")
    i_subs.add_parser("assumptions", help="List assumptions")
    i_subs.add_parser("sources", help="List sources")
    i_subs.add_parser("claims", help="List claims")
    ir = i_subs.add_parser("rerun", help="Preview or apply rerun plan for an assumption")
    ir.add_argument("assumption_key", help="The assumption that changed")
    ir.add_argument("--apply", action="store_true", help="Actually create the rerun tasks")

    # Work Order
    wo_parser = subparsers.add_parser("work-order", help="Fetch the current work order")
    wo_parser.add_argument("--id", help="Work order ID (optional if RAIL_WORK_ORDER_ID set)")

    # Result
    res_parser = subparsers.add_parser("result", help="Submit a session result")
    res_parser.add_argument("--file", help="Path to session_result.json")
    res_parser.add_argument("--session", help="Session ID (optional if RAIL_SESSION_ID set)")

    # Ask
    ask_parser = subparsers.add_parser("ask", help="Ask a question")
    ask_parser.add_argument("question", help="The question to ask")
    ask_parser.add_argument("--session", help="Session ID (optional if RAIL_SESSION_ID set)")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    project = _get_project(args)

    if args.command == "search":
        cmd_search(project, args)
    elif args.command == "query":
        cmd_query(project, args)
    elif args.command == "hydrate":
        cmd_hydrate(project, args)
    elif args.command == "reconcile":
        cmd_reconcile(project, args)
    elif args.command == "series":
        cmd_series(project, args)
    elif args.command == "secrets":
        cmd_secrets(project, args)
    elif args.command == "integrity":
        cmd_integrity(project, args)
    elif args.command == "work-order":
        cmd_work_order(project, args)
    elif args.command == "result":
        cmd_result(project, args)
    elif args.command == "ask":
        cmd_ask(project, args)

if __name__ == "__main__":
    main()
