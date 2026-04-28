import argparse
import json
import os
import sys
from typing import Any

import rail

def _print_json(data: Any):
    print(json.dumps(data, indent=2))

def _get_project(args: argparse.Namespace) -> rail.Project:
    if args.local or os.path.exists("rail.yaml"):
        return rail.local(path=args.path)
    
    if not args.project:
        print("Error: --project <slug> is required for cloud mode (or run in a local project directory).")
        sys.exit(1)
    
    return rail.connect(
        slug=args.project,
        api_url=args.api_url,
        api_key=args.api_key
    )

def cmd_search(project: rail.Project, args: argparse.Namespace):
    if args.type == "registry":
        results = project.search_registry(args.query, provider=args.provider, geography=args.geography)
    else:
        results = project.discover(args.query, tags=args.tags.split(",") if args.tags else None)
    _print_json(results)

def cmd_query(project: rail.Project, args: argparse.Namespace):
    if args.command == "sql":
        df = project.query(args.query_text)
        print(df.to_string())
    elif args.command == "entities":
        df = project.entities(args.class_name, limit=args.limit)
        print(df.to_string())
    elif args.command == "search":
        results = project.search(args.query_text)
        _print_json(results)
    elif args.command == "classes":
        results = project.classes()
        _print_json(results)

def cmd_hydrate(project: rail.Project, args: argparse.Namespace):
    result = project.hydrate(pipeline_slug=args.pipeline)
    _print_json(result)

def cmd_series(project: rail.Project, args: argparse.Namespace):
    df = project.series(args.series_id)
    print(df.to_string())

def cmd_secrets(project: rail.Project, args: argparse.Namespace):
    if args.secrets_command == "list":
        results = project.list_secrets()
        _print_json(results)
    elif args.secrets_command == "set":
        result = project.set_secret(args.key, args.value)
        _print_json(result)
    elif args.secrets_command == "delete":
        result = project.delete_secret(args.key)
        _print_json(result)

def main():
    parser = argparse.ArgumentParser(prog="rail", description="RAIL platform CLI")
    parser.add_argument("--project", help="Project slug (cloud mode)")
    parser.add_argument("--api-url", help="RAIL API URL")
    parser.add_argument("--api-key", help="RAIL API Key")
    parser.add_argument("--local", action="store_true", help="Force local mode")
    parser.add_argument("--path", default=".", help="Local project path")

    subparsers = parser.add_subparsers(dest="command", help="Subcommands")

    # Search
    p_search = subparsers.add_parser("search", help="Search registry or templates")
    p_search.add_argument("query", help="Search query")
    p_search.add_argument("--type", choices=["registry", "templates"], default="registry")
    p_search.add_argument("--provider", help="Filter by provider (registry only)")
    p_search.add_argument("--geography", help="Filter by geography (registry only)")
    p_search.add_argument("--tags", help="Comma-separated tags (templates only)")

    # Query
    p_query = subparsers.add_parser("query", help="Query the knowledge graph")
    q_subs = p_query.add_subparsers(dest="query_command")
    
    psql = q_subs.add_parser("sql", help="Run SQL")
    psql.add_argument("query_text", help="DuckDB SQL query")
    
    pent = q_subs.add_parser("entities", help="List entities of a class")
    pent.add_argument("class_name", help="Ontology class name")
    pent.add_argument("--limit", type=int, default=20)
    
    psearch = q_subs.add_parser("search", help="Search entities")
    psearch.add_argument("query_text", help="Search term")
    
    pclasses = q_subs.add_parser("classes", help="List ontology classes")

    # Hydrate
    p_hydrate = subparsers.add_parser("hydrate", help="Run hydration pipeline")
    p_hydrate.add_argument("--pipeline", help="Pipeline slug")

    # Series
    p_series = subparsers.add_parser("series", help="Fetch time-series data")
    p_series.add_argument("series_id", help="Series identifier")

    # Secrets
    p_secrets = subparsers.add_parser("secrets", help="Manage project secrets")
    s_subs = p_secrets.add_subparsers(dest="secrets_command")
    
    sl = s_subs.add_parser("list", help="List project secrets")
    
    ss = s_subs.add_parser("set", help="Set a project secret")
    ss.add_argument("key", help="Secret key name")
    ss.add_argument("value", help="Secret plaintext value")
    
    sd = s_subs.add_parser("delete", help="Delete a project secret")
    sd.add_argument("key", help="Secret key name")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    project = _get_project(args)

    if args.command == "search":
        cmd_search(project, args)
    elif args.command == "query":
        args.command = args.query_command # nested
        cmd_query(project, args)
    elif args.command == "hydrate":
        cmd_hydrate(project, args)
    elif args.command == "series":
        cmd_series(project, args)
    elif args.command == "secrets":
        cmd_secrets(project, args)

if __name__ == "__main__":
    main()
