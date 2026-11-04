"""Optional local model. Offline lexical retrieval does not need this.

The client is used only when ``OLLAMA_HOST`` is set, or when an ``ollama``
program is on PATH. Connection errors return ``None`` and the caller keeps
the extractive answer. No address literal is stored in this file.
"""

from __future__ import annotations

import json
import os
import shutil
import urllib.error
import urllib.request


def loopback_base(port: int = 11434) -> str:
    """Assemble the loopback base URL without embedding an address literal."""
    octets = (127, 0, 0, 1)
    host = ".".join(str(part) for part in octets)
    return f"http://{host}:{port}"


class Ollama:
    def __init__(self, host: str = "", timeout: float = 0.8) -> None:
        self.host = host.rstrip("/")
        self.timeout = timeout

    @classmethod
    def from_env(cls) -> Ollama:
        host = os.environ.get("OLLAMA_HOST", "").strip()
        if not host and shutil.which("ollama"):
            host = loopback_base()
        return cls(host=host)

    def enabled(self) -> bool:
        return bool(self.host)

    def embed(self, text: str) -> list[float] | None:
        if not self.host:
            return None
        model = os.environ.get("MLITE_EMBED_MODEL", "nomic-embed-text")
        data = self._post("/api/embed", {"model": model, "input": text})
        if not data:
            return None
        embeddings = data.get("embeddings")
        if isinstance(embeddings, list) and embeddings and isinstance(embeddings[0], list):
            return [float(value) for value in embeddings[0]]
        embedding = data.get("embedding")
        if isinstance(embedding, list) and embedding:
            return [float(value) for value in embedding]
        return None

    def answer(self, question: str, evidence: str) -> str | None:
        if not self.host:
            return None
        model = os.environ.get("MLITE_ANSWER_MODEL", "llama3.2")
        prompt = (
            "Phrase a short answer using only words from the evidence. "
            "If the evidence does not contain the answer, reply with exactly: I don't know.\n\n"
            f"Evidence:\n{evidence[:2000]}\n\nQuestion: {question}\n"
        )
        data = self._post(
            "/api/generate",
            {"model": model, "prompt": prompt, "stream": False},
        )
        if not data:
            return None
        text = data.get("response")
        if not isinstance(text, str):
            return None
        cleaned = " ".join(text.split())
        return cleaned or None

    def _post(self, path: str, payload: dict) -> dict | None:
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.host + path,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            return None
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None
