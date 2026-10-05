import asyncio

from sparky.context import render_for_prompt, resolve
from sparky.tools.cite import make_cite_tool

PACK = {"metrics": {
    "enrollment_headcount": {"description": "Distinct students", "context_card": {
        "expectations": {"healthy_range": "85-92%"},
        "investigations": {"known_structural_causes": ["Fall B census trails Fall A", "Online has later census"]},
    }},
    "other": {"context_card": {"investigations": {"known_structural_causes": ["x"]}}},
}}


def test_resolve_exact_and_parent_paths():
    found, unknown = resolve(PACK, ["expectations.healthy_range"], "enrollment_headcount")
    assert found == [{"metric": "enrollment_headcount", "path": "expectations.healthy_range", "text": "85-92%"}]
    assert unknown == []
    found, _ = resolve(PACK, ["investigations"], "enrollment_headcount")
    assert [f["path"] for f in found] == ["investigations.known_structural_causes"]


def test_resolve_unknown_and_unscoped():
    found, unknown = resolve(PACK, ["nope.path"])
    assert found == [] and unknown == ["nope.path"]
    found, _ = resolve(PACK, ["investigations.known_structural_causes"])  # no metric: searches all
    assert {f["metric"] for f in found} == {"enrollment_headcount", "other"}


def test_render_lists_field_paths():
    text = render_for_prompt(PACK)
    assert "investigations.known_structural_causes: Fall B census trails Fall A; Online has later census" in text


async def test_cite_tool_emits_structured_event_not_prose():
    events = []

    async def emit(ev):
        events.append(ev)

    tool = make_cite_tool(PACK, emit)
    res = await tool.handler({"paths": ["investigations.known_structural_causes"], "metric": "enrollment_headcount"})
    assert events[0]["type"] == "cite" and events[0]["citations"][0]["metric"] == "enrollment_headcount"
    assert not res.get("is_error")
    bad = await tool.handler({"paths": ["missing.field"]})
    assert bad["is_error"] and len(events) == 1
