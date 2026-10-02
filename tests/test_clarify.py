import asyncio

from sparky.agent import build_options, load_system_prompt
from sparky.config import ALLOWED_TOOLS, DISALLOWED_TOOLS, Settings
from sparky.tools.clarify import ClarifyBroker


async def test_broker_roundtrip():
    events = []

    async def emit(ev):
        events.append(ev)

    broker = ClarifyBroker(emit)
    task = asyncio.create_task(broker.ask("Which metric?", ["revenue", "orders"], True))
    await asyncio.sleep(0)
    assert events[0]["type"] == "clarify"
    assert broker.answer(events[0]["id"], "revenue")
    assert await task == "revenue"
    assert not broker.answer(events[0]["id"], "again")


def test_no_write_tools_allowed():
    for t in DISALLOWED_TOOLS:
        assert t not in ALLOWED_TOOLS
    assert "mcp__dbt__query_metrics" in ALLOWED_TOOLS


def test_options_and_prompt():
    prompt = load_system_prompt()
    assert "Socratic" in prompt and "read-only" in prompt
    opts = build_options(Settings(), ClarifyBroker(lambda e: asyncio.sleep(0)))
    assert set(opts.mcp_servers) == {"dbt", "sparky"}


def test_agent_is_isolated_from_account_connectors_and_builtins():
    opts = build_options(Settings(), ClarifyBroker(lambda e: asyncio.sleep(0)))
    assert opts.strict_mcp_config is True
    assert opts.tools == []
