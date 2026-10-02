# Sparky

Conversational analytics over the dbt Semantic Layer. A web chat app built on the
Claude Agent SDK that uses the dbt MCP server and Socratic rules to sharpen vague
questions into precise semantic-layer queries.

## Run
```bash
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
cp .env.example .env   # fill in DBT_HOST (see Auth below); ANTHROPIC_API_KEY is optional
set -a; source .env; set +a
.venv/bin/uvicorn sparky.server:app --reload
```
Open http://localhost:8000. Requires `uvx` (install `uv`) to launch `dbt-mcp`.

## Auth to Anthropic
Sparky drives the bundled Claude Code CLI, so it uses whatever login Claude Code has.
- **OAuth (default when `ANTHROPIC_API_KEY` is empty):** run `claude` once and `/login`, then start Sparky
  from a shell with the same `CLAUDE_CONFIG_DIR` (if you use one) so it finds the credentials.
- **API key:** set `ANTHROPIC_API_KEY` in `.env`. A set key takes precedence over the login.

## Auth to dbt
- **OAuth (default when `DBT_TOKEN` is empty):** set only `DBT_HOST` to your static-subdomain Access
  URL. On the first query `dbt-mcp` opens a browser on the machine running the server for login
  and project selection. Needs an Enterprise/Enterprise+ account with AI features enabled.
  The login belongs to whoever is at the server's browser, so this suits local, single-user use.
- **Service token:** set `DBT_TOKEN` and `DBT_PROD_ENV_ID` as well. Use this for a shared or deployed app.

## Customize behavior
- [src/sparky/rules/socratic.md](src/sparky/rules/socratic.md): the question-refinement rules
- [src/sparky/rules/system.md](src/sparky/rules/system.md): role and safety
- [src/sparky/config.py](src/sparky/config.py): allowed/blocked tools (read-only by default)
