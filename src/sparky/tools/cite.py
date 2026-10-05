"""cite_context: the model reports which context-card fields changed its conclusion.

Rendered by the UI as a chip under the answer (structured metadata, never narrated in prose).
"""
from typing import Any

from claude_agent_sdk import SdkMcpTool, tool

from ..context import resolve
from .clarify import Emit


def make_cite_tool(pack: dict[str, Any], emit: Emit) -> SdkMcpTool:
    @tool(
        "cite_context",
        "Record which business context-card fields changed your conclusion. Call it in the same "
        "message as your answer, with field paths like `investigations.known_structural_causes`. "
        "Never mention it in prose.",
        {
            "type": "object",
            "properties": {
                "paths": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                "metric": {"type": "string", "description": "Metric name, if several cards define the same path"},
            },
            "required": ["paths"],
        },
    )
    async def cite_context(args: dict[str, Any]) -> dict[str, Any]:
        found, unknown = resolve(pack, list(args["paths"]), args.get("metric"))
        if found:
            await emit({"type": "cite", "citations": found})
        if unknown and not found:
            return {"content": [{"type": "text", "text": f"Unknown context paths: {unknown}"}], "is_error": True}
        note = f" (unknown, ignored: {unknown})" if unknown else ""
        return {"content": [{"type": "text", "text": f"Cited {len(found)} context field(s){note}."}]}

    return cite_context
