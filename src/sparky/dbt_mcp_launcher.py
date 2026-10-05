"""Launch ``dbt-mcp`` with a clean environment.

dbt-mcp builds its settings with pydantic-settings, which reads the process environment *and* a
``.env`` file in the current working directory. An empty value such as ``DBT_PROD_ENV_ID=`` is
parsed as ``""`` rather than "unset", and dbt-mcp dies at startup with an int validation error.
Both sources are hit in practice: ``.env.example`` ships empty keys, and ``make start`` exports
the whole ``.env`` with ``set -a``. This wrapper drops empty dbt variables and starts dbt-mcp from
a directory that has no ``.env``.

It also points the dbt-mcp interpreter at certifi's CA bundle (unless the caller already set one).
``uvx`` may pick a python.org framework Python on macOS, whose ``ssl`` module has no root
certificates until "Install Certificates.command" is run; dbt-mcp then fails every HTTPS call with
``CERTIFICATE_VERIFY_FAILED``.
"""
import os
import sys
import tempfile

PREFIXES = ("DBT_", "MULTICELL_")


CA_VARS = ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE")


def clean_env(env: dict[str, str]) -> dict[str, str]:
    """Return a copy of ``env`` without empty-valued dbt-mcp settings, with a CA bundle set."""
    out = {k: v for k, v in env.items() if v != "" or not k.startswith(PREFIXES)}
    if not any(out.get(v) for v in CA_VARS):
        try:
            import certifi
        except ImportError:  # pragma: no cover - certifi ships with the SDK's httpx dependency
            return out
        out.update({v: certifi.where() for v in CA_VARS})
    return out


def main() -> None:
    env = clean_env(dict(os.environ))
    os.chdir(tempfile.gettempdir())
    os.execvpe("uvx", ["uvx", "dbt-mcp", *sys.argv[1:]], env)


if __name__ == "__main__":
    main()
