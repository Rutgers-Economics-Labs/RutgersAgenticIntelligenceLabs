from __future__ import annotations
from pydantic import BaseModel
from typing import List, Optional, Any

class ZenProject(BaseModel):
    name: str
    slug: str
    phase: str
    health: str

class ZenActiveRun(BaseModel):
    id: str
    label: str
    role: str
    runner: str
    status: str
    elapsedSeconds: int
    lastEvent: Optional[str] = None
    outputsCreated: List[str] = []
    needsInput: bool = False

class ZenTruth(BaseModel):
    claim: str
    confidence: float
    evidenceRefs: List[str]
    verified: bool

class ZenDecision(BaseModel):
    type: str
    prompt: str
    recommendedAction: Optional[str] = None
    actions: List[dict] = []
    id: Optional[str] = None
    severity: Optional[str] = None
    source: Optional[str] = None

class ZenPlan(BaseModel):
    now: List[str]
    next: List[str]
    later: List[str]
    done: List[str]

class ZenAttention(BaseModel):
    severity: str # 'info', 'warning', 'error'
    title: str
    detail: str
    action: Optional[dict] = None

class ZenArtifact(BaseModel):
    name: str
    path: str
    freshness: str
    verified: bool

class ZenResponse(BaseModel):
    project: ZenProject
    objective: str
    activeRun: Optional[ZenActiveRun] = None
    latestTruth: List[ZenTruth] = []
    nextDecision: Optional[ZenDecision] = None
    plan: ZenPlan
    attention: List[ZenAttention] = []
    artifacts: List[ZenArtifact] = []
    decisions: List[ZenDecision] = []
