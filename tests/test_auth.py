from sparky.agent import dbt_mcp_config
from sparky.config import Settings
from sparky.modes import get_mode


def test_oauth_when_no_token():
    s = Settings(dbt_host="abc123.us1.dbt.com", dbt_token="", dbt_prod_env_id="")
    env = dbt_mcp_config(s)["env"]
    assert s.use_oauth
    assert env["DBT_HOST"] == "abc123.us1.dbt.com"
    assert "DBT_TOKEN" not in env and "DBT_PROD_ENV_ID" not in env


def test_token_mode():
    s = Settings(dbt_host="cloud.getdbt.com", dbt_token="t", dbt_prod_env_id="1")
    env = dbt_mcp_config(s)["env"]
    assert not s.use_oauth
    assert env["DBT_TOKEN"] == "t" and env["DBT_PROD_ENV_ID"] == "1"


def test_only_semantic_layer_tools_exposed():
    from sparky.config import DBT_TOOLS
    env = dbt_mcp_config(Settings(dbt_host="h"), get_mode("arm3"))["env"]
    assert env["DBT_MCP_ENABLE_TOOLS"].split(",") == DBT_TOOLS
    assert not any(k.startswith("DISABLE_") for k in env)


def test_dbt_mcp_runs_through_launcher():
    cfg = dbt_mcp_config(Settings(dbt_host="h"))
    assert cfg["args"] == ["-m", "sparky.dbt_mcp_launcher"]


def test_launcher_drops_empty_dbt_vars_only():
    from sparky.dbt_mcp_launcher import clean_env
    env = {"DBT_PROD_ENV_ID": "", "DBT_TOKEN": "", "MULTICELL_ACCOUNT_PREFIX": "", "DBT_HOST": "h",
           "ANTHROPIC_API_KEY": "", "PATH": "/bin"}
    out = clean_env(env)
    assert {k: out[k] for k in ("DBT_HOST", "ANTHROPIC_API_KEY", "PATH")} == {
        "DBT_HOST": "h", "ANTHROPIC_API_KEY": "", "PATH": "/bin"}
    assert not any(k in out for k in ("DBT_PROD_ENV_ID", "DBT_TOKEN", "MULTICELL_ACCOUNT_PREFIX"))


def test_launcher_sets_ca_bundle_unless_given():
    import certifi
    from sparky.dbt_mcp_launcher import clean_env
    assert clean_env({})["SSL_CERT_FILE"] == certifi.where()
    assert clean_env({"SSL_CERT_FILE": "/corp/ca.pem"})["SSL_CERT_FILE"] == "/corp/ca.pem"


def test_mcp_startup_timeout_allows_browser_login():
    from sparky.agent import MCP_STARTUP_TIMEOUT_MS, build_options
    from sparky.tools.clarify import ClarifyBroker
    opts = build_options(Settings(dbt_host="h"), ClarifyBroker(lambda e: None), get_mode("arm2"))
    assert int(opts.env["MCP_TIMEOUT"]) == MCP_STARTUP_TIMEOUT_MS >= 120_000
