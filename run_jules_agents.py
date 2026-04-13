#!/usr/bin/env python3
import glob
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import requests


API_KEY = os.environ.get("JULES_API_KEY")
if not API_KEY:
    print("Error: Please set the JULES_API_KEY environment variable.")
    print("Example: export JULES_API_KEY='your_api_key'")
    sys.exit(1)

API_URL = os.environ.get("JULES_API_URL", "https://jules.googleapis.com/v1alpha")
SOURCE = os.environ.get(
    "JULES_SOURCE",
    "sources/github/Rutgers-Economics-Labs/RutgersAgenticIntelligenceLabs",
)
WORK_ORDERS_DIR = os.environ.get("WORK_ORDERS_DIR", "state/work-orders")
STATUS_ALLOWLIST = {
    value.strip().lower()
    for value in os.environ.get("WORK_ORDER_STATUSES", "pending").split(",")
    if value.strip()
}
WORK_ORDER_IDS = {
    value.strip()
    for value in os.environ.get("WORK_ORDER_IDS", "").split(",")
    if value.strip()
}
AUTO_APPROVE = os.environ.get("AUTO_APPROVE", "0") == "1"
DRY_RUN = os.environ.get("DRY_RUN", "0") == "1"
IGNORE_DEPENDENCIES = os.environ.get("IGNORE_DEPENDENCIES", "0") == "1"
POLL_INTERVAL_SECONDS = int(os.environ.get("POLL_INTERVAL_SECONDS", "15"))
MAX_ORDERS = int(os.environ["MAX_ORDERS"]) if os.environ.get("MAX_ORDERS") else None


@dataclass
class WorkOrder:
    work_order_id: str
    path: Path
    title: str
    status: str
    depends_on: list[str]
    raw_content: str


def parse_bool_prompt(message: str, default: bool = False) -> bool:
    suffix = "[Y/n]" if default else "[y/N]"
    answer = input(f"{message} {suffix} ").strip().lower()
    if not answer:
        return default
    return answer in {"y", "yes"}


def parse_metadata_field(content: str, field_name: str) -> str | None:
    pattern = rf"^\*\*{re.escape(field_name)}:\*\*\s*(.+?)\s*$"
    match = re.search(pattern, content, flags=re.MULTILINE)
    return match.group(1).strip() if match else None


def parse_depends_on(raw_value: str | None) -> list[str]:
    if not raw_value or raw_value.lower() == "none":
        return []
    parts = [part.strip() for part in raw_value.split(",")]
    return [part.strip("` ") for part in parts if part.strip()]


def parse_work_order(path: Path) -> WorkOrder:
    content = path.read_text()
    title = path.stem
    id_match = re.match(r"^(WO-F\d+\.\d+)", title)
    work_order_id = id_match.group(1) if id_match else title
    status = (parse_metadata_field(content, "Status") or "pending").lower()
    depends_on = parse_depends_on(parse_metadata_field(content, "Depends on"))
    return WorkOrder(
        work_order_id=work_order_id,
        path=path,
        title=title,
        status=status,
        depends_on=depends_on,
        raw_content=content,
    )


def list_work_orders() -> list[WorkOrder]:
    files = sorted(glob.glob(os.path.join(WORK_ORDERS_DIR, "WO-F*.md")))
    return [parse_work_order(Path(file_path)) for file_path in files]


def git_current_branch() -> str:
    explicit = os.environ.get("STARTING_BRANCH")
    if explicit:
        return explicit
    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True,
            text=True,
            check=True,
        )
        branch = result.stdout.strip()
        if branch:
            return branch
    except Exception:
        pass
    return "future"


def get_pr_branch(pr_url: str) -> str | None:
    try:
        res = subprocess.run(
            ["gh", "pr", "view", pr_url, "--json", "headRefName"],
            capture_output=True,
            text=True,
            check=True,
        )
        data = json.loads(res.stdout)
        return data.get("headRefName")
    except Exception as exc:
        print(f"Error fetching PR info using gh CLI: {exc}")
        if isinstance(exc, subprocess.CalledProcessError):
            print(f"CLI Error Output: {exc.stderr}")
        return None


def partition_work_orders(work_orders: list[WorkOrder]) -> tuple[dict[str, WorkOrder], list[WorkOrder]]:
    by_id = {work_order.work_order_id: work_order for work_order in work_orders}
    completed = {
        work_order.work_order_id: work_order
        for work_order in work_orders
        if work_order.status == "completed"
    }

    ready: list[WorkOrder] = []
    for work_order in work_orders:
        if WORK_ORDER_IDS and work_order.work_order_id not in WORK_ORDER_IDS:
            continue
        if work_order.status not in STATUS_ALLOWLIST:
            continue

        unmet = [
            dependency
            for dependency in work_order.depends_on
            if dependency not in completed
        ]
        if unmet and not IGNORE_DEPENDENCIES:
            continue
        ready.append(work_order)

    if MAX_ORDERS is not None:
        ready = ready[:MAX_ORDERS]

    return by_id, ready


def print_queue_summary(work_orders: list[WorkOrder], ready_queue: list[WorkOrder]) -> None:
    print(f"Found {len(work_orders)} future work orders in {WORK_ORDERS_DIR}.")
    status_counts: dict[str, int] = {}
    for work_order in work_orders:
        status_counts[work_order.status] = status_counts.get(work_order.status, 0) + 1

    print("Status summary:")
    for status in sorted(status_counts):
        print(f"  - {status}: {status_counts[status]}")

    if not ready_queue:
        print("No ready work orders matched the current filters.")
        return

    print("Ready queue:")
    for work_order in ready_queue:
        deps = ", ".join(work_order.depends_on) if work_order.depends_on else "none"
        print(f"  - {work_order.work_order_id} ({work_order.status}; depends on: {deps})")


