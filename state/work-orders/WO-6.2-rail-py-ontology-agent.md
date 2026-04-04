# WO-6.2 — rail-py OntologyView + AgentClient

**Status:** blocked  
**Spec:** `specs/rail-py.md`  
**Depends on:** WO-6.1  
**Blocks:** nothing  

---

## Goal

Add `OntologyView` (owlready2 wrapper for graph traversal) and `AgentClient` (SSE streaming wrapper for the research agent), and expose them from `Project`.

---

## Files

| File | Action | Notes |
|------|--------|-------|
| `packages/rail-py/rail/ontology.py` | **Create** | `OntologyView` wrapping owlready2 |
| `packages/rail-py/rail/agent.py` | **Create** | `AgentClient` with `ask()` |
| `packages/rail-py/rail/project.py` | **Modify** | Add `.ontology()` and `.agent` properties |
| `packages/rail-py/README.md` | **Create** | Usage examples |

---

## Steps

### 1. Create `rail/ontology.py` — OntologyView

```python
from pathlib import Path

class OntologyView:
    """Thin wrapper around owlready2 World for local ontology access."""
    
    def __init__(self, onto_db_path: str):
        try:
            from owlready2 import World
        except ImportError:
            raise ImportError("owlready2 required: pip install 'rail[local]'")
        
        self._world = World(filename=onto_db_path)
        self._onto = list(self._world.ontologies.values())[0]
    
    def classes(self) -> list[str]:
        """List all OWL class names."""
        return [cls.name for cls in self._onto.classes()]
    
    def individuals(self, class_name: str) -> list:
        """List all individuals of a class."""
        cls = self._onto[class_name]
        if cls is None:
            raise ValueError(f"Class not found: {class_name}")
        return list(cls.instances())
    
    def get(self, uri: str):
        """Get an individual by URI fragment."""
        return self._world.search_one(iri=f"*{uri}")
    
    def search(self, q: str) -> list:
        """Search individuals by hasName property."""
        results = []
        for ind in self._onto.individuals():
            name = getattr(ind, "hasName", [])
            if name and q.lower() in str(name[0]).lower():
                results.append(ind)
        return results[:50]
    
    def neighbors(self, individual, depth: int = 1) -> dict:
        """Return a neighborhood subgraph around an individual."""
        visited = set()
        nodes = []
        edges = []
        
        def traverse(ind, d):
            if ind in visited or d < 0:
                return
            visited.add(ind)
            nodes.append({"iri": ind.iri, "name": getattr(ind, "hasName", [ind.name])[0]})
            for prop in ind.get_properties():
                for val in prop[ind]:
                    if hasattr(val, "iri"):
                        edges.append({"source": ind.iri, "target": val.iri, "property": prop.name})
                        traverse(val, d - 1)
        
        traverse(individual, depth)
        return {"nodes": nodes, "edges": edges}
    
    def sparql(self, query: str) -> list:
        """Run a SPARQL query against the ontology."""
        return list(self._world.sparql(query))
```

### 2. Create `rail/agent.py` — AgentClient

Supports both blocking and streaming modes.

```python
import json
import httpx
from typing import Generator, AsyncGenerator

class AgentClient:
    def __init__(self, base_url: str, project_slug: str, api_key: str = ""):
        self.base_url = base_url.rstrip("/")
        self.project_slug = project_slug
        self.headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    
    def ask(self, question: str, stream: bool = False, model: str | None = None):
        """Ask a question. Returns full answer text (stream=False) or event generator (stream=True)."""
        if stream:
            return self._stream(question, model)
        else:
            return self._blocking(question, model)
    
    def _blocking(self, question: str, model: str | None) -> str:
        """Collect all text_delta events and return the full answer."""
        text = []
        for event in self._stream(question, model):
            if event.get("type") == "text_delta":
                text.append(event.get("text", ""))
        return "".join(text)
    
    def _stream(self, question: str, model: str | None) -> Generator[dict, None, None]:
        """Yield raw SSE event dicts."""
        url = f"{self.base_url}/agent/chat?project={self.project_slug}"
        payload = {"message": question, "history": []}
        if model:
            payload["model"] = model
        
        with httpx.Client(timeout=300) as client:
            with client.stream("POST", url, json=payload, headers=self.headers) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if line.startswith("data: "):
                        try:
                            event = json.loads(line[6:])
                            yield event
                        except json.JSONDecodeError:
                            pass
    
    async def ask_async(self, question: str, model: str | None = None) -> AsyncGenerator[dict, None]:
        """Async streaming version."""
        url = f"{self.base_url}/agent/chat?project={self.project_slug}"
        payload = {"message": question, "history": []}
        if model:
            payload["model"] = model
        
        async with httpx.AsyncClient(timeout=300) as client:
            async with client.stream("POST", url, json=payload, headers=self.headers) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        try:
                            yield json.loads(line[6:])
                        except json.JSONDecodeError:
                            pass
```

### 3. Update `rail/project.py`

```python
@property
def agent(self) -> "AgentClient":
    """Access the research agent for this project."""
    from rail.agent import AgentClient
    if not hasattr(self._backend, "base_url"):
        raise RuntimeError("Agent access requires cloud mode (rail.connect())")
    return AgentClient(
        base_url=self._backend.base_url,
        project_slug=self.slug,
        api_key=getattr(self._backend, "api_key", ""),
    )

def ontology(self) -> "OntologyView":
    """Access the owlready2 ontology directly (local mode or local onto.db path)."""
    from rail.ontology import OntologyView
    if hasattr(self._backend, "project_path"):
        # Local mode
        db_path = str(self._backend.project_path / "ontology/onto.db")
    else:
        raise RuntimeError("ontology() requires local mode or a local onto.db path")
    return OntologyView(db_path)
```

### 4. Create `packages/rail-py/README.md`

Usage examples:

```python
import rail

# Cloud mode
project = rail.connect("nj-economics")

# DataFrame queries
df = project.query("SELECT county_name, unemployment_rate FROM County ORDER BY unemployment_rate DESC LIMIT 10")

# Agent research
answer = project.agent.ask("What counties had unemployment above 10% in 2020?")
print(answer)

# Streaming agent
for event in project.agent.ask("Compare Hudson and Bergen County unemployment trends", stream=True):
    if event["type"] == "text_delta":
        print(event["text"], end="", flush=True)

# Local mode
project = rail.local("./nj-economics")
ont = project.ontology()
counties = ont.individuals("County")
print(f"Loaded {len(counties)} counties")
```

---

## Acceptance

- [ ] `project.agent.ask("What is the unemployment rate?")` returns a text answer string
- [ ] `project.agent.ask(..., stream=True)` yields SSE event dicts
- [ ] `project.ontology().classes()` returns OWL class names in local mode
- [ ] `project.ontology().individuals("County")` returns owlready2 individual objects
- [ ] `project.ontology().neighbors(ind, depth=1)` returns a subgraph dict
- [ ] `README.md` has working examples that can be pasted into a notebook
