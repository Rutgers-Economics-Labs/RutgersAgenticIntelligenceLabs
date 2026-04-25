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
    for value in os.environ.get("WORK_ORDER_STATUSES", "ready").split(",")
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
STATE_FILE = Path(
    os.environ.get(
        "JULES_RUNNER_STATE_FILE",
        os.path.join(WORK_ORDERS_DIR, ".jules-runner-state.json"),
    )
)


@dataclass
class WorkOrder:
    work_order_id: str
    path: Path
    title: str
    status: str
    depends_on: list[str]
    raw_content: str


def load_runner_state() -> dict:
    if not STATE_FILE.exists():
        return {
            "starting_branch": None,
            "completed_work_order_ids": [],
            "active_session": None,
            "session_history": [],
        }
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception as exc:
        print(f"Warning: could not read runner state from {STATE_FILE}: {exc}")
        return {
            "starting_branch": None,
            "completed_work_order_ids": [],
            "active_session": None,
            "session_history": [],
        }


def save_runner_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    temp_file = STATE_FILE.with_suffix(f"{STATE_FILE.suffix}.tmp")
    temp_file.write_text(json.dumps(state, indent=2, sort_keys=True))
    temp_file.replace(STATE_FILE)


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
    id_match = re.match(r"^(WO-[A-Za-z0-9.\-]+)", title)
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
    files = sorted(glob.glob(os.path.join(WORK_ORDERS_DIR, "WO-*.md")))
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


def partition_work_orders(
    work_orders: list[WorkOrder],
    cached_completed_ids: set[str] | None = None,
    active_work_order_id: str | None = None,
) -> tuple[dict[str, WorkOrder], list[WorkOrder]]:
    by_id = {work_order.work_order_id: work_order for work_order in work_orders}
    completed_ids = {
        work_order.work_order_id
        for work_order in work_orders
        if work_order.status == "completed"
    }
    if cached_completed_ids:
        completed_ids.update(cached_completed_ids)

    ready: list[WorkOrder] = []
    for work_order in work_orders:
        if active_work_order_id and work_order.work_order_id == active_work_order_id:
            continue
        if work_order.work_order_id in completed_ids:
            continue
        if WORK_ORDER_IDS and work_order.work_order_id not in WORK_ORDER_IDS:
            continue
        if work_order.status not in STATUS_ALLOWLIST:
            continue

        unmet = [
            dependency
            for dependency in work_order.depends_on
            if dependency not in completed_ids
        ]
        if unmet and not IGNORE_DEPENDENCIES:
            continue
        ready.append(work_order)

    if MAX_ORDERS is not None:
        ready = ready[:MAX_ORDERS]

    return by_id, ready


