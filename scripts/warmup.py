"""Run each arm's demo question once, off-camera, right before presenting.

Cold MCP/API connections are the usual source of dead air. This connects each arm, runs the exact
demo question, and reports timing so you can see every arm is healthy.

    set -a; source .env; set +a
    .venv/bin/python scripts/warmup.py [--arms arm1,arm2,arm3] [--question "..."]
"""
import argparse
import asyncio
import time

from sparky.agent import Session

DEMO_QUESTION = "Why is Program Q's melt rate so much higher than Program S's this term?"


async def warm(arm: str, question: str) -> None:
    t0 = time.time()
    session = Session(mode=arm)
    seen: list[str] = []
    answer = ""
    try:
        async for ev in session.ask(question):
            t = ev["type"]
            if t == "clarify":
                session.broker.answer(ev["id"], ev["options"][0])
            elif t in ("tool_use", "cite", "result_table"):
                seen.append(ev.get("name", t).replace("mcp__", ""))
            elif t == "text":
                answer = ev["text"]
            elif t == "error":
                print(f"{arm}: ERROR {ev['message']}")
    finally:
        await session.close()
    print(f"{arm}: {time.time() - t0:5.1f}s  steps={seen}")
    print(f"       answer: {answer[:160]!r}")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms", default="arm1,arm2,arm3")
    ap.add_argument("--question", default=DEMO_QUESTION)
    a = ap.parse_args()
    for arm in a.arms.split(","):
        await warm(arm.strip(), a.question)


if __name__ == "__main__":
    asyncio.run(main())
