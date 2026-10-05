/* Chart planning for result cards: which chart types fit a result, and the Chart.js config for each.
 * Pure functions (no DOM), so they can be tested with Node: `node tests/charts.test.js`.
 *
 * shape = { rows, cols, metrics, dims, timeDim }  (see shapeOf)
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

  function shapeOf(ev) {
    const cols = ev.columns || [];
    const metrics = (ev.metrics || []).filter((m) => cols.includes(m));
    const dims = cols.filter((c) => !metrics.includes(c));
    const fromGroupBy = ((ev.group_by || []).find((g) => g.type === 'time_dimension') || {}).name;
    const timeDim = dims.find((c) => /metric_time|_dt$|date/i.test(c)) || (dims.includes(fromGroupBy) ? fromGroupBy : undefined);
    return { rows: ev.rows || [], cols, metrics, dims, timeDim };
  }

  const fmtLabel = (v, isTime) => {
    const s = v == null ? '' : String(v);
    return isTime ? s.slice(0, 10) : s; // 2026-09-23T00:00:00 -> 2026-09-23
  };

  /* Labels and datasets. With two dimensions and one metric, the second dimension becomes the series
   * (e.g. term on x, program as separate bars), which is what comparisons need. */
  function prepare(shape) {
    const { rows, metrics, dims, timeDim } = shape;
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
      return { labels, datasets, xDim, seriesDim };
    }
    const labels = rows.map((r) => dims.map((d) => fmtLabel(r[d], d === timeDim)).join(' · '));
    const datasets = metrics.map((m) => ({ label: m, data: rows.map((r) => r[m]) }));
    return { labels, datasets, xDim, seriesDim: null };
  }

  /* Chart types that make sense for this result, best default first. Empty means "show a stat/table". */
  function kinds(shape) {
    const { rows, metrics, dims, timeDim } = shape;
    if (rows.length < 2 || metrics.length === 0 || dims.length === 0) return [];
    const p = prepare(shape);
    const multi = p.datasets.length > 1;
    const out = timeDim ? ['line', 'area', 'bar'] : ['bar', 'hbar', 'line'];
    if (multi) out.splice(out.indexOf('bar') + 1, 0, 'stacked');
    const vals = p.datasets[0].data;
    const pieOk = !timeDim && p.datasets.length === 1 && rows.length <= MAX_PIE_SLICES &&
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
      return {
        type: 'scatter',
        data: { datasets: [{ label: `${my} vs ${mx}`, data: shape.rows.map((r) => ({ x: r[mx], y: r[my] })), backgroundColor: color(0) }] },
        options: { responsive: true, plugins: { legend: { display: false } },
          scales: { x: { title: { display: true, text: mx } }, y: { title: { display: true, text: my }, beginAtZero: true } } },
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
    if (kind === 'hbar') options.indexAxis = 'y';
    if (kind === 'stacked') options.scales = { x: { stacked: true }, y: { stacked: true, beginAtZero: true } };
    return { type, data: { labels: p.labels, datasets }, options };
  }

  const api = { KINDS, shapeOf, prepare, kinds, config };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.SparkyCharts = api;
})(typeof window !== 'undefined' ? window : globalThis);
