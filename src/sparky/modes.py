"""The three demo configurations ("arms"). Same question, three levels of context.

Arm 1  Text2SQL        raw SQL only: no metric definitions, no Socratic rules, no context
Arm 2  Semantic layer  dbt Semantic Layer metrics, stripped prompt: pick closest metric, query, answer
Arm 3  + context cards Semantic layer + Socratic rules + typed business context and citations
"""
from dataclasses import dataclass

from .config import BASE_DISALLOWED_TOOLS, CITE_TOOL, CLARIFY_TOOL, DBT_TOOLS, SQL_TOOLS


@dataclass(frozen=True)
class Mode:
    id: str
    label: str
    short: str
    dbt_tools: tuple[str, ...]
    prompt_files: tuple[str, ...]
    clarify: bool = False
    cite: bool = False
    context: bool = False  # load the context pack into the prompt

    @property
    def allowed_tools(self) -> list[str]:
        tools = [f"mcp__dbt__{t}" for t in self.dbt_tools]
        if self.clarify:
            tools.append(CLARIFY_TOOL)
        if self.cite:
            tools.append(CITE_TOOL)
        return tools

    @property
    def disallowed_tools(self) -> list[str]:
        extra = [] if "execute_sql" in self.dbt_tools else ["mcp__dbt__execute_sql"]
        return BASE_DISALLOWED_TOOLS + extra

    @property
    def uses_sparky_server(self) -> bool:
        return self.clarify or self.cite


MODES: dict[str, Mode] = {
    "arm1": Mode("arm1", "Arm 1 — Text2SQL", "Text2SQL", tuple(SQL_TOOLS), ("arm1.md",)),
    "arm2": Mode("arm2", "Arm 2 — Semantic layer", "Semantic layer", tuple(DBT_TOOLS), ("arm2.md",)),
    "arm3": Mode(
        "arm3", "Arm 3 — Context-aware", "Semantic + context", tuple(DBT_TOOLS),
        ("system.md", "socratic.md"), clarify=True, cite=True, context=True,
    ),
}
DEFAULT_MODE = "arm3"


def get_mode(mode_id: str | None) -> Mode:
    try:
        return MODES[mode_id or DEFAULT_MODE]
    except KeyError:
        raise ValueError(f"Unknown mode {mode_id!r}; expected one of {sorted(MODES)}") from None
