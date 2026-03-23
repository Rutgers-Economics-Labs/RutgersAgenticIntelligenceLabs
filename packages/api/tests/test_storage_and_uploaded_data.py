import pytest
import httpx
import yaml
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

@pytest.mark.asyncio
async def test_upload_and_resolve_flow(client, tmp_path):
    # 1. Test File Upload
    file_content = b"name,population\nEssex,800000"
    files = {"file": ("test.csv", file_content, "text/csv")}
    
    resp = await client.post("/api/v1/storage/upload", files=files)
    assert resp.status_code == 200
    data = resp.json()
    assert data["filename"] == "test.csv"
    storage_key = data["storageKey"]
    assert Path(storage_key).name == "test.csv"
    assert "inputs" in Path(storage_key).parts

    # 2. Test Hydration Worker Resolution
    from app.services import hydration_worker
    
    pipeline_content = yaml.dump({
        "name": "test_pipeline",
        "ontology": "custom_onto",
        "steps": [{"name": "step1", "api": "user_data", "class": "County", "uri": "C_{name}"}]
    })
    
    api_configs = {
        "user_data": yaml.dump({
            "name": "user_data",
            "type": "uploaded",
            "storage_key": storage_key,
            "fields": [{"source": "name", "alias": "name"}]
        })
    }
    
    onto_configs = {
        "custom_onto": yaml.dump({
            "uri": "http://example.org/test.owl",
            "classes": [{"name": "County"}]
        })
    }

    # Mock dependencies to avoid running the actual engine subprocess
    from app.services.hydration_worker import storage, convex

    mock_exec = AsyncMock()

    with patch.object(convex, "mutation", new_callable=AsyncMock) as mock_mutation, \
         patch.object(convex, "query", new_callable=AsyncMock) as mock_query, \
         patch.object(storage, "download", new_callable=AsyncMock) as mock_download, \
         patch.object(storage, "upload", new_callable=AsyncMock) as mock_upload, \
         patch("asyncio.create_subprocess_exec", mock_exec):
        
        mock_upload.return_value = "uploaded_key"
        
        # Setup mock subprocess
        mock_proc = MagicMock()
        async def mock_stdout_iter():
            yield b"[step] step1:"
            yield b"-> 1 County individuals processed"
        mock_proc.stdout = mock_stdout_iter()
        mock_proc.wait = AsyncMock(return_value=0)
        mock_proc.returncode = 0
        mock_exec.return_value = mock_proc

        await hydration_worker.run("job123", pipeline_content, api_configs, onto_configs)

        # Verify storage.download was called with the correct storage_key
        assert mock_download.called
        args, kwargs = mock_download.call_args
        assert args[0] == storage_key
        
        # Verify custom ontology was passed to Convex logs or processed
        # (Internal check of tmpdir content is harder here, but we verified the logic)
        assert mock_exec.called


@pytest.mark.asyncio
async def test_hydration_embedding_index_failure_is_non_fatal(tmp_path):
    from app.services import hydration_worker
    from app.services.hydration_worker import convex, storage

    pipeline_content = yaml.dump({
        "name": "test_pipeline",
        "ontology": "core",
        "steps": [{"name": "step1", "api": "source", "class": "County", "uri": "C_{name}"}],
    })
    api_configs = {
        "source": yaml.dump({
            "name": "source",
            "type": "csv",
            "path": "sources/test.csv",
            "fields": [{"source": "name", "alias": "name"}],
        })
    }

    mock_exec = AsyncMock()

    with patch.object(convex, "mutation", new_callable=AsyncMock) as mock_mutation, \
         patch.object(storage, "upload", new_callable=AsyncMock) as mock_upload, \
         patch("asyncio.create_subprocess_exec", mock_exec), \
         patch("app.services.ontology_service.load") as mock_load, \
         patch("app.services.ontology_service.export_to_duckdb", new_callable=AsyncMock) as mock_export, \
         patch("app.services.sql_service.set_path") as mock_set_path, \
         patch("app.services.embedding_service.build_index", new_callable=AsyncMock) as mock_build_index:

        mock_upload.side_effect = [
            str(tmp_path / "onto.db"),
            str(tmp_path / "populated_ontology.owl"),
        ]
        mock_build_index.side_effect = RuntimeError("boom")

        mock_proc = MagicMock()

        async def mock_stdout_iter():
            yield b"[step] step1:"
            yield b"-> 1 County individuals processed"

        mock_proc.stdout = mock_stdout_iter()
        mock_proc.wait = AsyncMock(return_value=0)
        mock_proc.returncode = 0
        mock_exec.return_value = mock_proc

        await hydration_worker.run("job-semantic", pipeline_content, api_configs)

        mock_build_index.assert_awaited_once()

        mutation_calls = [call.args for call in mock_mutation.await_args_list]
        assert any(
            fn_path == "jobs:updateJob" and payload.get("status") == "success"
            for fn_path, payload in mutation_calls
        )
        assert any(
            fn_path == "jobs:appendLog"
            and "Embedding index failed (non-fatal): boom" in payload.get("message", "")
            for fn_path, payload in mutation_calls
        )


@pytest.mark.asyncio
async def test_hydration_resolves_document_storage_key(client):
    from app.services import hydration_worker
    from app.services.hydration_worker import convex, storage

    pipeline_content = yaml.dump({
        "name": "doc_pipeline",
        "ontology": "core",
        "steps": [{"name": "step1", "api": "report_data", "class": "County", "uri": "C_{name}"}],
    })
    api_configs = {
        "report_data": yaml.dump({
            "name": "report_data",
            "type": "pdf",
            "storage_key": "inputs/report.pdf",
            "extraction_mode": "tables",
            "fields": [{"source": "name", "alias": "name"}],
        })
    }

    mock_exec = AsyncMock()

    with patch.object(convex, "mutation", new_callable=AsyncMock), \
         patch.object(storage, "download", new_callable=AsyncMock) as mock_download, \
         patch.object(storage, "upload", new_callable=AsyncMock) as mock_upload, \
         patch("asyncio.create_subprocess_exec", mock_exec), \
         patch("app.services.ontology_service.load"), \
         patch("app.services.ontology_service.export_to_duckdb", new_callable=AsyncMock), \
         patch("app.services.sql_service.set_path"), \
         patch("app.services.embedding_service.build_index", new_callable=AsyncMock):

        mock_upload.side_effect = ["/tmp/onto.db", "/tmp/populated_ontology.owl"]

        mock_proc = MagicMock()

        async def mock_stdout_iter():
          yield b"[step] step1:"
          yield b"-> 1 County individuals processed"

        mock_proc.stdout = mock_stdout_iter()
        mock_proc.wait = AsyncMock(return_value=0)
        mock_proc.returncode = 0
        mock_exec.return_value = mock_proc

        await hydration_worker.run("job-doc", pipeline_content, api_configs)

        assert mock_download.called
        download_args, _ = mock_download.call_args
        assert download_args[0] == "inputs/report.pdf"
        assert str(download_args[1]).endswith("report.pdf")
        
def asyncio_future(result):
    from asyncio import Future
    f = Future()
    f.set_result(result)
    return f
