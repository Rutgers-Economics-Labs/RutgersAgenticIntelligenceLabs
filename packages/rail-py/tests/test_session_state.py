from rail.session_state import (
    is_active_status,
    is_terminal_status,
    normalize_session_record,
    normalize_session_status,
)


def test_normalize_session_status_maps_done_to_completed():
    assert normalize_session_status("done") == "completed"


def test_is_active_and_terminal():
    assert is_active_status("running")
    assert not is_terminal_status("running")
    assert is_terminal_status("completed")
    assert not is_active_status("completed")


def test_normalize_session_record():
    assert normalize_session_record({"status": "done"})["status"] == "completed"
