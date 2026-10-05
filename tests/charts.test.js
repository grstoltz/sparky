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
assert.deepStrictEqual(C.kinds(sh(['n', 'm'], ['n', 'm'], [{ n: 1, m: 2 }, { n: 3, m: 4 }])), []);

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

// every offered kind produces a config
for (const s of [cat, time, two, mm, gap]) for (const k of C.kinds(s)) assert.ok(cfg(k, s).type, k);
console.log('charts ok');
