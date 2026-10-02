"""One Agent SDK session per conversation, exposed as an async stream of UI events."""
import asyncio
import json
from pathlib import Path
from typing import Any, AsyncIterator

from claude_agent_sdk import (
    AssistantMessage, ClaudeAgentOptions, ClaudeSDKClient, ResultMessage, StreamEvent,
    TextBlock, ToolResultBlock, ToolUseBlock, UserMessage,
)

from .config import ALLOWED_TOOLS, DBT_TOOLS, DISALLOWED_TOOLS, Settings
from .tools.clarify import ClarifyBroker, build_clarify_server

RULES_DIR = Path(__file__).parent / "rules"


def load_system_prompt() -> str:
    return "\n\n".join(p.read_text() for p in sorted(RULES_DIR.glob("*.md")))


def dbt_mcp_config(s: Settings) -> dict[str, Any]:
    env = {
        "DBT_HOST": s.dbt_host,
        # Expose only the semantic-layer tools. Fewer tool schemas means far fewer tokens on every
        # model turn, and it keeps admin/SQL/CLI tools out of reach (config.py allow-list is the guard).
        "DBT_MCP_ENABLE_TOOLS": ",".join(DBT_TOOLS),
    }
    if s.dbt_account_prefix:
        env["MULTICELL_ACCOUNT_PREFIX"] = s.dbt_account_prefix
    if not s.use_oauth:
        # Service-token auth. With OAuth, dbt-mcp opens a browser and the user picks the project.
        env["DBT_TOKEN"] = s.dbt_token
        env["DBT_PROD_ENV_ID"] = s.dbt_prod_env_id
    return {"type": "stdio", "command": "uvx", "args": ["dbt-mcp"], "env": env}


def build_options(s: Settings, broker: ClarifyBroker) -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        system_prompt=load_system_prompt(),
        mcp_servers={"dbt": dbt_mcp_config(s), "sparky": build_clarify_server(broker)},
        # Only the servers above: ignore claude.ai account connectors (Gmail, Drive, ...) that the
        # CLI would otherwise load, and drop all built-in tools (Bash, Edit, ...). Both shrink the
        # per-turn prompt a lot and keep unrelated tools out of the agent's reach.
        include_partial_messages=True,  # stream text deltas to the UI as the model writes
        strict_mcp_config=True,
        tools=[],
        allowed_tools=ALLOWED_TOOLS,
        disallowed_tools=DISALLOWED_TOOLS,
        permission_mode="default",
        max_turns=s.max_turns,
        model=s.model,
        setting_sources=[],  # don't inherit user/project Claude Code settings
        # Load the (small, allow-listed) MCP tool schemas up front instead of spending a
        # model turn on ToolSearch to discover them.
        env={"ENABLE_TOOL_SEARCH": "false"},
    )


class Session:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings()
        self.events: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.broker = ClarifyBroker(self.events.put)
        self.client = ClaudeSDKClient(build_options(self.settings, self.broker))
        self._connected = False
        self._lock = asyncio.Lock()
        self._calls: dict[str, tuple[str, dict[str, Any]]] = {}

    async def connect(self) -> None:
        """Start the CLI and dbt-mcp processes. Idempotent; safe to call ahead of the first question."""
        if not self._connected:
            await self.client.connect()
            self._connected = True

    async def _run_turn(self, text: str) -> None:
        try:
            await self.connect()
            await self.client.query(text)
            async for msg in self.client.receive_response():
                for ev in map_message(msg, self._calls):
                    await self.events.put(ev)
        except Exception as e:  # surface to the UI instead of hanging the stream
            await self.events.put({"type": "error", "message": str(e)})
        finally:
            await self.events.put({"type": "done"})

    async def ask(self, text: str) -> AsyncIterator[dict[str, Any]]:
        async with self._lock:
            task = asyncio.create_task(self._run_turn(text))
            try:
                while True:
                    ev = await self.events.get()
                    yield ev
                    if ev["type"] == "done":
                        break
            finally:
                if not task.done():
                    self.broker.cancel_all()
                    task.cancel()

    async def close(self) -> None:
        self.broker.cancel_all()
        if self._connected:
            await self.client.disconnect()


