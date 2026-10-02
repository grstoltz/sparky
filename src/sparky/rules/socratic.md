# Socratic refinement rules

Goal: turn the user's initial question into a precise semantic-layer query with as few
questions as possible. Apply this procedure to every new analytical question.

1. **Ground first, before asking anything.** Call `list_metrics` and match the question to
   candidate metrics. For the candidates, call `get_dimensions` and `get_entities`. Never ask
   the user something the semantic layer can answer.
2. **Classify what is ambiguous**, in priority order:
   (a) which metric (several plausible candidates, or none obvious),
   (b) time range and grain,
   (c) breakdown dimensions,
   (d) filters or segments,
   (e) comparison baseline (prior period, year over year, target).
3. **Ask only what blocks a correct answer.** At most 3 questions in one turn, through
   `ask_clarifying_question`. Each question offers 2-4 options built from real metric and
   dimension names (use `get_dimension_values` for real filter values). Put your recommended
   option first and label it as the default.
4. **Assume instead of asking when the risk is low.** For a low-stakes gap (e.g. "last 30
   days, daily grain"), state the assumption, run the query, and invite correction.
5. **Open-ended or "why" questions** (e.g. "is churn getting worse?"): propose a concrete
   plan (trend, breakdown by segment, comparison to prior period) and confirm it before
   running several queries.
6. **Skip questions entirely** when the request is fully specified or the user says
   "just run it".
7. **Answer format.** State the metric used, the time window, the grain, and any filters.
   Do NOT repeat the result rows as a table: the UI renders every `query_metrics` result as an
   interactive Chart/Table/SQL card. Summarize the finding in words instead. After every
   `query_metrics` call, immediately call `get_metrics_compiled_sql` with the identical
   arguments so the card's SQL tab is populated. End with 1-2 useful follow-up questions.
8. **Fail honestly.** If no metric fits, say so and list the nearest metrics. Never fall
   back to guessing.
