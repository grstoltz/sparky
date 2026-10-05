import json

import pytest

from sparky import pii
from sparky.agent import _result_scrubber, _semantic_guard, _sql_guard

EMPLID = "1234567890"


@pytest.mark.parametrize("name", ["student", "emplid", "asuo_x__stdnt_id", "STDNT_ID", "s.emplid",
                                  "asurite_id", "student__email_addr", "first_name", "stdnt_phone_nbr",
                                  "birth_dt", "home_zip_cd"])
def test_identifier_names(name):
    assert pii.is_identifier(name)


@pytest.mark.parametrize("name", ["student__stdnt_carr_desig_cd", "asuo_enrl_wkly__stdnt_cat_pop_id",
                                  "asuo_enrl_wkly__class_section_id", "acad_plan__acad_plan_crnt_ld",
                                  "asuo_enrl_registration__crnt_lmh_state", "metric_time", "enrl_students",
                                  "column_name", "table_name"])
def test_safe_names(name):
    assert not pii.is_identifier(name)


def test_bare_student_is_only_an_identifier_as_an_entity():
    assert not pii.is_identifier("student", entities=False)


@pytest.mark.parametrize("sql", [
    "SELECT program, COUNT(DISTINCT stdnt_id) AS students FROM enrl GROUP BY program",
    "select count(*) from student.enrollment",
    "select column_name from information_schema.columns where column_name like '%emplid%'",
    "select term, sum(credit_hrs) from reg where term = '2261' group by 1",
])
def test_aggregate_sql_is_allowed(sql):
    assert pii.check_sql(sql) is None


@pytest.mark.parametrize("sql", [
    "select * from enrl",
    "select e.* from enrl e",
    "select emplid, program from enrl",
    "select program from enrl where emplid = '1234567890'",
    "select program, count(*) from enrl where id = 1234567890 group by 1",
    "select max(stdnt_id) from enrl",
    "select first_name, last_name from person",
    'select "EMPLID" from enrl',
])
def test_identifier_sql_is_refused(sql):
    assert pii.check_sql(sql)


def test_semantic_args_allow_normal_queries():
    args = {"metrics": ["enrl_students_budget"], "limit": 5,
            "group_by": [{"name": "asuo_term_session__term_season", "type": "dimension"}],
            "where": "{{ Dimension('acad_plan__acad_plan_type_sd') }} = 'Non-Degree Student'"}
    assert pii.check_semantic_args(args) is None


@pytest.mark.parametrize("args", [
    {"metrics": ["enrl_students"], "group_by": [{"name": "student", "type": "entity"}]},
    {"metrics": ["enrl_students"], "group_by": ["student"]},
    {"metrics": ["enrl_students"], "where": "{{ Entity('student') }} = '1234567890'"},
    {"metrics": ["enrl_students"], "where": "{{ Dimension('student__emplid') }} is not null"},
    {"metrics": ["enrl_students"], "order_by": [{"name": "student__first_name"}]},
    {"dimension": "student__asurite_id", "metrics": ["enrl_students"]},
])
def test_semantic_args_refuse_identifiers(args):
    assert pii.check_semantic_args(args)


def test_scrub_text_redacts_ids_and_contact_details():
    s = pii.scrub_text(f"id {EMPLID}, ssn 123-45-6789, a@asu.edu, (602) 555-1234 or 602-555-1234")
    for leak in (EMPLID, "123-45-6789", "a@asu.edu", "555-1234"):
        assert leak not in s


def test_scrub_text_leaves_numbers_dates_and_terms():
    s = "73,871 students on 2026-09-23 in term 2261; 402,925.25 credit hours (11%)"
    assert pii.scrub_text(s) == s


def test_stream_redactor_catches_an_id_split_across_deltas():
    r = pii.StreamRedactor()
    parts = ["Student 123", "4567", "890 enrolled. Email a@", "asu.edu", " today."]
    out = "".join(r.feed(p) for p in parts) + r.flush()
    assert EMPLID not in out and "a@asu.edu" not in out
    assert out.startswith("Student [redacted] enrolled.") and out.endswith(" today.")


def test_stream_redactor_passes_ordinary_text_through():
    r = pii.StreamRedactor()
    text = "Fall enrollment is 73,871, up 4% on last year. That is the highest yet."
    out = "".join(r.feed(c) for c in text) + r.flush()
    assert out == text


