from fastapi import APIRouter, UploadFile, File, HTTPException
from app.services.storage_service import storage

router = APIRouter(prefix="/storage", tags=["storage"])


@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """
    Upload a file to the storage backend.
    Returns the storage key that can be used in API configs.
    """
    try:
        content = await file.read()
        storage_key = await storage.upload_input(file.filename, content)
        return {
            "filename": file.filename,
            "storageKey": storage_key,
            "size": len(content)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
