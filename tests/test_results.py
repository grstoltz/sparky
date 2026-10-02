import json

from claude_agent_sdk import AssistantMessage, ToolResultBlock, ToolUseBlock, UserMessage

from sparky.agent import map_message, parse_rows, query_key

ARGS = {"metrics": ["enrl_students_budget"],
        "group_by": [{"name": "asuo_term_session__term_season", "type": "dimension"}], "limit": 5}
ROWS = [{"asuo_term_session__term_season": "Fall", "enrl_students_budget": 96733.0}]


def _run(name, content):
    calls = {}
    map_message(AssistantMessage(content=[ToolUseBlock(id="t1", name=name, input=ARGS)], model="m"), calls)
    return map_message(UserMessage(content=[ToolResultBlock(tool_use_id="t1", content=content)]), calls)


def test_query_metrics_emits_table():
    evs = _run("mcp__dbt__query_metrics", json.dumps(ROWS))
    t = next(e for e in evs if e["type"] == "result_table")
    assert t["rows"] == ROWS and t["columns"] == list(ROWS[0]) and t["key"] == query_key(ARGS)


def test_wrapped_result_parses():
    assert parse_rows(json.dumps({"result": json.dumps(ROWS)})) == ROWS


def test_sql_pairs_by_key():
    evs = _run("mcp__dbt__get_metrics_compiled_sql", "SELECT 1")
    s = next(e for e in evs if e["type"] == "sql")
    assert s["key"] == query_key(ARGS) and s["sql"] == "SELECT 1"


def test_sql_unwraps_result_envelope():
    evs = _run("mcp__dbt__get_metrics_compiled_sql", json.dumps({"result": "SELECT 1"}))
    assert next(e for e in evs if e["type"] == "sql")["sql"] == "SELECT 1"