def print_queue_summary(
    work_orders: list[WorkOrder],
    ready_queue: list[WorkOrder],
    cached_completed_ids: set[str] | None = None,
    active_session: dict | None = None,
) -> None:
    print(f"Found {len(work_orders)} future work orders in {WORK_ORDERS_DIR}.")
    status_counts: dict[str, int] = {}
    for work_order in work_orders:
        status_counts[work_order.status] = status_counts.get(work_order.status, 0) + 1

    print("Status summary:")
    for status in sorted(status_counts):
        print(f"  - {status}: {status_counts[status]}")

    if cached_completed_ids:
        print(f"Cached completed work orders: {len(cached_completed_ids)}")
    if active_session:
        print(
            "Active cached session: "
            f"{active_session.get('work_order_id')} ({active_session.get('session_id')})"
        )

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
    state = load_runner_state()
    if os.environ.get("RESET_RUNNER_STATE") == "1":
        state = {
            "starting_branch": None,
            "completed_work_order_ids": [],
            "active_session": None,
            "session_history": [],
        }
        save_runner_state(state)
        print(f"Reset runner state at {STATE_FILE}.")

    starting_branch = os.environ.get("STARTING_BRANCH") or state.get("starting_branch") or git_current_branch()
    state["starting_branch"] = starting_branch
    save_runner_state(state)
    print(f"Initial starting branch: {starting_branch}")
    print(f"Runner state file: {STATE_FILE}")

    resume_id = os.environ.get("RESUME_SESSION_ID")

    try:
        while True:
            work_orders = list_work_orders()
            if not work_orders:
                print(f"No future work orders found in {WORK_ORDERS_DIR}.")
                return

            cached_completed_ids = set(state.get("completed_work_order_ids", []))
            active_session = state.get("active_session")
            active_work_order_id = active_session.get("work_order_id") if active_session else None

            if (
                active_session
                and active_work_order_id in cached_completed_ids
                and not resume_id
            ):
                print(
                    "Clearing stale active session cache for already-completed work order: "
                    f"{active_work_order_id} ({active_session.get('session_id')})"
                )
                state["active_session"] = None
                save_runner_state(state)
                active_session = None
                active_work_order_id = None

            by_id, ready_queue = partition_work_orders(
                work_orders,
                cached_completed_ids=cached_completed_ids,
                active_work_order_id=active_work_order_id,
            )
            print_queue_summary(
                work_orders,
                ready_queue,
                cached_completed_ids=cached_completed_ids,
                active_session=active_session,
            )

            if DRY_RUN:
                print("DRY_RUN=1, exiting without creating Jules sessions.")
                return

            if active_session:
                work_order = by_id.get(active_session["work_order_id"])
                if not work_order:
                    print(
                        "Cached active session references a work order that no longer exists. "
                        "Clearing active session cache."
                    )
                    state["active_session"] = None
                    save_runner_state(state)
                    continue
            else:
                if not ready_queue:
                    print("No ready work orders remain. Runner is finished.")
                    break
                work_order = ready_queue[0]

            print(f"\n{'=' * 60}")
            print(f"Processing {work_order.work_order_id}")
            print(f"Base branch: {starting_branch}")
            print(f"{'=' * 60}")

            session_id = None
            session_name = None

            if resume_id or active_session:
                session_id = resume_id or active_session["session_id"]
                print(f"Resuming existing session: {session_id}")
                try:
                    response = requests.get(f"{API_URL}/sessions/{session_id}", headers=headers)
                    response.raise_for_status()
                    session = response.json()
                    session_name = session["name"]
                    state["active_session"] = {
                        "work_order_id": work_order.work_order_id,
                        "session_id": session_id,
                        "session_name": session_name,
                        "title": work_order.title,
                        "starting_branch": starting_branch,
                        "resumed_at": int(time.time()),
                    }
                    save_runner_state(state)
                    resume_id = None
                except Exception as exc:
                    print(f"Failed to resume session {session_id}: {exc}")
                    break
            else:
                if not AUTO_APPROVE:
                    approved = parse_bool_prompt(
                        f"Create a Jules session for {work_order.work_order_id}?",
                        default=False,
                    )
                    if not approved:
                        print("Stopping before creating the next session.")
                        break

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
                    state["active_session"] = {
                        "work_order_id": work_order.work_order_id,
                        "session_id": session_id,
                        "session_name": session_name,
                        "title": work_order.title,
                        "starting_branch": starting_branch,
                        "created_at": int(time.time()),
                    }
                    save_runner_state(state)
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
            state["starting_branch"] = starting_branch
            completed_work_order_ids = set(state.get("completed_work_order_ids", []))
            completed_work_order_ids.add(work_order.work_order_id)
            state["completed_work_order_ids"] = sorted(completed_work_order_ids)
            state.setdefault("session_history", []).append(
                {
                    "work_order_id": work_order.work_order_id,
                    "session_id": session_id,
                    "session_name": session_name,
                    "pull_request_url": pr_url,
                    "result_branch": branch_name,
                    "completed_at": int(time.time()),
                }
            )
            state["active_session"] = None
            save_runner_state(state)

            print(f"Next work order will build off branch: '{starting_branch}'")
            print("Sleeping briefly before starting the next work order...")
            time.sleep(10)

    except KeyboardInterrupt:
        save_runner_state(state)
        print("\nInterrupted. Runner state was saved for resume.")
        return

    print("\nJules queue processing finished.")


if __name__ == "__main__":
    main()
