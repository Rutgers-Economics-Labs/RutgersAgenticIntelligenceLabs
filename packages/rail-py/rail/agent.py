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
