import json

from fastapi.testclient import TestClient

import sparky.server as server


class FakeSession:
    async def connect(self):
        pass

    async def ask(self, text):
        yield {"type": "text", "text": "hi"}
        yield {"type": "done"}

    async def close(self):
        pass


def test_session_event_carries_type_so_ui_can_store_id(monkeypatch):
    monkeypatch.setattr(server, "pool", server.SessionPool(factory=FakeSession))
    with TestClient(server.app) as c:
        body = c.post("/chat", json={"message": "x"}).text
    first = next(l for l in body.splitlines() if l.startswith("data:"))
    ev = json.loads(first[5:])
    assert ev["type"] == "session" and ev["session_id"]
