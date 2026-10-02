from sparky.agent import dbt_mcp_config
from sparky.config import Settings


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
