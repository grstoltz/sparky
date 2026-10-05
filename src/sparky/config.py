import os
from pathlib import Path
from dataclasses import dataclass, field

# Semantic-layer tools only. Everything else from dbt-mcp is not allow-listed.
DBT_TOOLS = [
    "list_metrics",
    "get_dimensions",
    "get_entities",
    "get_dimension_values",
    "query_metrics",
    "get_metrics_compiled_sql",
]

SQL_TOOLS = ["execute_sql"]  # Arm 1 only: raw SQL, no metric definitions

CLARIFY_TOOL = "mcp__sparky__ask_clarifying_question"
CITE_TOOL = "mcp__sparky__cite_context"
# Always blocked. execute_sql is added back per mode (Arm 1 only), see modes.py.
BASE_DISALLOWED_TOOLS = [
    "Bash", "Write", "Edit", "NotebookEdit", "WebFetch", "WebSearch",
    "mcp__dbt__trigger_job_run", "mcp__dbt__retry_job_run", "mcp__dbt__cancel_job_run",
]

ROOT = Path(__file__).resolve().parents[2]


@dataclass
class Settings:
    model: str | None = field(default_factory=lambda: os.getenv("SPARKY_MODEL") or None)
    dbt_host: str = field(default_factory=lambda: os.getenv("DBT_HOST", "cloud.getdbt.com"))
    dbt_token: str = field(default_factory=lambda: os.getenv("DBT_TOKEN", ""))
    dbt_prod_env_id: str = field(default_factory=lambda: os.getenv("DBT_PROD_ENV_ID", ""))
    # Multi-cell accounts: DBT_HOST=us1.dbt.com + MULTICELL_ACCOUNT_PREFIX=abc123
    dbt_account_prefix: str = field(default_factory=lambda: os.getenv("MULTICELL_ACCOUNT_PREFIX", ""))
    max_turns: int = 25
    # Demo modes (see modes.py): arm1 = Text2SQL, arm2 = semantic layer only, arm3 = + context cards
    mode: str = field(default_factory=lambda: os.getenv("SPARKY_MODE", "arm3"))
    # Replay recorded transcripts instead of calling the model (also available per request via ?mock=1)
    mock_mode: bool = field(default_factory=lambda: os.getenv("SPARKY_MOCK_MODE", "").lower() in ("1", "true", "yes"))
    context_path: Path = field(default_factory=lambda: Path(os.getenv("SPARKY_CONTEXT_PACK") or ROOT / "data" / "context_cards.json"))
    transcripts_path: Path = field(default_factory=lambda: ROOT / "demo" / "transcripts.yaml")
    # Seconds to wait for the first live event before falling back to a recorded transcript
    live_timeout_s: float = field(default_factory=lambda: float(os.getenv("SPARKY_LIVE_TIMEOUT", "30")))

    @property
    def use_oauth(self) -> bool:
        """No service token configured -> dbt-mcp runs its browser OAuth flow."""
        return not self.dbt_token
