"""Context pack: typed business context (DRIED context cards) distilled from the dbt manifest.

Generated in the dbt repo (see data/README.md) and synced to data/context_cards.json.
Only Arm 3 loads it, so Arms 1 and 2 stay clean baselines.
"""
import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

EMPTY: dict[str, Any] = {"metrics": {}}


def load_context_cards(path: Path | str) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        log.warning("Context pack %s not found; Arm 3 will run without context cards", p)
        return {"metrics": {}}
    data = json.loads(p.read_text())
    if not isinstance(data.get("metrics"), dict):
        raise ValueError(f"{p}: expected a top-level 'metrics' object")
    return data


def _walk(node: Any, prefix: str = ""):
    """Yield (dotted_path, value) for every leaf of a context card."""
    if isinstance(node, dict):
        for k, v in node.items():
            yield from _walk(v, f"{prefix}.{k}" if prefix else k)
    else:
        yield prefix, node


def _text(value: Any) -> str:
    return "; ".join(map(str, value)) if isinstance(value, list) else str(value)


def render_for_prompt(pack: dict[str, Any]) -> str:
    """Compact text block appended to the Arm 3 system prompt."""
    lines: list[str] = []
    for name, m in pack["metrics"].items():
        card = m.get("context_card")
        if not card:
            continue
        lines.append(f"### {name}")
        if m.get("description"):
            lines.append(m["description"])
        for path, value in _walk(card):
            lines.append(f"- {path}: {_text(value)}")
    if not lines:
        return ""
    return "## Business context cards\nField paths below are what `cite_context` expects.\n\n" + "\n".join(lines)


def resolve(pack: dict[str, Any], paths: list[str], metric: str | None = None) -> tuple[list[dict], list[str]]:
    """Look up context-card field paths. Returns (citations, unknown_paths)."""
    metrics = pack["metrics"]
    scope = {metric: metrics[metric]} if metric in metrics else metrics
    found: list[dict] = []
    unknown: list[str] = []
    for path in paths:
        hits = []
        for name, m in scope.items():
            leaves = dict(_walk(m.get("context_card") or {}))
            # Exact leaf, or a parent path such as "investigations" that covers several leaves
            for leaf, value in leaves.items():
                if leaf == path or leaf.startswith(path + "."):
                    hits.append({"metric": name, "path": leaf, "text": _text(value)})
        if hits:
            found.extend(hits)
        else:
            unknown.append(path)
    return found, unknown
