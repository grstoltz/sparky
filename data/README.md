# Context pack

`context_cards.json` holds the typed business context (DRIED context cards) for Arm 3. Only Arm 3
loads it, so Arms 1 and 2 remain clean baselines.

The real file is generated in the dbt repo (`data-engg-alab-dbt-redshift`) by a script that walks
`manifest.json` after `dbt parse`/`dbt compile`, pulls each metric's description and
`config.meta.context_card`, and writes this schema:

```json
{ "metrics": { "<metric_name>": { "description": "...", "context_card": { "<section>": { "<field>": "text or list" } } } } }
```

Field paths used by `cite_context` are relative to the card, e.g. `investigations.known_structural_causes`.
Regenerate and re-sync this file whenever `metrics.yml` changes (the dbt repo should expose a Makefile
target), otherwise it goes stale. Point Sparky at another location with `SPARKY_CONTEXT_PACK`.
