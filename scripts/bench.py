"""Benchmark Sparky end to end against the real dbt project.

    set -a; source .env; set +a
    .venv/bin/python scripts/bench.py [--out bench.json] [--only 0,2]

Each question runs in a fresh session except the follow-up, which reuses the previous
session. Clarifying questions are auto-answered with their first option.
"""
import argparse
import asyncio
import json
import time

from sparky.agent import Session, SessionPool

QUESTIONS = [
    ("specified", "How many budget-basis enrolled students were there at census by term season?", False),
    ("vague", "how are we doing?", False),
    ("grouped", "how many students are enrolled by term season?", False),
    ("filtered", "enrolled students for Fall 2026 by student career", False),
    ("followup", "now break that out by residency", True),
    ("no_match", "what was our football ticket revenue last year?", False),
]


async def run(session: Session, text: str) -> dict:
    t0 = time.time()
    first = None
    first_text = None
    tools: list[str] = []
    clarifies = 0
    rec: dict = {"question": text, "error": None, "tables": 0, "sql": 0}
    async for ev in session.ask(text):
        now = time.time() - t0
        if first is None:
            first = now
        t = ev["type"]
        if t in ("text", "text_delta") and first_text is None:
            first_text = now
        if t == "tool_use":
            tools.append(ev["name"].replace("mcp__", ""))
        elif t == "clarify":
            clarifies += 1
            session.broker.answer(ev["id"], ev["options"][0])
        elif t == "result_table":
            rec["tables"] += 1
        elif t == "sql":
            rec["sql"] += 1
        elif t == "result":
            u = ev.get("usage") or {}
            rec.update(
                cost_usd=ev["cost_usd"], turns=ev["num_turns"], api_ms=ev["duration_api_ms"],
                input_tokens=u.get("input_tokens"), output_tokens=u.get("output_tokens"),
                cache_read=u.get("cache_read_input_tokens"), cache_write=u.get("cache_creation_input_tokens"),
            )
        elif t == "error":
            rec["error"] = ev["message"]
    rec.update(wall_s=round(time.time() - t0, 1), first_event_s=round(first or 0, 1),
               first_text_s=round(first_text or 0, 1),
               tools=tools, clarifies=clarifies)
    return rec


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="bench.json")
    ap.add_argument("--only", default="")
    ap.add_argument("--cold", action="store_true", help="build a fresh session per question (no pool)")
    a = ap.parse_args()
    only = {int(x) for x in a.only.split(",") if x != ""}
    results, session = [], None
    pool = SessionPool()
    if not a.cold:
        pool.warm()
        await pool._warm  # exclude one-time startup from timings, like a running server
    for i, (name, text, reuse) in enumerate(QUESTIONS):
        if only and i not in only:
            continue
        if not (reuse and session):
            if session:
                await session.close()
            session = Session() if a.cold else await pool.take()
        r = await run(session, text)
        r["name"] = name
        results.append(r)
        print(f"{name:10} {r['wall_s']:>6}s first={r['first_event_s']}s text={r['first_text_s']}s turns={r.get('turns')} "
              f"cost=${(r.get('cost_usd') or 0):.3f} clarify={r['clarifies']} tools={len(r['tools'])} "
              f"cache_read={r.get('cache_read')} err={r['error']}", flush=True)
    if session:
        await session.close()
    await pool.close()
    json.dump(results, open(a.out, "w"), indent=2)
    tot = sum(r["wall_s"] for r in results)
    print(f"\ntotal {tot:.1f}s, cost ${sum((r.get('cost_usd') or 0) for r in results):.2f} -> {a.out}")


if __name__ == "__main__":
    asyncio.run(main())
