// Run with: node tests/charts.test.js  (also run by tests/test_charts.py)
const assert = require('assert');
const C = require('../web/assets/charts.js');
const PAL = ['#8C1D40', '#FFC627', '#00A3E0', '#78BE20', '#FF7F32', '#747474'];

const ev = (cols, metrics, rows, group_by = []) => ({ columns: cols, metrics, rows, group_by });
const sh = (...a) => C.shapeOf(ev(...a));

// categorical, one metric
const cat = sh(['season', 'n'], ['n'], [{ season: 'Fall', n: 5 }, { season: 'Summer', n: 3 }]);
assert.deepStrictEqual(C.kinds(cat), ['bar', 'hbar', 'line', 'pie']);

// time dimension: line first, no pie
const time = sh(['metric_time__day', 'n'], ['n'],
  [{ metric_time__day: '2026-09-22T00:00:00', n: 1 }, { metric_time__day: '2026-09-23T00:00:00', n: 2 }]);
assert.strictEqual(time.timeDim, 'metric_time__day');
assert.deepStrictEqual(C.kinds(time), ['line', 'area', 'bar']);
assert.deepStrictEqual(C.prepare(time).labels, ['2026-09-22', '2026-09-23']);

// time dim detected from group_by even when the name does not look like a date
const gb = sh(['term', 'n'], ['n'], [{ term: 'a', n: 1 }, { term: 'b', n: 2 }], [{ name: 'term', type: 'time_dimension' }]);
assert.strictEqual(gb.timeDim, 'term');

// two dimensions + one metric: second dimension becomes the series (comparison shape)
const two = sh(['term', 'program', 'n'], ['n'], [
  { term: 'Fall A', program: 'Q', n: 10 }, { term: 'Fall A', program: 'S', n: 20 },
  { term: 'Fall B', program: 'Q', n: 12 }, { term: 'Fall B', program: 'S', n: 18 }]);
const p2 = C.prepare(two);
assert.deepStrictEqual(p2.labels, ['Fall A', 'Fall B']);
assert.deepStrictEqual(p2.datasets.map((d) => d.label), ['Q', 'S']);
assert.deepStrictEqual(p2.datasets[1].data, [20, 18]);
assert.ok(C.kinds(two).includes('stacked'));
assert.ok(!C.kinds(two).includes('pie'));

// missing combination becomes null, not a crash
const gap = sh(['term', 'program', 'n'], ['n'], [
  { term: 'A', program: 'Q', n: 1 }, { term: 'B', program: 'S', n: 2 }]);
assert.deepStrictEqual(C.prepare(gap).datasets.map((d) => d.data), [[1, null], [null, 2]]);

// two metrics: stacked and scatter offered
const mm = sh(['season', 'a', 'b'], ['a', 'b'], [{ season: 'x', a: 1, b: 2 }, { season: 'y', a: 3, b: 4 }]);
assert.deepStrictEqual(C.kinds(mm), ['bar', 'stacked', 'hbar', 'line', 'scatter']);

// single value or no dimension: no chart types (UI shows a stat)
assert.deepStrictEqual(C.kinds(sh(['n'], ['n'], [{ n: 1 }])), []);
// several rows but no dimension: rows are numbered on the x axis
const nodim = sh(['n', 'm'], ['n', 'm'], [{ n: 1, m: 2 }, { n: 3, m: 4 }]);
assert.deepStrictEqual(C.kinds(nodim), ['bar', 'stacked', 'hbar', 'line', 'scatter']);
assert.deepStrictEqual(C.prepare(nodim).labels, ['1', '2']);

// no declared metrics (raw SQL, decimals as strings): numeric columns are inferred and coerced
const raw = sh(['program', 'melt_rate'], [], [{ program: 'Q', melt_rate: '0.31' }, { program: 'S', melt_rate: '0.12' }]);
assert.deepStrictEqual(raw.metrics, ['melt_rate']);
assert.deepStrictEqual(raw.rows.map((r) => r.melt_rate), [0.31, 0.12]);
assert.strictEqual(C.kinds(raw)[0], 'bar');
// all-numeric columns: the first stays the x axis
assert.deepStrictEqual(sh(['yr', 'n'], [], [{ yr: 2025, n: 1 }, { yr: 2026, n: 2 }]).metrics, ['n']);
// nothing numeric: no chart
assert.deepStrictEqual(sh(['a', 'b'], [], [{ a: 'x', b: 'y' }, { a: 'z', b: 'w' }]).metrics, []);

// pie only for non-negative values and at most 12 slices
const neg = sh(['k', 'n'], ['n'], [{ k: 'a', n: -1 }, { k: 'b', n: 2 }]);
assert.ok(!C.kinds(neg).includes('pie'));
const many = sh(['k', 'n'], ['n'], Array.from({ length: 13 }, (_, i) => ({ k: 'k' + i, n: i + 1 })));
assert.ok(!C.kinds(many).includes('pie'));

