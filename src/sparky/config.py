import os
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

CLARIFY_TOOL = "mcp__sparky__ask_clarifying_question"
ALLOWED_TOOLS = [f"mcp__dbt__{t}" for t in DBT_TOOLS] + [CLARIFY_TOOL]
DISALLOWED_TOOLS = [
    "Bash", "Write", "Edit", "NotebookEdit", "WebFetch", "WebSearch",
    "mcp__dbt__execute_sql", "mcp__dbt__trigger_job_run",
    "mcp__dbt__retry_job_run", "mcp__dbt__cancel_job_run",
]


@dataclass
class Settings:
    model: str | None = field(default_factory=lambda: os.getenv("SPARKY_MODEL") or None)
    dbt_host: str = field(default_factory=lambda: os.getenv("DBT_HOST", "cloud.getdbt.com"))
    dbt_token: str = field(default_factory=lambda: os.getenv("DBT_TOKEN", ""))
    dbt_prod_env_id: str = field(default_factory=lambda: os.getenv("DBT_PROD_ENV_ID", ""))
    # Multi-cell accounts: DBT_HOST=us1.dbt.com + MULTICELL_ACCOUNT_PREFIX=abc123
    dbt_account_prefix: str = field(default_factory=lambda: os.getenv("MULTICELL_ACCOUNT_PREFIX", ""))
    max_turns: int = 25

    @property
    def use_oauth(self) -> bool:
        """No service token configured -> dbt-mcp runs its browser OAuth flow."""
        return not self.dbt_token
