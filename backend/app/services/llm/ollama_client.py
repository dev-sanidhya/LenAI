import asyncio
import json
from typing import AsyncIterator
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()

# Semaphore enforces OLLAMA_MAX_CONCURRENCY - prevents OOM under load.
# Stored per-event-loop so the Celery worker (which spins up a new loop per
# task via asyncio.new_event_loop) doesn't reuse a semaphore bound to a
# dead loop, which raises 'Future attached to a different loop'.
_semaphores: dict = {}


def _get_semaphore() -> asyncio.Semaphore:
    loop = asyncio.get_event_loop()
    sem = _semaphores.get(id(loop))
    if sem is None:
        sem = asyncio.Semaphore(settings.ollama_max_concurrency)
        _semaphores[id(loop)] = sem
    return sem


PROMPT_VERSION = "v1.0"


class OllamaClient:
    def __init__(self):
        self.base_url = settings.ollama_base_url
        self.llm_model = settings.ollama_llm_model
        self.embed_model = settings.ollama_embed_model

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError)),
    )
    async def generate(self, prompt: str, system: str = "", temperature: float = 0.1) -> str:
        """Single-shot generation with retry and concurrency control."""
        async with _get_semaphore():
            async with httpx.AsyncClient(timeout=120.0) as client:
                payload = {
                    "model": self.llm_model,
                    "prompt": prompt,
                    "system": system,
                    "stream": False,
                    "options": {"temperature": temperature, "num_predict": 2048},
                }
                logger.info("llm_generate", model=self.llm_model, prompt_len=len(prompt))
                resp = await client.post(f"{self.base_url}/api/generate", json=payload)
                resp.raise_for_status()
                data = resp.json()
                return data.get("response", "")

    async def generate_json(self, prompt: str, system: str = "", retries: int = 3) -> dict:
        """Generate and parse JSON output, retrying on parse failure."""
        for attempt in range(retries):
            raw = await self.generate(
                prompt=prompt,
                system=system + "\nYou MUST respond with valid JSON only. No markdown, no explanation.",
                temperature=0.0,
            )
            # Strip markdown code fences if model added them
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                logger.warning("json_parse_failed", attempt=attempt + 1, raw_snippet=raw[:200])
                if attempt == retries - 1:
                    raise ValueError(f"LLM returned invalid JSON after {retries} attempts: {raw[:300]}")
        return {}

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=5),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError)),
    )
    async def embed(self, text: str) -> list[float]:
        """Generate embedding vector for a single text."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{self.base_url}/api/embeddings",
                json={"model": self.embed_model, "prompt": text},
            )
            resp.raise_for_status()
            return resp.json()["embedding"]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts sequentially (Ollama doesn't support true batching)."""
        results = []
        for text in texts:
            emb = await self.embed(text)
            results.append(emb)
        return results

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self.base_url}/api/tags")
                return resp.status_code == 200
        except Exception:
            return False


_client: OllamaClient | None = None


def get_ollama_client() -> OllamaClient:
    global _client
    if _client is None:
        _client = OllamaClient()
    return _client
