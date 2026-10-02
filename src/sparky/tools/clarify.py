"""Structured Socratic questions: the agent calls a tool, the UI renders options,
and the user's pick is returned as the tool result."""
import asyncio
import uuid
from typing import Any, Awaitable, Callable

from claude_agent_sdk import SdkMcpTool, create_sdk_mcp_server, tool

MAX_QUESTIONS = 3

Emit = Callable[[dict[str, Any]], Awaitable[None]]


class ClarifyBroker:
    """Bridges the blocking tool call and the HTTP /answer endpoint."""

    def __init__(self, emit: Emit):
        self._emit = emit
        self._pending: dict[str, asyncio.Future[str]] = {}

    async def ask(self, question: str, options: list[str], allow_free_text: bool) -> str:
        qid = uuid.uuid4().hex[:8]
        fut: asyncio.Future[str] = asyncio.get_running_loop().create_future()
        self._pending[qid] = fut
        await self._emit({
            "type": "clarify", "id": qid, "question": question,
            "options": options, "allow_free_text": allow_free_text,
        })
        try:
            return await fut
        finally:
            self._pending.pop(qid, None)

    def answer(self, qid: str, text: str) -> bool:
        fut = self._pending.get(qid)
        if fut is None or fut.done():
            return False
        fut.set_result(text)
        return True

    def cancel_all(self) -> None:
        for fut in self._pending.values():
            if not fut.done():
                fut.cancel()


def build_clarify_server(broker: ClarifyBroker):
    @tool(
        "ask_clarifying_question",
        "Ask the user ONE Socratic clarifying question with 2-4 concrete options built from "
        "real semantic-layer metrics/dimensions/values. Put the recommended option first. "
        "Returns the user's chosen option or free-text answer.",
        {
            "type": "object",
            "properties": {
                "question": {"type": "string"},
                "options": {"type": "array", "items": {"type": "string"}, "minItems": 2, "maxItems": 4},
                "allow_free_text": {"type": "boolean", "default": True},
            },
            "required": ["question", "options"],
        },
    )
    async def ask_clarifying_question(args: dict[str, Any]) -> dict[str, Any]:
        try:
            answer = await broker.ask(
                args["question"], list(args["options"]), bool(args.get("allow_free_text", True))
            )
        except asyncio.CancelledError:
            return {"content": [{"type": "text", "text": "User did not answer."}], "is_error": True}
        return {"content": [{"type": "text", "text": answer}]}

    tools: list[SdkMcpTool] = [ask_clarifying_question]
    return create_sdk_mcp_server(name="sparky", version="0.1.0", tools=tools)
