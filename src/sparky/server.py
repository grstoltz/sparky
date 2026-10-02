import json
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from .agent import Session, SessionPool

WEB_DIR = Path(__file__).resolve().parents[2] / "web"
sessions: dict[str, Session] = {}
pool = SessionPool()


@asynccontextmanager
async def lifespan(_: FastAPI):
    pool.warm()  # connect in the background; startup is not blocked by a first-time login
    yield
    await pool.close()
    for s in sessions.values():
        await s.close()


app = FastAPI(title="Sparky", lifespan=lifespan)
app.mount("/assets", StaticFiles(directory=WEB_DIR / "assets"), name="assets")


class ChatIn(BaseModel):
    session_id: str | None = None
    message: str


class AnswerIn(BaseModel):
    session_id: str
    question_id: str
    answer: str


@app.get("/health")
async def health():
    return {"ok": True}


@app.post("/warm")
async def warm():
    pool.warm()
    return {"ok": True}


@app.post("/chat")
async def chat(body: ChatIn):
    sid = body.session_id or uuid.uuid4().hex
    session = sessions.get(sid)
    if session is None:
        session = sessions[sid] = await pool.take()

    async def stream():
        yield {"event": "session", "data": json.dumps({"type": "session", "session_id": sid})}
        async for ev in session.ask(body.message):
            yield {"event": ev["type"], "data": json.dumps(ev)}

    return EventSourceResponse(stream())


@app.post("/answer")
async def answer(body: AnswerIn):
    session = sessions.get(body.session_id)
    if session is None or not session.broker.answer(body.question_id, body.answer):
        raise HTTPException(404, "No pending question")
    return {"ok": True}


@app.get("/")
async def index():
    return FileResponse(WEB_DIR / "index.html")
