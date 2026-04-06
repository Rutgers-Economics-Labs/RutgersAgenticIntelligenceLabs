#!/usr/bin/env python3
import os
import glob
import json
import time
import requests
import subprocess

# Set this to your Jules API Key
API_KEY = os.environ.get("JULES_API_KEY")
if not API_KEY:
    print("Error: Please set the JULES_API_KEY environment variable.")
    print("Example: export JULES_API_KEY='your_api_key'")
    exit(1)

API_URL = "https://jules.googleapis.com/v1alpha"
SOURCE = "sources/github/Rutgers-Economics-Labs/RutgersAgenticIntelligenceLabs"
WORK_ORDERS_DIR = "state/work-orders"

def get_pr_branch(pr_url):
    """Uses GitHub CLI to fetch the branch name of a given PR URL."""
    try:
        res = subprocess.run(
            ["gh", "pr", "view", pr_url, "--json", "headRefName"], 
            capture_output=True, 
            text=True, 
            check=True
        )
        data = json.loads(res.stdout)
        return data.get("headRefName")
    except Exception as e:
        print(f"Error fetching PR info using gh CLI: {e}")
        if isinstance(e, subprocess.CalledProcessError):
            print(f"CLI Error Output: {e.stderr}")
        return None

def main():
    headers = {
         "X-Goog-Api-Key": API_KEY,
         "Content-Type": "application/json"
    }
    
    # 1. Glob work orders and sort them
    files = sorted(glob.glob(os.path.join(WORK_ORDERS_DIR, "WO-*.md")))
    if not files:
        print(f"No work orders found in {WORK_ORDERS_DIR}.")
        return

    # Skip completed work orders
    skip_list = ["WO-0.1", "WO-0.2", "WO-0.3", "WO-1.1", "WO-1.2", "WO-2.1", "WO-2.2"]
    files = [f for f in files if not any(s in f for s in skip_list)]

    print(f"Found {len(files)} remaining work orders to process.")

    # Use the branch created by Jules for the previous work order (WO-2.2) as our new baseline
    starting_branch = "project-scoped-routes-11462404618152258496"

    resume_id = os.environ.get("RESUME_SESSION_ID")

    for file in files:
        print(f"\n{'='*50}")
        print(f"Processing {file}")
        print(f"Base branch: {starting_branch}")
        print(f"{'='*50}")
        
        session_id = None
        session_name = None

        if resume_id:
            session_id = resume_id
            print(f"Resuming existing session: {session_id}")
            try:
                resp = requests.get(f"{API_URL}/sessions/{session_id}", headers=headers)
                resp.raise_for_status()
                session = resp.json()
                session_name = session['name']
                resume_id = None # Only resume once
            except Exception as e:
                print(f"Failed to resume session {session_id}: {e}")
                break
        else:
            with open(file, "r") as f:
                content = f.read()

            title = os.path.basename(file).replace('.md', '')
            prompt = (
                f"Please implement the following work order. The spec details are below:\n\n{content}\n\n"
                "CRITICAL: After implementing the changes, you MUST run the appropriate test scripts or verification commands "
                "(e.g., 'make hydrate', 'make test', or equivalent) to ensure there are no regressions. "
                "You have access to all necessary environment variables in your workspace."
            )

            payload = {
                "prompt": prompt,
                "sourceContext": {
                    "source": SOURCE,
                    "githubRepoContext": {
                        "startingBranch": starting_branch
                    }
                },
                "automationMode": "AUTO_CREATE_PR",
                "title": title
            }

            # 2. Start Jules session
            print("Creating Jules session...")
            try:
                resp = requests.post(f"{API_URL}/sessions", headers=headers, json=payload)
                resp.raise_for_status()
                session = resp.json()
                session_id = session['id']
                session_name = session['name']
                print(f"Session Created successfully: {session_id}")
            except Exception as e:
                print(f"Failed to create session: {e}")
                break

        # 3. Poll until complete and extract PR
        pr_url = None
        session_completed = False
        last_feedback_time = 0
        
        while not session_completed:
            time.sleep(15)
            print(f"Polling session {session_id} for completion...")
            
            try:
                # Check for sessions state (Looking for outputs -> pullRequest)
                poll_resp = requests.get(f"{API_URL}/{session_name}", headers=headers)
                
                if poll_resp.ok:
                    poll_session = poll_resp.json()
                    
                    # Handle AWAITING_USER_FEEDBACK
                    if poll_session.get("state") == "AWAITING_USER_FEEDBACK":
                        current_time = time.time()
                        if current_time - last_feedback_time > 60:
                            print(f"Session {session_id} is awaiting feedback. Auto-confirming...")
                            msg_payload = {"prompt": "Yes, please proceed with the current plan. Make sure to run tests!"}
                            requests.post(f"{API_URL}/{session_name}:sendMessage", json=msg_payload, headers=headers)
                            last_feedback_time = current_time

                    if "outputs" in poll_session:
                        for output in poll_session["outputs"]:
                            if "pullRequest" in output:
                                pr_url = output["pullRequest"]["url"]
                                session_completed = True
                                break
                
                # Check activities to see if the session finished early or failed
                if not session_completed:
                    act_resp = requests.get(f"{API_URL}/{session_name}/activities?pageSize=10", headers=headers)
                    if act_resp.ok:
                        acts = act_resp.json().get("activities", [])
                        for activity in acts:
                            if "sessionCompleted" in activity:
                                session_completed = True
                                break
            except Exception as e:
                print(f"Error while polling: {e}")
                # We can continue trying
                pass

        if pr_url:
            print(f"Session complete! PR created: {pr_url}")
            print("Extracting branch name from PR...")
            
            # 4. Grab branch name from the PR so the next agent builds off it
            branch_name = get_pr_branch(pr_url)
            
            if branch_name:
                starting_branch = branch_name
                print(f"-> Next work order will build off branch: '{starting_branch}'")
            else:
                print("Could not determine PR branch. Aborting to avoid conflicts.")
                break
        else:
            print("Session completed, but no PR was produced. Stopping chain.")
            break

        # Optional: Add an artificial delay before creating the next agent session
        print("Sleeping briefly before starting the next work order...")
        time.sleep(10)

    print("\nAll tasks processed! Check your repository for the generated PRs.")

if __name__ == '__main__':
    main()
