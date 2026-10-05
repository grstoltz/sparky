/* Chart planning for result cards: which chart types fit a result, and the Chart.js config for each.
 * Pure functions (no DOM), so they can be tested with Node: `node tests/charts.test.js`.
 *
 * shape = { rows, cols, metrics, dims, timeDim, labels, shortLabels, intent }  (see shapeOf; intent from intentOf)
 */
(function (root) {
  const KINDS = {
    bar: 'Bar',
    hbar: 'Horizontal bar',
    line: 'Line',
    area: 'Area',
    stacked: 'Stacked bar',
    pie: 'Pie',
    scatter: 'Scatter',
  };
  const MAX_PIE_SLICES = 12;

  /* What the question asks for, judged from its wording: 'yoy' (year over year), 'trend' (over time) or null.
   * 'yoy' splits the result into one series per year (see yoySplit); the chart type follows the x axis. */
  const YOY_RE = new RegExp([
    String.raw`\byear[\s-]*(over|on|to)[\s-]*year\b`, String.raw`\b(yoy|y\/y|y-o-y)\b`,
    String.raw`\b(vs\.?|versus|compared?\s+(to|with)|against|than)\s+(the\s+)?(last|prior|previous)\s+year\b`,
    String.raw`\bsame\s+(time|point|period|day|week|month|term|session)\s+(as\s+)?(last|prior|previous)\s+year\b`,
  ].join('|'), 'i');
  const TREND_RE = new RegExp([
    String.raw`\bover\s+time\b`, String.raw`\btrend`, String.raw`\btime[\s-]*series\b`, String.raw`\bhistoric`,
    String.raw`\bover\s+the\s+(last|past)\b`, String.raw`\b(daily|weekly|monthly|quarterly|yearly|annually)\b`,
    String.raw`\bby\s+(day|week|month|quarter|year|term|session)\b`,
  ].join('|'), 'i');
  function intentOf(question) {
    const q = String(question || '');
    return YOY_RE.test(q) ? 'yoy' : TREND_RE.test(q) ? 'trend' : null;
  }

  const isNum = (v) => typeof v === 'number' || (typeof v === 'string' && v.trim() !== '' && !isNaN(v));

  /* Whether the question asks to see a chart: chart words, or trend / year-over-year wording.
   * Follow-up questions open on the data unless this is true. */
  const CHART_RE = /\b(chart|graph|plot|visuali[sz]|visual|draw|diagram)/i;
  function wantsChart(question) {
    return CHART_RE.test(String(question || '')) || intentOf(question) !== null;
  }

  function shapeOf(ev, intent) {
    const cols = ev.columns || [];
    let rows = ev.rows || [];
    let metrics = (ev.metrics || []).filter((m) => cols.includes(m));
    // No declared metrics (e.g. raw SQL whose numbers arrive as strings): chart the numeric columns,
    // keeping the first column as the x axis when every column is numeric.
    if (!metrics.length && rows.length) {
      metrics = cols.filter((c) => rows.every((r) => r[c] == null || isNum(r[c])) && rows.some((r) => r[c] != null));
      if (metrics.length === cols.length && cols.length > 1 && rows.length > 1) metrics = metrics.slice(1);
    }
    // Numeric strings (decimals often come back that way) become numbers so every chart type can plot them.
    if (metrics.some((m) => rows.some((r) => typeof r[m] === 'string'))) {
      rows = rows.map((r) => {
        const o = { ...r };
        metrics.forEach((m) => { if (typeof o[m] === 'string' && isNum(o[m])) o[m] = +o[m]; });
        return o;
      });
    }
    const dims = cols.filter((c) => !metrics.includes(c));
    const fromGroupBy = ((ev.group_by || []).find((g) => g.type === 'time_dimension') || {}).name;
    const timeDim = dims.find((c) => /metric_time|_dt(__\w+)?$|date/i.test(c)) || (dims.includes(fromGroupBy) ? fromGroupBy : undefined);
    return { rows, cols, metrics, dims, timeDim, labels: ev.labels || {}, shortLabels: ev.short_labels || {}, intent: intent || null };
  }

  /* Friendly metric name for titles: the semantic layer's label, else "enrl_students_budget" -> "Enrl students budget". */
  function metricLabel(shape, m) {
    return (shape.labels || {})[m] || String(m).replace(/_/g, ' ').replace(/^./, (c) => c.toUpperCase());
  }
  /* Short name for tooltips, legends and axes (dbt config.meta.short_label, e.g. "Enrollments"), else the label. */
  function shortLabel(shape, m) {
    return (shape.shortLabels || {})[m] || metricLabel(shape, m);
  }

  const fmtLabel = (v, isTime) => {
    const s = v == null ? '' : String(v);
    return isTime ? s.slice(0, 10) : s; // 2026-09-23T00:00:00 -> 2026-09-23
  };

  // ---- Year over year: one series per year on a shared x axis ----
  const YEAR_RE = /\b(?:19|20)\d{2}(?:\s*[-\u2013/]\s*(?:19|20)?\d{2})?\b/; // 2025, 2025-26, 2025-2026
  const YEAR_DIM_RE = /(^|_)(yr|year)$/i; // acad_yr, fiscal_yr, calendar_yr, metric_time__year
  const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const yearOf = (v) => (String(v ?? '').match(YEAR_RE) || [])[0];
  const stripYear = (v) => String(v ?? '').replace(YEAR_RE, '').replace(/\s{2,}/g, ' ').trim();
  const grainOf = (d) => ((d.match(/__(day|week|month|quarter|year)$/i) || [])[1] || 'day').toLowerCase();

  /* Position within the year for a date, so different years line up: { key (sortable), label }. */
  function seasonal(v, grain) {
    const s = String(v ?? ''), mm = +s.slice(5, 7), dd = +s.slice(8, 10);
    const pad = (n) => String(n).padStart(2, '0');
    if (grain === 'month') return { key: pad(mm), label: MONTHS[mm - 1] };
    if (grain === 'quarter') { const q = Math.ceil(mm / 3); return { key: 'Q' + q, label: 'Q' + q }; }
    if (grain === 'week') {
      const y = +s.slice(0, 4), w = Math.floor((Date.UTC(y, mm - 1, dd) - Date.UTC(y, 0, 1)) / 864e5 / 7) + 1;
      return { key: 'W' + pad(w), label: 'Wk ' + w };
    }
    return { key: pad(mm) + '-' + pad(dd), label: MONTHS[mm - 1] + ' ' + dd };
  }

  /* Split a one-metric result into per-year series, or null when the result has no year to split on:
   *  - two dimensions, one a year (acad_yr...) or year-bearing ('Fall 2025'): it is the series, the other is x;
   *  - one date dimension below year grain: the year is the series, the date within the year is x;
   *  - one dimension whose values carry a year ('Fall A 2025'): the year is the series, the rest is x. */
  function yoySplit(shape) {
    const { rows, metrics, dims, timeDim } = shape;
    if (metrics.length !== 1 || !rows.length) return null;
    const allYears = (d) => rows.every((r) => yearOf(r[d]));
    let seriesDim, xDim, seriesOf, xOf;
    if (dims.length === 2) {
      seriesDim = dims.find((d) => YEAR_DIM_RE.test(d)) || dims.find((d) => d !== timeDim && allYears(d));
      if (!seriesDim) return null;
      xDim = dims.find((d) => d !== seriesDim);
      seriesOf = (r) => (seriesDim === timeDim ? String(r[seriesDim]).slice(0, 4) : String(r[seriesDim]));
      // Drop any year from the x value too ('Fall 2025' -> 'Fall') so the years share one axis.
      xOf = xDim === timeDim ? (r) => seasonal(r[xDim], grainOf(xDim))
        : (r) => { const k = stripYear(r[xDim]) || String(r[xDim]); return { key: k, label: k }; };
    } else if (dims.length === 1 && dims[0] === timeDim && grainOf(timeDim) !== 'year') {
      xDim = seriesDim = timeDim;
      seriesOf = (r) => String(r[timeDim]).slice(0, 4);
      xOf = (r) => seasonal(r[timeDim], grainOf(timeDim));
    } else if (dims.length === 1 && dims[0] !== timeDim && allYears(dims[0]) && rows.every((r) => stripYear(r[dims[0]]))) {
      xDim = seriesDim = dims[0];
      seriesOf = (r) => yearOf(r[xDim]);
      xOf = (r) => { const k = stripYear(r[xDim]); return { key: k, label: k }; };
    } else return null;

    const names = [...new Set(rows.map(seriesOf))].sort((a, b) =>
      String(yearOf(a) || a).localeCompare(String(yearOf(b) || b)) || a.localeCompare(b));
    if (names.length < 2) return null;
    const xs = new Map();
    rows.forEach((r) => { const x = xOf(r); if (!xs.has(x.key)) xs.set(x.key, x.label); });
    let keys = [...xs.keys()];
    if (keys.every((k) => k !== '' && !isNaN(k))) keys.sort((a, b) => a - b); // week numbers, days to census
    else if (xDim === timeDim) keys.sort();
    const m = metrics[0];
    const datasets = names.map((n) => ({
      label: n,
      data: keys.map((k) => {
        const hit = rows.find((r) => seriesOf(r) === n && xOf(r).key === k);
        return hit ? hit[m] : null;
      }),
    }));
    return { labels: keys.map((k) => xs.get(k)), datasets, xDim, seriesDim, metricLabel: shortLabel(shape, m), yoy: true };
  }

  /* Labels and datasets. With two dimensions and one metric, the second dimension becomes the series
   * (e.g. term on x, program as separate bars), which is what comparisons need. */
  function prepare(shape) {
    const { rows, metrics, dims, timeDim } = shape;
    const yoy = shape.intent === 'yoy' && yoySplit(shape);
    if (yoy) return yoy;
    const xDim = timeDim || dims[0];
    const seriesDim = dims.length >= 2 && metrics.length === 1 ? dims.find((d) => d !== xDim) : null;

    if (seriesDim) {
      const labels = [...new Set(rows.map((r) => fmtLabel(r[xDim], xDim === timeDim)))];
      const names = [...new Set(rows.map((r) => String(r[seriesDim])))];
      const m = metrics[0];
      const datasets = names.map((n) => ({
        label: n,
        data: labels.map((l) => {
          const hit = rows.find((r) => fmtLabel(r[xDim], xDim === timeDim) === l && String(r[seriesDim]) === n);
          return hit ? hit[m] : null;
        }),
      }));
      return { labels, datasets, xDim, seriesDim, metricLabel: shortLabel(shape, m) };
    }
    // No dimension to label the x axis with: number the rows.
    const labels = rows.map((r, i) => (dims.length ? dims.map((d) => fmtLabel(r[d], d === timeDim)).join(' · ') : String(i + 1)));
    const datasets = metrics.map((m) => ({ label: shortLabel(shape, m), data: rows.map((r) => r[m]) }));
    return { labels, datasets, xDim, seriesDim: null };
  }

  // Ordinal time offsets, e.g. term_sess_snp_rel_wk_nbr (weeks from session start): a time axis too.
  const REL_TIME_RE = /(^|_)(wk|week|day|month)_?(nbr|num|number)$/i;

  /* Chart types that make sense for this result, best default first. Empty means "show a stat" (one row)
   * or, with nothing numeric, the table. A time-series x axis defaults to a line, anything else to a bar. */
  function kinds(shape) {
    const { rows, metrics, timeDim } = shape;
    if (rows.length < 2 || metrics.length === 0) return [];
    const p = prepare(shape);
    const multi = p.datasets.length > 1;
    const timeAxis = (timeDim !== undefined && p.xDim === timeDim) || REL_TIME_RE.test(p.xDim || '');
    const out = timeAxis ? ['line', 'area', 'bar'] : ['bar', 'hbar', 'line'];
    // Stacking adds series together, which is meaningless across years.
    if (multi && !p.yoy) out.splice(out.indexOf('bar') + 1, 0, 'stacked');
    const vals = p.datasets[0].data;
    const pieOk = !timeAxis && p.datasets.length === 1 && rows.length <= MAX_PIE_SLICES &&
      vals.every((v) => typeof v === 'number' && v >= 0) && vals.some((v) => v > 0);
    if (pieOk) out.push('pie');
    if (metrics.length >= 2 && metrics.every((m) => rows.every((r) => typeof r[m] === 'number'))) out.push('scatter');
    return out;
  }

  /* Chart.js config for `kind`. `palette` is an array of CSS colors. */
  function config(kind, shape, palette) {
    const p = prepare(shape);
    const color = (i) => palette[i % palette.length];
    const base = { responsive: true, plugins: { legend: { display: p.datasets.length > 1 } }, scales: { y: { beginAtZero: true } } };

    if (kind === 'pie') {
      return {
        type: 'pie',
        data: { labels: p.labels, datasets: [{ label: p.datasets[0].label, data: p.datasets[0].data, backgroundColor: p.labels.map((_, i) => color(i)) }] },
        options: { responsive: true, plugins: { legend: { display: true, position: 'right' } } },
      };
    }
    if (kind === 'scatter') {
      const [mx, my] = shape.metrics;
      const [lx, ly] = [shortLabel(shape, mx), shortLabel(shape, my)];
      return {
        type: 'scatter',
        data: { datasets: [{ label: `${ly} vs ${lx}`, data: shape.rows.map((r) => ({ x: r[mx], y: r[my] })), backgroundColor: color(0) }] },
        options: { responsive: true, plugins: { legend: { display: false } },
          scales: { x: { title: { display: true, text: lx } }, y: { title: { display: true, text: ly }, beginAtZero: true } } },
      };
    }
    const type = kind === 'line' || kind === 'area' ? 'line' : 'bar';
    const datasets = p.datasets.map((d, i) => ({
      ...d,
      borderColor: color(i),
      backgroundColor: kind === 'area' ? color(i) + '55' : color(i),
      fill: kind === 'area',
      tension: 0.2,
    }));
    const options = { ...base };
    // Series datasets are named after the second dimension, so put the metric in the tooltip line.
    if (p.seriesDim) {
      options.plugins = { ...base.plugins,
        tooltip: { callbacks: { label: (ctx) => `${ctx.dataset.label} · ${p.metricLabel}: ${ctx.formattedValue}` } } };
    }
    if (kind === 'hbar') options.indexAxis = 'y';
    if (kind === 'stacked') options.scales = { x: { stacked: true }, y: { stacked: true, beginAtZero: true } };
    return { type, data: { labels: p.labels, datasets }, options };
  }

  const api = { KINDS, intentOf, wantsChart, shapeOf, metricLabel, shortLabel, prepare, kinds, config };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.SparkyCharts = api;
})(typeof window !== 'undefined' ? window : globalThis);
