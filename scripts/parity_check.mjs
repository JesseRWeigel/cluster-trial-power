/**
 * Hold the JavaScript port to the Python engine.
 *
 * The page computes in the browser, so the browser code is a second implementation
 * of a validated engine. Two implementations that have drifted apart mean the page
 * is showing numbers no reference table has ever checked, and nothing else in this
 * repository would notice. So every case dumped by scripts/parity_dump.py is
 * recomputed here and compared.
 *
 * The tolerance is mainly relative, 1e-10, because the quantities span from a design
 * effect near 1 to a sample size near 1e4, and an absolute tolerance would mean
 * something different at each end. It is not 0: the two languages differ in their log
 * gamma (Python uses the C library, this port uses Lanczos) and in their error
 * function, so agreement to the last bit is not available.
 *
 * There is also an absolute floor of 1e-12, and it needs its justification stated.
 * Both implementations of the noncentral t build the answer by adding and subtracting
 * quantities of order one, so their agreement floor is a few hundred units of double
 * precision, about 4e-13 as measured. Below a probability of roughly 1e-4 that floor
 * is larger than 1e-10 relative, and demanding relative agreement there would be
 * demanding agreement below the noise of both. It cannot hide a real defect: a
 * discrepancy of 1e-12 in a probability cannot move a required N by one person, and
 * anything larger in the region that governs a decision, power between 0.001 and
 * 0.999, is still caught by the relative test. The run prints the worst relative
 * disagreement restricted to that region so the margin is visible rather than
 * asserted.
 *
 * usage: node scripts/parity_check.mjs <cases.json>
 */

import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const engine = await import(resolve(HERE, "..", "src", "power.js"));

const TOL = 1e-10;
const ABS_FLOOR = 1e-12;
// The band in which a value can actually change a reported answer.
const DECISION_BAND = 1e-3;

const DISPATCH = {
  normPpf: (a) => engine.normPpf(...a),
  normCdf: (a) => engine.normCdf(...a),
  tPpf: (a) => engine.tPpf(...a),
  tCdf: (a) => engine.tCdf(...a),
  nctCdf: (a) => engine.nctCdf(...a),
  designEffect: (a) => engine.designEffect(...a),
  cohenH: (a) => engine.cohenH(...a),
  proportionSmd: (a) => engine.proportionSmd(...a),
  powerTwoSample: (a) => engine.powerTwoSample(...a),
  nTwoSample: (a) => engine.nTwoSample(...a),
  powerCrt: (a) => engine.powerCrt(...a),
  clustersCrtField: ([field, effect, m, icc, cv, power, alpha, sides, dfRule]) => {
    const res = engine.clustersCrt({ effect, m, icc, cv, power, alpha, sides, dfRule });
    return Number(res[field]);
  },
  powerCurvePoint: ([effect, m, icc, cv, k]) => engine.powerCrt(effect, m, icc, k, cv),
  ocPoint: ([k, m, icc, cv, d]) => (d === 0 ? 0.05 : engine.powerCrt(d, m, icc, k, cv)),
};

const path = process.argv[2];
if (!path) {
  console.error("usage: node scripts/parity_check.mjs <cases.json>");
  process.exit(2);
}

const { cases } = JSON.parse(readFileSync(path, "utf8"));
if (!Array.isArray(cases) || cases.length < 100) {
  console.error(`expected at least 100 parity cases, got ${cases?.length}`);
  process.exit(1);
}

let worst = 0;
let worstCase = null;
let worstDecision = 0;
let worstDecisionCase = null;
let worstAbsolute = 0;
const failures = [];
const byFn = new Map();

for (const testCase of cases) {
  const fn = DISPATCH[testCase.fn];
  if (!fn) {
    failures.push(`${testCase.fn}: no javascript counterpart, cannot check`);
    continue;
  }
  let got;
  try {
    got = fn(testCase.args);
  } catch (err) {
    failures.push(`${testCase.fn}(${testCase.args}) threw: ${err.message}`);
    continue;
  }
  const expected = testCase.expected;
  const absolute = Math.abs(got - expected);
  const denom = Math.abs(expected) > 1e-12 ? Math.abs(expected) : 1;
  const rel = absolute / denom;
  byFn.set(testCase.fn, Math.max(byFn.get(testCase.fn) ?? 0, rel));
  worstAbsolute = Math.max(worstAbsolute, absolute);
  if (rel > worst) {
    worst = rel;
    worstCase = `${testCase.fn}(${testCase.args}) python=${expected} js=${got}`;
  }
  if (Math.abs(expected) >= DECISION_BAND && rel > worstDecision) {
    worstDecision = rel;
    worstDecisionCase = `${testCase.fn}(${testCase.args}) python=${expected} js=${got}`;
  }
  if (!(absolute <= ABS_FLOOR || rel <= TOL)) {
    failures.push(`${testCase.fn}(${testCase.args}): python ${expected}, js ${got}, `
      + `rel ${rel.toExponential(3)}, abs ${absolute.toExponential(3)}`);
  }
}

const names = [...byFn.keys()].sort();
for (const name of names) {
  console.log(`  ${name.padEnd(20)} worst relative difference ${byFn.get(name).toExponential(2)}`);
}
console.log(`parity cases: ${cases.length}, functions: ${names.length}, `
  + `tolerance rel ${TOL} or abs ${ABS_FLOOR}`);
console.log(`worst relative anywhere:            ${worst.toExponential(3)}  (${worstCase})`);
console.log(`worst relative above ${DECISION_BAND}:          ${worstDecision.toExponential(3)}  (${worstDecisionCase})`);
console.log(`worst absolute anywhere:            ${worstAbsolute.toExponential(3)}`);

if (failures.length) {
  console.error(`PARITY FAILED: ${failures.length}`);
  for (const failure of failures.slice(0, 25)) console.error(`  - ${failure}`);
  process.exit(1);
}
console.log("parity check PASSED");
