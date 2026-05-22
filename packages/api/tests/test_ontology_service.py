from pathlib import Path

from app.services import ontology_service


def test_ensure_loaded_reloads_when_same_db_path_changes(tmp_path, monkeypatch):
    db_path = tmp_path / "onto.db"
    db_path.write_text("v1")

    loaded = []

    def fake_load_locked(st, path):
        stat = Path(path).stat()
        loaded.append((path, stat.st_mtime_ns, stat.st_size))
        st.db_path = str(path)
        st.db_mtime_ns = stat.st_mtime_ns
        st.db_size = stat.st_size
        st.world = object()
        st.onto = object()

    monkeypatch.setattr(ontology_service, "_load_locked", fake_load_locked)
    ontology_service._states_by_id.clear()
    ontology_service._states_by_path.clear()

    ontology_service.ensure_loaded(db_path, project_id="soccer")
    assert len(loaded) == 1

    ontology_service.ensure_loaded(db_path, project_id="soccer")
    assert len(loaded) == 1

    db_path.write_text("v2 with more bytes")
    ontology_service.ensure_loaded(db_path, project_id="soccer")
    assert len(loaded) == 2