def test_result_table_drops_identifier_columns():
    ev = {"type": "result_table", "key": "k", "metrics": ["n"], "columns": ["emplid", "program", "n"],
          "rows": [{"emplid": EMPLID, "program": "Nursing", "n": 1}], "group_by": [{"name": "emplid"}],
          "labels": {"n": "Count"}}
    out = pii.sanitize_event(ev)
    assert out["columns"] == ["program", "n"] and out["rows"] == [{"program": "Nursing", "n": 1}]
    assert out["group_by"] == [] and out["labels"] == {"n": "Count"}
    assert EMPLID not in json.dumps(out)


def test_result_table_of_only_identifiers_is_dropped():
    ev = {"type": "result_table", "columns": ["emplid"], "rows": [{"emplid": EMPLID}], "metrics": []}
    assert pii.sanitize_event(ev) is None


def test_events_hide_tool_input_and_redact_text():
    assert "input" not in pii.sanitize_event({"type": "tool_use", "id": "t", "name": "x", "input": {"sql": "s"}})
    c = pii.sanitize_event({"type": "clarify", "question": f"Which of {EMPLID}?", "options": ["a@asu.edu", "Fall"]})
    assert EMPLID not in c["question"] and c["options"] == ["[redacted]", "Fall"]
    # The card and its SQL are paired by key, so both keys must be scrubbed identically.
    t = pii.sanitize_event({"type": "result_table", "key": f"sql:{EMPLID}", "columns": ["n"], "rows": [{"n": 1}]})
    s = pii.sanitize_event({"type": "sql", "key": f"sql:{EMPLID}", "sql": f"... {EMPLID}"})
    assert t["key"] == s["key"] and EMPLID not in t["key"] + s["sql"]


def test_event_guard_flushes_held_text_before_the_next_event():
    g = pii.EventGuard()
    out = g({"type": "text_delta", "text": "Total is 42"}) + g({"type": "done"}) + g.close()
    assert "".join(e["text"] for e in out if e["type"] == "text_delta") == "Total is 42"
    assert out[-1] == {"type": "done"}


def test_scrub_payload_cleans_json_inside_tool_text():
    body = {"schema": {"fields": [{"name": "emplid"}, {"name": "n"}]},
            "data": [{"emplid": EMPLID, "n": 3}], "sql": "select ..."}
    payload = [{"type": "text", "text": json.dumps(body)}]
    clean = pii.scrub_payload(payload)
    assert EMPLID not in json.dumps(clean)
    assert json.loads(clean[0]["text"])["data"] == [{"n": 3}]
    assert pii.scrub_payload([{"type": "text", "text": '[{"term": "Fall", "n": 3}]'}]) == \
        [{"type": "text", "text": '[{"term": "Fall", "n": 3}]'}]  # unchanged text keeps its formatting


async def test_sql_hook_denies_identifier_queries():
    deny = await _sql_guard({"tool_input": {"sql": "select emplid from enrl"}}, "t", None)
    assert deny["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "aggregate" in deny["hookSpecificOutput"]["permissionDecisionReason"]
    assert await _sql_guard({"tool_input": {"sql": "select count(distinct emplid) from enrl"}}, "t", None) == {}


async def test_semantic_hook_denies_grouping_by_student():
    deny = await _semantic_guard({"tool_input": {"metrics": ["m"], "group_by": [{"name": "student"}]}}, "t", None)
    assert deny["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert await _semantic_guard({"tool_input": {"metrics": ["m"], "group_by": ["metric_time"]}}, "t", None) == {}


async def test_result_hook_rewrites_only_when_something_leaks():
    leaky = {"tool_response": [{"type": "text", "text": json.dumps([{"emplid": EMPLID, "n": 1}])}]}
    out = await _result_scrubber(leaky, "t", None)
    spec = out["hookSpecificOutput"]
    assert spec["hookEventName"] == "PostToolUse" and EMPLID not in json.dumps(spec["updatedMCPToolOutput"])
    clean = {"tool_response": [{"type": "text", "text": json.dumps([{"term": "Fall", "n": 1}])}]}
    assert await _result_scrubber(clean, "t", None) == {}