class SessionPool:
    """Keeps one connected Session ready so a new chat skips the CLI + dbt-mcp cold start."""

    def __init__(self, factory=Session):
        self._factory = factory
        self._warm: asyncio.Task[Session] | None = None

    async def _spawn(self) -> Session:
        session = self._factory()
        await session.connect()
        return session

    def warm(self) -> None:
        """Ensure a warm session is being prepared (no-op if one already is)."""
        if self._warm is None:
            self._warm = asyncio.create_task(self._spawn())

    async def take(self) -> Session:
        """Hand out the warm session and start preparing the next one."""
        task, self._warm = self._warm, None
        self.warm()
        if task is not None:
            try:
                return await task
            except Exception:  # warm-up failed (e.g. login pending): fall back to a cold session
                pass
        return self._factory()

    async def close(self) -> None:
        task, self._warm = self._warm, None
        if task is not None:
            try:
                await (await task).close()
            except Exception:
                pass


def query_key(args: dict[str, Any]) -> str:
    """Stable id shared by a query_metrics call and its get_metrics_compiled_sql twin."""
    keep = {k: args.get(k) for k in ("metrics", "group_by", "where", "order_by", "limit")}
    return json.dumps(keep, sort_keys=True, default=str)


def _result_text(block: ToolResultBlock) -> str:
    c = block.content
    if isinstance(c, str):
        return c
    return "".join(x.get("text", "") for x in (c or []) if isinstance(x, dict))


def unwrap_text(text: str) -> str:
    """Tools return either the bare value or {"result": "<value>"}."""
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return text
    if isinstance(data, dict) and isinstance(data.get("result"), str):
        return data["result"]
    return text


def parse_rows(text: str) -> list[dict[str, Any]] | None:
    """query_metrics returns a JSON array of row objects (sometimes wrapped as {"result": ...})."""
    try:
        data = json.loads(text)
        if isinstance(data, dict) and "result" in data:
            data = data["result"]
            if isinstance(data, str):
                data = json.loads(data)
    except (ValueError, TypeError):
        return None
    if isinstance(data, list) and all(isinstance(r, dict) for r in data):
        return data
    return None


def map_message(msg: Any, calls: dict[str, tuple[str, dict[str, Any]]] | None = None) -> list[dict[str, Any]]:
    calls = calls if calls is not None else {}
    out: list[dict[str, Any]] = []
    if isinstance(msg, StreamEvent):
        ev = msg.event or {}
        delta = ev.get("delta") or {}
        if (ev.get("type") == "content_block_delta" and delta.get("type") == "text_delta"
                and not msg.parent_tool_use_id and delta.get("text")):
            out.append({"type": "text_delta", "text": delta["text"]})
    elif isinstance(msg, AssistantMessage):
        for b in msg.content:
            if isinstance(b, TextBlock) and b.text.strip():
                out.append({"type": "text", "text": b.text})
            elif isinstance(b, ToolUseBlock):
                calls[b.id] = (b.name, b.input)
                out.append({"type": "tool_use", "id": b.id, "name": b.name, "input": b.input})
    elif isinstance(msg, UserMessage) and isinstance(msg.content, list):
        for b in msg.content:
            if not isinstance(b, ToolResultBlock):
                continue
            out.append({"type": "tool_result", "id": b.tool_use_id, "is_error": bool(b.is_error)})
            name, args = calls.get(b.tool_use_id, ("", {}))
            if b.is_error:
                continue
            if name.endswith("query_metrics"):
                rows = parse_rows(_result_text(b))
                if rows is not None:
                    out.append({
                        "type": "result_table", "key": query_key(args), "id": b.tool_use_id,
                        "metrics": args.get("metrics", []), "rows": rows,
                        "columns": list(rows[0].keys()) if rows else [],
                        "group_by": args.get("group_by") or [],
                    })
            elif name.endswith("get_metrics_compiled_sql"):
                out.append({"type": "sql", "key": query_key(args), "sql": unwrap_text(_result_text(b))})
    elif isinstance(msg, ResultMessage):
        out.append({
            "type": "result", "cost_usd": msg.total_cost_usd, "num_turns": msg.num_turns,
            "duration_ms": msg.duration_ms, "duration_api_ms": msg.duration_api_ms,
            "usage": msg.usage,
        })
    return out