// configs
const cfg = (k, s) => C.config(k, s, PAL);
assert.strictEqual(cfg('bar', cat).type, 'bar');
assert.strictEqual(cfg('hbar', cat).options.indexAxis, 'y');
assert.strictEqual(cfg('line', cat).type, 'line');
assert.strictEqual(cfg('area', time).data.datasets[0].fill, true);
assert.ok(cfg('area', time).data.datasets[0].backgroundColor.endsWith('55'));
assert.strictEqual(cfg('stacked', two).options.scales.x.stacked, true);
assert.strictEqual(cfg('pie', cat).type, 'pie');
assert.strictEqual(cfg('pie', cat).data.datasets[0].backgroundColor.length, 2);
assert.deepStrictEqual(cfg('scatter', mm).data.datasets[0].data, [{ x: 1, y: 2 }, { x: 3, y: 4 }]);
assert.strictEqual(cfg('bar', two).options.plugins.legend.display, true);   // multi-series shows a legend
assert.strictEqual(cfg('bar', cat).options.plugins.legend.display, false);

// friendly metric names: the semantic-layer label when given, else a humanized metric name
const lab = C.shapeOf({ ...ev(['season', 'enrl_students_budget'], ['enrl_students_budget'],
  [{ season: 'Fall', enrl_students_budget: 5 }, { season: 'Summer', enrl_students_budget: 3 }]),
labels: { enrl_students_budget: 'Budgeted enrollment' } });
assert.strictEqual(C.metricLabel(lab, 'enrl_students_budget'), 'Budgeted enrollment');
assert.strictEqual(cfg('bar', lab).data.datasets[0].label, 'Budgeted enrollment');
assert.strictEqual(cfg('pie', lab).data.datasets[0].label, 'Budgeted enrollment');
assert.strictEqual(C.metricLabel(cat, 'enrl_students_budget'), 'Enrl students budget');
// short_label (dbt config.meta) names the metric inside the chart; the full label stays the title
const wk = C.shapeOf({ ...ev(['season', 'asuo_wkly_enrl_students'], ['asuo_wkly_enrl_students'],
  [{ season: 'Fall', asuo_wkly_enrl_students: 5 }, { season: 'Summer', asuo_wkly_enrl_students: 3 }]),
labels: { asuo_wkly_enrl_students: 'ASUO Weekly Enrolled Students' }, short_labels: { asuo_wkly_enrl_students: 'Enrollments' } });
assert.strictEqual(C.metricLabel(wk, 'asuo_wkly_enrl_students'), 'ASUO Weekly Enrolled Students');
assert.strictEqual(cfg('bar', wk).data.datasets[0].label, 'Enrollments');
assert.strictEqual(C.shortLabel(lab, 'enrl_students_budget'), 'Budgeted enrollment');
const twoLab = { ...two, labels: { n: 'Headcount' } };
const tip = cfg('bar', twoLab).options.plugins.tooltip.callbacks.label;
assert.strictEqual(tip({ dataset: { label: 'Q' }, formattedValue: '10' }), 'Q · Headcount: 10');
assert.strictEqual(cfg('scatter', { ...mm, labels: { a: 'Apps' } }).options.scales.x.title.text, 'Apps');

// wantsChart: chart words, or trend / year-over-year wording
for (const q of ['Can you chart that?', 'graph it by program', 'plot it', 'visualize by term', 'and over time?', 'year over year?'])
  assert.ok(C.wantsChart(q), q);
for (const q of ['what about Program S?', 'and for graduate students', '', null]) assert.ok(!C.wantsChart(q), q);

// question intent
for (const q of ['Enrollment year over year', 'Show YoY melt', 'Fall A vs last year', 'how does it compare to the prior year?',
  'same point last year', 'year-on-year growth']) assert.strictEqual(C.intentOf(q), 'yoy', q);
for (const q of ['Enrollment over time', 'melt trend', 'monthly applications', 'enrollment by term', 'over the last 6 weeks'])
  assert.strictEqual(C.intentOf(q), 'trend', q);
for (const q of ['Enrollment by program', 'How many students last year?', '', null]) assert.strictEqual(C.intentOf(q), null, q);

// without a time-series x axis the default is a bar, whatever the wording
assert.deepStrictEqual(C.kinds({ ...cat, intent: 'trend' }), ['bar', 'hbar', 'line', 'pie']);
// weeks/days relative to session start count as a time axis
assert.strictEqual(C.kinds(sh(['term_sess_snp_rel_wk_nbr', 'n'], ['n'],
  [{ term_sess_snp_rel_wk_nbr: -2, n: 1 }, { term_sess_snp_rel_wk_nbr: -1, n: 2 }]))[0], 'line');

