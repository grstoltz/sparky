import json

from fastapi.testclient import TestClient

import sparky.server as server
from sparky.agent import SessionPool
from sparky.modes import get_mode

Q = "Why is Program Q's melt rate so much higher than Program S's this term?"


class FakeSession:
    def __init__(self, mode="arm3", events=None, hang=False):
        self.mode = get_mode(mode)
        self._events = events or [{"type": "text", "text": "hi"}, {"type": "done"}]
        self._hang = hang

    async def connect(self):
        pass

    async def ask(self, text):
        if self._hang:
            import asyncio
            await asyncio.sleep(60)
        for ev in self._events:
            yield ev

    async def close(self):
        pass


def _client(monkeypatch, factory=FakeSession, **settings):
    server.sessions.clear()
    server.pools.clear()
    monkeypatch.setattr(server, "get_pool", lambda mode: SessionPool(factory=lambda: factory(mode)))
    for k, v in settings.items():
        monkeypatch.setattr(server.settings, k, v)
    return TestClient(server.app)


def _events(resp):
    out = []
    for line in resp.text.splitlines():
        if line.startswith("data:"):
            out.append(json.loads(line[5:]))
    return out


def test_session_event_carries_type_so_ui_can_store_id(monkeypatch):
    with _client(monkeypatch) as c:
        evs = _events(c.post("/chat", json={"message": "x"}))
    assert evs[0]["type"] == "session" and evs[0]["session_id"]


def test_session_event_reports_whether_server_session_was_resumed(monkeypatch):
    """The UI continues stored chats after a reload; a restarted server means a fresh agent."""
    with _client(monkeypatch) as c:
        fresh = _events(c.post("/chat", json={"message": "x", "mode": "arm2"}))[0]
        assert fresh["resumed"] is False
        stale = _events(c.post("/chat", json={"message": "x", "mode": "arm2", "session_id": "gone"}))[0]
        assert stale["session_id"] == "gone" and stale["resumed"] is False
        again = _events(c.post("/chat", json={"message": "x", "mode": "arm2", "session_id": "gone"}))[0]
        assert again["resumed"] is True


def test_modes_endpoint_lists_three_arms(monkeypatch):
    with _client(monkeypatch) as c:
        body = c.get("/modes").json()
    assert [m["id"] for m in body["modes"]] == ["arm1", "arm2", "arm3"]


def test_unknown_mode_is_400_and_mode_switch_on_same_session_is_409(monkeypatch):
    with _client(monkeypatch) as c:
        assert c.post("/chat", json={"message": "x", "mode": "arm9"}).status_code == 400
        first = _events(c.post("/chat", json={"message": "x", "mode": "arm2"}))[0]
        again = c.post("/chat", json={"message": "x", "mode": "arm3", "session_id": first["session_id"]})
        assert again.status_code == 409


def test_mock_mode_replays_recorded_transcript_without_a_session(monkeypatch):
    with _client(monkeypatch) as c:
        evs = _events(c.post("/chat", json={"message": Q, "mode": "arm3", "mock": True}))
    kinds = [e["type"] for e in evs]
    assert "replay" in kinds and "cite" in kinds and kinds[-1] == "done"


def test_mock_without_transcript_reports_error(monkeypatch):
    with _client(monkeypatch) as c:
        evs = _events(c.post("/chat", json={"message": "no recording", "mode": "arm3", "mock": True}))
    assert evs[-2]["type"] == "error" and evs[-1]["type"] == "done"


def test_live_error_falls_back_to_transcript(monkeypatch):
    broken = lambda mode: FakeSession(mode, events=[{"type": "error", "message": "boom"}, {"type": "done"}])
    with _client(monkeypatch, factory=broken) as c:
        evs = _events(c.post("/chat", json={"message": Q, "mode": "arm2"}))
    kinds = [e["type"] for e in evs]
    assert "replay" in kinds and "error" not in kinds


def test_live_hang_falls_back_to_transcript(monkeypatch):
    hung = lambda mode: FakeSession(mode, hang=True)
    with _client(monkeypatch, factory=hung, live_timeout_s=0.05) as c:
        evs = _events(c.post("/chat", json={"message": Q, "mode": "arm1"}))
    assert "replay" in [e["type"] for e in evs]


def test_live_hang_without_transcript_surfaces_error(monkeypatch):
    hung = lambda mode: FakeSession(mode, hang=True)
    with _client(monkeypatch, factory=hung, live_timeout_s=0.05) as c:
        evs = _events(c.post("/chat", json={"message": "unrecorded", "mode": "arm1"}))
    assert any(e["type"] == "error" for e in evs) and evs[-1]["type"] == "done"


EMPLID = "1234567890"
LEAKY = [
    {"type": "tool_use", "id": "t1", "name": "mcp__dbt__execute_sql", "input": {"sql": f"... {EMPLID}"}},
    {"type": "result_table", "key": "k", "metrics": ["n"], "columns": ["emplid", "program", "n"],
     "rows": [{"emplid": EMPLID, "program": "Nursing", "n": 2}], "group_by": []},
    {"type": "text_delta", "text": "Student 12345"}, {"type": "text_delta", "text": "67890 is enrolled."},
    {"type": "text", "text": f"Student {EMPLID} (a@asu.edu) is enrolled."},
    {"type": "done"},
]


def test_live_answers_never_carry_ids_or_contact_details(monkeypatch):
    leaky = lambda mode: FakeSession(mode, events=LEAKY)
    with _client(monkeypatch, factory=leaky) as c:
        resp = c.post("/chat", json={"message": "x", "mode": "arm1"})
    assert EMPLID not in resp.text and "a@asu.edu" not in resp.text
    evs = _events(resp)
    card = next(e for e in evs if e["type"] == "result_table")
    assert card["columns"] == ["program", "n"] and card["rows"] == [{"program": "Nursing", "n": 2}]
    assert "".join(e["text"] for e in evs if e["type"] == "text_delta") == "Student [redacted] is enrolled."
    assert "input" not in next(e for e in evs if e["type"] == "tool_use") and evs[-1]["type"] == "done"


def test_replayed_transcripts_are_scrubbed_too(monkeypatch, tmp_path):
    path = tmp_path / "t.yaml"
    path.write_text(json.dumps({"arm3": [{"question": "who", "events": LEAKY}]}))  # JSON is valid YAML
    with _client(monkeypatch, transcripts_path=path) as c:
        resp = c.post("/chat", json={"message": "who", "mode": "arm3", "mock": True})
    assert "replay" in resp.text and EMPLID not in resp.text and "a@asu.edu" not in resp.text
