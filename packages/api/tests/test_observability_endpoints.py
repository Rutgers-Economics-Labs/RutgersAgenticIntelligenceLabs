from __future__ import annotations

import json
from pathlib import Path
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_get_planner_decisions(tmp_path, monkeypatch):
    slug = "test-proj"
    local_repo_path = tmp_path
    
    async def _refresh_project_record(s):
        return {"_id": "project-1", "slug": s, "localRepoPath": str(local_repo_path)}
        
    monkeypatch.setattr("app.routers.projects._refresh_project_record", _refresh_project_record)
    
    # Write some fake decisions
    decisions_dir = local_repo_path / "research_plan"
    decisions_dir.mkdir(parents=True, exist_ok=True)
    decisions_file = decisions_dir / "planner_decisions.jsonl"
    
    decisions_data = [
        {"tool": "list_tasks", "args": {}, "result_summary": "Listed 5 tasks", "rationale": "Checking progress", "timestamp": 1000.0},
        {"tool": "create_task", "args": {"title": "Task A"}, "result_summary": "Task 'Task A' is ready", "rationale": "Next step", "timestamp": 2000.0},
    ]
    
    with open(decisions_file, "w", encoding="utf-8") as f:
        for item in decisions_data:
            f.write(json.dumps(item) + "\n")
            
    response = client.get(f"/api/v1/projects/{slug}/planner/decisions?limit=50")
    assert response.status_code == 200
    res_data = response.json()
    assert len(res_data) == 2
    # Should be in reverse order
    assert res_data[0]["tool"] == "create_task"
    assert res_data[1]["tool"] == "list_tasks"


def test_qa_pending_and_answer(tmp_path, monkeypatch):
    slug = "test-proj"
    local_repo_path = tmp_path
    
    async def _refresh_project_record(s):
        return {"_id": "project-1", "slug": s, "localRepoPath": str(local_repo_path)}
        
    monkeypatch.setattr("app.routers.projects._refresh_project_record", _refresh_project_record)
    
    qa_dir = local_repo_path / "research_plan" / "decisions"
    qa_dir.mkdir(parents=True, exist_ok=True)
    qa_file = qa_dir / "qa_log.json"
    
    qa_data = [
        {
            "question_id": "q1",
            "session_id": "sess-1",
            "question": "What is the primary indicator?",
            "answer": None,
            "tier": 3,
            "status": "pending",
            "timestamp": "2026-05-22T00:00:00Z"
        },
        {
            "question_id": "q2",
            "session_id": "sess-1",
            "question": "Where is the input file?",
            "answer": "in data/ folder",
            "tier": 2,
            "status": "resolved",
            "timestamp": "2026-05-22T00:01:00Z"
        }
    ]
    
    qa_file.write_text(json.dumps(qa_data, indent=2), encoding="utf-8")
    
    # Test GET pending
    response = client.get(f"/api/v1/projects/{slug}/qa/pending")
    assert response.status_code == 200
    pending = response.json()
    assert len(pending) == 1
    assert pending[0]["question_id"] == "q1"
    
    # Test POST answer
    mutations_called = []
    async def _mock_mutation(name, args):
        mutations_called.append((name, args))
        return None

    async def _get_running_agent(session_id):
        return {"_id": "agent-1", "status": "awaiting_input"}

    async def _update_running_agent(session_id, **fields):
        pass

    monkeypatch.setattr("app.services.convex_client.convex.mutation", _mock_mutation)
    monkeypatch.setattr("app.services.running_agent_service.get_running_agent", _get_running_agent)
    monkeypatch.setattr("app.services.running_agent_service.update_running_agent", _update_running_agent)
    
    response = client.post(f"/api/v1/projects/{slug}/qa/q1/answer", json={"answer": "It is NJ housing prices"})
    assert response.status_code == 200
    assert response.json()["status"] == "resolved"
    
    # Verify file is updated
    updated_log = json.loads(qa_file.read_text(encoding="utf-8"))
    q1_entry = next(item for item in updated_log if item["question_id"] == "q1")
    assert q1_entry["answer"] == "It is NJ housing prices"
    assert q1_entry["status"] == "resolved"
    
    # Verify Convex was called to relay progress
    assert len(mutations_called) == 1
    assert mutations_called[0][0] == "runnerEvents:append"
    assert mutations_called[0][1]["eventType"] == "progress"


def test_hold_approve_reject_dispatch(tmp_path, monkeypatch):
    slug = "test-proj"
    local_repo_path = tmp_path
    
    async def _refresh_project_record(s):
        return {"_id": "project-1", "slug": s, "localRepoPath": str(local_repo_path)}
        
    monkeypatch.setattr("app.routers.projects._refresh_project_record", _refresh_project_record)
    
    pending_dir = local_repo_path / "research_plan" / "pending_dispatch"
    pending_dir.mkdir(parents=True, exist_ok=True)
    pending_file = pending_dir / "wo-123.json"
    
    pending_data = {
        "runner_name": "codex_cli",
        "project_id": "proj-123",
        "running_session_id": "sess-123",
        "task_payload": {
            "work_order_id": "wo-123",
            "task_description": "Run coding task",
            "role": "coding",
            "branch": "main",
        }
    }
    pending_file.write_text(json.dumps(pending_data, indent=2), encoding="utf-8")
    
    # Test GET pending dispatches
    response = client.get(f"/api/v1/projects/{slug}/dispatches/pending")
    assert response.status_code == 200
    dispatches = response.json()
    assert len(dispatches) == 1
    assert dispatches[0]["task_payload"]["work_order_id"] == "wo-123"
    
    # Test POST approve
    async def _mock_resume_pending_dispatch(project_root, work_order_id, edits):
        return {"convex_session_id": "sess-123", "status": "running"}
        
    monkeypatch.setattr("app.runners.session_lifecycle.resume_pending_dispatch", _mock_resume_pending_dispatch)
    
    response = client.post(f"/api/v1/projects/{slug}/dispatches/wo-123/approve", json={"edits": {"some_field": "val"}})
    assert response.status_code == 200
    assert response.json()["status"] == "running"
    
    # Test POST reject
    async def _mock_reject_pending_dispatch(project_root, work_order_id, reason):
        pass
        
    monkeypatch.setattr("app.runners.session_lifecycle.reject_pending_dispatch", _mock_reject_pending_dispatch)
    
    response = client.post(f"/api/v1/projects/{slug}/dispatches/wo-123/reject", json={"reason": "Incorrect scope"})
    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
