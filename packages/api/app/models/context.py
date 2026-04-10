import uuid
from typing import List, Optional
from pydantic import BaseModel, Field

class ContextManifest(BaseModel):
    classes: List[str] = Field(default_factory=list, description="List of relevant ontology classes.")
    iris: List[str] = Field(default_factory=list, description="List of specific IRIs required.")
    filters: List[str] = Field(default_factory=list, description="List of filter conditions.")

class StructuredContextBundle(BaseModel):
    manifest_id: uuid.UUID = Field(default_factory=uuid.uuid4, description="Unique identifier for this bundle.")
    ontology_ddl: str = Field(..., description="SQL DDL needed to recreate the relevant sub-schema.")
    entities: List[str] = Field(default_factory=list, description="List of pinned IRIs for high-precision context.")
    document_ids: List[str] = Field(default_factory=list, description="Context document snippets.")
