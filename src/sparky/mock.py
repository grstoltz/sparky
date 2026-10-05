"""MOCK_MODE: replay recorded demo transcripts (keyed by arm + question) with a simulated stream.

Used when SPARKY_MOCK_MODE=1, when a request carries ?mock=1, or automatically when a live call
fails or hangs and a transcript exists for that arm + question.
"""
import asyncio
import re
from pathlib import Path
from typing import Any, AsyncIterator

import yaml


def normalize(question: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", question.lower())).strip()


def load_transcripts(path: Path | str) -> dict[str, list[dict[str, Any]]]:
    p = Path(path)
    if not p.exists():
        return {}
    return yaml.safe_load(p.read_text()) or {}


def find_transcript(transcripts: dict[str, Any], arm: str, question: str) -> list[dict[str, Any]] | None:
    want = normalize(question)
    for entry in transcripts.get(arm) or []:
        if normalize(entry["question"]) == want:
            return entry["events"]
    return None


async def replay(events: list[dict[str, Any]], delay: float = 0.03) -> AsyncIterator[dict[str, Any]]:
    """Yield recorded events; text is re-streamed word by word so it looks live."""
    yield {"type": "replay"}
    for ev in events:
        if ev["type"] == "text":
            words = ev["text"].split(" ")
            for i in range(0, len(words), 3):
                await asyncio.sleep(delay)
                yield {"type": "text_delta", "text": " ".join(words[i:i + 3]) + (" " if i + 3 < len(words) else "")}
            yield ev
        else:
            await asyncio.sleep(delay * 8 if ev["type"] == "tool_use" else delay)
            yield ev
    yield {"type": "done"}