// yoy, year dimension + comparison grain: one series per year, common x axis, no stacking; x is not time, so bar
const yy = C.shapeOf(ev(['asuo_term_session__acad_yr', 'asuo_term_session__term_sess_type', 'n'], ['n'], [
  { asuo_term_session__acad_yr: '2026', asuo_term_session__term_sess_type: 'Fall A', n: 12 },
  { asuo_term_session__acad_yr: '2025', asuo_term_session__term_sess_type: 'Fall A', n: 10 },
  { asuo_term_session__acad_yr: '2025', asuo_term_session__term_sess_type: 'Fall B', n: 7 },
  { asuo_term_session__acad_yr: '2026', asuo_term_session__term_sess_type: 'Fall B', n: 8 }]), 'yoy');
const pyy = C.prepare(yy);
assert.deepStrictEqual(pyy.labels, ['Fall A', 'Fall B']);
assert.deepStrictEqual(pyy.datasets.map((d) => [d.label, d.data]), [['2025', [10, 7]], ['2026', [12, 8]]]);
assert.deepStrictEqual(C.kinds(yy), ['bar', 'hbar', 'line']);
// the same rows without yoy intent keep the old layout (first dimension on x)
assert.deepStrictEqual(C.prepare({ ...yy, intent: null }).labels, ['2026', '2025']);

// yoy pacing: weeks relative to session start on x, one series per term ('Fall 2025', 'Fall 2026'), numeric x order
const pace = C.shapeOf(ev(['term_descr', 'rel_wk_nbr', 'n'], ['n'], [
  { term_descr: 'Fall 2025', rel_wk_nbr: 2, n: 5 }, { term_descr: 'Fall 2025', rel_wk_nbr: -1, n: 3 },
  { term_descr: 'Fall 2026', rel_wk_nbr: -1, n: 4 }, { term_descr: 'Fall 2026', rel_wk_nbr: 2, n: 6 }]), 'yoy');
const pp = C.prepare(pace);
assert.deepStrictEqual(pp.labels, ['-1', '2']);
assert.deepStrictEqual(pp.datasets.map((d) => [d.label, d.data]), [['Fall 2025', [3, 5]], ['Fall 2026', [4, 6]]]);
assert.strictEqual(C.kinds(pace)[0], 'line');

// yoy over a monthly date: split into years, months shared on x
const mon = C.shapeOf(ev(['metric_time__month', 'n'], ['n'], [
  { metric_time__month: '2025-01-01T00:00:00', n: 1 }, { metric_time__month: '2025-02-01T00:00:00', n: 2 },
  { metric_time__month: '2026-01-01T00:00:00', n: 3 }, { metric_time__month: '2026-02-01T00:00:00', n: 4 }]), 'yoy');
const pm = C.prepare(mon);
assert.deepStrictEqual(pm.labels, ['Jan', 'Feb']);
assert.strictEqual(C.kinds(mon)[0], 'line');
assert.deepStrictEqual(pm.datasets.map((d) => [d.label, d.data]), [['2025', [1, 2]], ['2026', [3, 4]]]);
assert.strictEqual(C.config('line', mon, PAL).options.plugins.tooltip.callbacks.label(
  { dataset: { label: '2026' }, formattedValue: '3' }), '2026 · N: 3');

// yoy over one year-bearing label: the year becomes the series, the rest the x value
const lab1 = C.prepare(C.shapeOf(ev(['term_sess_descr', 'n'], ['n'], [
  { term_sess_descr: 'Fall A 2025', n: 1 }, { term_sess_descr: 'Fall B 2025', n: 2 },
  { term_sess_descr: 'Fall A 2026', n: 3 }, { term_sess_descr: 'Fall B 2026', n: 4 }]), 'yoy'));
assert.deepStrictEqual(lab1.labels, ['Fall A', 'Fall B']);
assert.deepStrictEqual(lab1.datasets.map((d) => d.label), ['2025', '2026']);

// nothing to split on (a single year, or no year at all): falls back to the normal layout
assert.strictEqual(C.prepare({ ...cat, intent: 'yoy' }).datasets.length, 1);
assert.strictEqual(C.prepare(C.shapeOf(ev(['metric_time__year', 'n'], ['n'], [
  { metric_time__year: '2025-01-01', n: 1 }, { metric_time__year: '2026-01-01', n: 2 }]), 'yoy')).datasets.length, 1);

// every offered kind produces a config
for (const s of [cat, time, two, mm, gap, yy, pace, mon]) for (const k of C.kinds(s)) assert.ok(cfg(k, s).type, k);
console.log('charts ok');