def build_prompt(work_order: WorkOrder) -> str:
    return (
        "Please implement the following future work order. "
        "The spec details are below.\n\n"
        f"{work_order.raw_content}\n\n"
        "Important constraints:\n"
        "- Respect the future repo contract and existing local changes.\n"
        "- Do not undo unrelated work.\n"
        "- Run the most relevant verification commands after implementation.\n"
        "- If the work order requires human approval or missing secrets, stop and ask.\n"
    )


def create_session(headers: dict[str, str], prompt: str, title: str, starting_branch: str) -> dict:
    payload = {
        "prompt": prompt,
        "sourceContext": {
            "source": SOURCE,
            "githubRepoContext": {
                "startingBranch": starting_branch,
            },
        },
        "automationMode": "AUTO_CREATE_PR",
        "title": title,
    }
    response = requests.post(f"{API_URL}/sessions", headers=headers, json=payload)
    response.raise_for_status()
    return response.json()


def handle_feedback(headers: dict[str, str], session_name: str) -> bool:
    print("Session is awaiting user feedback.")
    if AUTO_APPROVE:
        default_message = "Please continue carefully, follow the current plan, and run verification before finishing."
        print("AUTO_APPROVE=1, sending default feedback message.")
        requests.post(
            f"{API_URL}/{session_name}:sendMessage",
            json={"prompt": default_message},
            headers=headers,
        ).raise_for_status()
        return True

    print("Type a reply to send back to Jules.")
    print("Press Enter with no text to keep polling.")
    print("Type 'abort' to stop this run.")
    answer = input("> ").strip()
    if not answer:
        return True
    if answer.lower() == "abort":
        return False

    requests.post(
        f"{API_URL}/{session_name}:sendMessage",
        json={"prompt": answer},
        headers=headers,
    ).raise_for_status()
    return True


def poll_session(headers: dict[str, str], session_id: str, session_name: str) -> str | None:
    pr_url = None
    session_completed = False

    while not session_completed:
        time.sleep(POLL_INTERVAL_SECONDS)
        print(f"Polling session {session_id} for completion...")

        try:
            session_response = requests.get(f"{API_URL}/{session_name}", headers=headers)
            if session_response.ok:
                session = session_response.json()
                state = session.get("state")
                if state:
                    print(f"Current state: {state}")

                if state == "AWAITING_USER_FEEDBACK":
                    if not handle_feedback(headers, session_name):
                        return None

                if "outputs" in session:
                    for output in session["outputs"]:
                        if "pullRequest" in output:
                            pr_url = output["pullRequest"]["url"]
                            session_completed = True
                            break

            if not session_completed:
                activities_response = requests.get(
                    f"{API_URL}/{session_name}/activities?pageSize=10",
                    headers=headers,
                )
                if activities_response.ok:
                    activities = activities_response.json().get("activities", [])
                    for activity in activities:
                        if "sessionCompleted" in activity:
                            session_completed = True
                            break
        except Exception as exc:
            print(f"Error while polling: {exc}")

    return pr_url


def main() -> None:
    headers = {
        "X-Goog-Api-Key": API_KEY,
        "Content-Type": "application/json",
    }

    work_orders = list_work_orders()
    if not work_orders:
        print(f"No future work orders found in {WORK_ORDERS_DIR}.")
        return

    _, ready_queue = partition_work_orders(work_orders)
    print_queue_summary(work_orders, ready_queue)

    if DRY_RUN:
        print("DRY_RUN=1, exiting without creating Jules sessions.")
        return

    if not ready_queue:
        print("Nothing ready to run.")
        return

    starting_branch = git_current_branch()
    print(f"Initial starting branch: {starting_branch}")

    resume_id = os.environ.get("RESUME_SESSION_ID")

    for work_order in ready_queue:
        print(f"\n{'=' * 60}")
        print(f"Processing {work_order.work_order_id}")
        print(f"Base branch: {starting_branch}")
        print(f"{'=' * 60}")

        if not AUTO_APPROVE:
            approved = parse_bool_prompt(
                f"Create a Jules session for {work_order.work_order_id}?",
                default=False,
            )
            if not approved:
                print("Stopping before creating the next session.")
                break

        session_id = None
        session_name = None

        if resume_id:
            session_id = resume_id
            print(f"Resuming existing session: {session_id}")
            try:
                response = requests.get(f"{API_URL}/sessions/{session_id}", headers=headers)
                response.raise_for_status()
                session = response.json()
                session_name = session["name"]
                resume_id = None
            except Exception as exc:
                print(f"Failed to resume session {session_id}: {exc}")
                break
        else:
            print("Creating Jules session...")
            try:
                session = create_session(
                    headers=headers,
                    prompt=build_prompt(work_order),
                    title=work_order.title,
                    starting_branch=starting_branch,
                )
                session_id = session["id"]
                session_name = session["name"]
                print(f"Session created successfully: {session_id}")
            except Exception as exc:
                print(f"Failed to create session: {exc}")
                break

        pr_url = poll_session(headers, session_id, session_name)
        if not pr_url:
            print("Session finished without a PR or was interrupted. Stopping chain.")
            break

        print(f"Session complete. PR created: {pr_url}")
        print("Extracting branch name from PR...")

        branch_name = get_pr_branch(pr_url)
        if not branch_name:
            print("Could not determine PR branch. Aborting to avoid conflicts.")
            break

        starting_branch = branch_name
        print(f"Next work order will build off branch: '{starting_branch}'")
        print("Sleeping briefly before starting the next work order...")
        time.sleep(10)

    print("\nJules queue processing finished.")


if __name__ == "__main__":
    main()
