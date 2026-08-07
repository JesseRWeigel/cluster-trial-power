/**
 * Cluster trial power, a direct port of src/power.py and src/distributions.py.
 *
 * The page has to compute in the browser, and pulling a statistics library over a
 * CDN for a page that must work offline was not worth it. So this is a hand port,
 * and scripts/parity_check.mjs holds it to the Python engine over a grid of several
 * hundred cases at a relative tolerance of 1e-10. A port that has drifted from the
 * validated engine is worse than no port, because the page would then be showing
 * numbers no reference table has ever seen.
 *
 * Every routine below has the same name as its Python counterpart. Where the two
 * differ at all, the Python one is the reference.
 */

// --------------------------------------------------------------------------
// gamma
// --------------------------------------------------------------------------

const LANCZOS = [
  676.5203681218851, -1259.1392167224028, 771.32342877765313,
  -176.61502916214059, 12.507343278686905, -0.13857109526572012,
  9.9843695780195716e-6, 1.5056327351493116e-7,
];

/** Log gamma by the Lanczos approximation, g = 7, n = 9. About 1e-15 relative. */
export function lgamma(x) {
  if (x < 0.5) {
    // reflection: Gamma(x) Gamma(1-x) = pi / sin(pi x)
    return Math.log(Math.PI / Math.abs(Math.sin(Math.PI * x))) - lgamma(1.0 - x);
  }
  const z = x - 1.0;
  let a = 0.99999999999980993;
  for (let i = 0; i < LANCZOS.length; i += 1) a += LANCZOS[i] / (z + i + 1);
  const t = z + LANCZOS.length - 0.5;
  return 0.5 * Math.log(2 * Math.PI) + (z + 0.5) * Math.log(t) - t + Math.log(a);
}

// --------------------------------------------------------------------------
// normal
// --------------------------------------------------------------------------

/** Abramowitz and Stegun 7.1.26 is not accurate enough here, so erfc is built up
 *  from a continued fraction in the tail and a series near the origin. */
function erf(x) {
  const ax = Math.abs(x);
  if (ax < 2.0) {
    // series: erf(x) = 2/sqrt(pi) sum_{n>=0} (-1)^n x^(2n+1) / (n! (2n+1))
    let term = x;
    let sum = x;
    for (let n = 1; n < 200; n += 1) {
      term *= (-x * x) / n;
      const add = term / (2 * n + 1);
      sum += add;
      if (Math.abs(add) < 1e-18 * Math.abs(sum)) break;
    }
    return (2 / Math.sqrt(Math.PI)) * sum;
  }
  return x > 0 ? 1 - erfc(x) : erfc(-x) - 1;
}

/** Complementary error function, Lentz continued fraction for |x| >= 2. */
function erfc(x) {
  if (x < 0) return 2 - erfc(-x);
  if (x < 2.0) return 1 - erf(x);
  // erfc(x) = exp(-x^2)/(x sqrt(pi)) * 1/(1 + 1/(2x^2)/(1 + 2/(2x^2)/(1 + ...)))
  const xx = x * x;
  let f = 0.0;
  for (let n = 60; n >= 1; n -= 1) f = (n / 2) / (x + f);
  return Math.exp(-xx) / (Math.sqrt(Math.PI) * (x + f));
}

export function normCdf(x) {
  return 0.5 * erfc(-x / Math.SQRT2);
}

const A = [3.3871328727963666080e0, 1.3314166789178437745e2, 1.9715909503065514427e3,
  1.3731693765509461125e4, 4.5921953931549871457e4, 6.7265770927008700853e4,
  3.3430575583588128105e4, 2.5090809287301226727e3];
const B = [1.0, 4.2313330701600911252e1, 6.8718700749205790830e2, 5.3941960214247511077e3,
  2.1213794301586595867e4, 3.9307895800092710610e4, 2.8729085735721942674e4,
  5.2264952788528545610e3];
const C = [1.42343711074968357734e0, 4.63033784615654529590e0, 5.76949722146069140550e0,
  3.64784832476320460504e0, 1.27045825245236838258e0, 2.41780725177450611770e-1,
  2.27238449892691845833e-2, 7.74545014278341407640e-4];
const D = [1.0, 2.05319162663775882187e0, 1.67638483018380384940e0, 6.89767334985100004550e-1,
  1.48103976427480074590e-1, 1.51986665636164571966e-2, 5.47593808499534494600e-4,
  1.05075007164441684324e-9];
const E = [6.65790464350110377720e0, 5.46378491116411436990e0, 1.78482653991729133580e0,
  2.96560571828504891230e-1, 2.65321895265761230930e-2, 1.24266094738807843860e-3,
  2.71155556874348757815e-5, 2.01033439929228813265e-7];
const F = [1.0, 5.99832206555887937690e-1, 1.36929880922735805310e-1, 1.48753612908506148525e-2,
  7.86869131145613259100e-4, 1.84631831751005468180e-5, 1.42151175831644588870e-7,
  2.04426310338993978564e-15];

function poly8(coef, r) {
  let out = 0.0;
  for (let i = coef.length - 1; i >= 0; i -= 1) out = out * r + coef[i];
  return out;
}

/** Wichura (1988) AS 241, PPND16. */
export function normPpf(p) {
  if (!(p > 0 && p < 1)) throw new Error(`normPpf needs 0 < p < 1, got ${p}`);
  const q = p - 0.5;
  if (Math.abs(q) <= 0.425) {
    const r = 0.180625 - q * q;
    return (q * poly8(A, r)) / poly8(B, r);
  }
  let r = q < 0 ? p : 1 - p;
  r = Math.sqrt(-Math.log(r));
  let value;
  if (r <= 5.0) {
    r -= 1.6;
    value = poly8(C, r) / poly8(D, r);
  } else {
    r -= 5.0;
    value = poly8(E, r) / poly8(F, r);
  }
  return q < 0 ? -value : value;
}

// --------------------------------------------------------------------------
// incomplete beta, Student t
// --------------------------------------------------------------------------

const FPMIN = 1e-300;

function betacf(a, b, x) {
  const qab = a + b;
  const qap = a + 1.0;
  const qam = a - 1.0;
  let c = 1.0;
  let d = 1.0 - (qab * x) / qap;
  if (Math.abs(d) < FPMIN) d = FPMIN;
  d = 1.0 / d;
  let h = d;
  for (let m = 1; m <= 500; m += 1) {
    const m2 = 2 * m;
    let aa = (m * (b - m) * x) / ((qam + m2) * (a + m2));
    d = 1.0 + aa * d;
    if (Math.abs(d) < FPMIN) d = FPMIN;
    c = 1.0 + aa / c;
    if (Math.abs(c) < FPMIN) c = FPMIN;
    d = 1.0 / d;
    h *= d * c;
    aa = (-(a + m) * (qab + m) * x) / ((a + m2) * (qap + m2));
    d = 1.0 + aa * d;
    if (Math.abs(d) < FPMIN) d = FPMIN;
    c = 1.0 + aa / c;
    if (Math.abs(c) < FPMIN) c = FPMIN;
    d = 1.0 / d;
    const delta = d * c;
    h *= delta;
    if (Math.abs(delta - 1.0) < 3e-16) return h;
  }
  throw new Error(`incomplete beta did not converge for a=${a} b=${b} x=${x}`);
}

export function betainc(a, b, x) {
  if (x <= 0) return 0;
  if (x >= 1) return 1;
  const lnFront = lgamma(a + b) - lgamma(a) - lgamma(b) + a * Math.log(x) + b * Math.log1p(-x);
  if (x < (a + 1.0) / (a + b + 2.0)) return (Math.exp(lnFront) * betacf(a, b, x)) / a;
  const lnBack = lgamma(a + b) - lgamma(a) - lgamma(b) + b * Math.log1p(-x) + a * Math.log(x);
  return 1.0 - (Math.exp(lnBack) * betacf(b, a, 1.0 - x)) / b;
}

export function tCdf(t, df) {
  if (df <= 0) throw new Error(`tCdf needs df > 0, got ${df}`);
  if (t === 0) return 0.5;
  const tt = t * t;
  if (tt < df) {
    const half = 0.5 * betainc(0.5, 0.5 * df, tt / (tt + df));
    return t > 0 ? 0.5 + half : 0.5 - half;
  }
  const tail = 0.5 * betainc(0.5 * df, 0.5, df / (df + tt));
  return t > 0 ? 1.0 - tail : tail;
}

export function tPpf(p, df) {
  if (!(p > 0 && p < 1)) throw new Error(`tPpf needs 0 < p < 1, got ${p}`);
  if (df <= 0) throw new Error(`tPpf needs df > 0, got ${df}`);
  let lo = -1e6;
  let hi = 1e6;
  for (let i = 0; i < 200; i += 1) {
    const mid = 0.5 * (lo + hi);
    if (tCdf(mid, df) < p) lo = mid; else hi = mid;
    if (hi - lo < 1e-13 * Math.max(1.0, Math.abs(lo))) break;
  }
  return 0.5 * (lo + hi);
}

// --------------------------------------------------------------------------
// noncentral t
// --------------------------------------------------------------------------

function nctSeries(t, df, ncp) {
  const x = (t * t) / (t * t + df);
  if (x <= 0) return normCdf(-ncp);
  const halfD2 = 0.5 * ncp * ncp;
  let p = Math.exp(-halfD2);
  let q = Math.sqrt(2 / Math.PI) * ncp * Math.exp(-halfD2);
  const a = 0.5;
  const b = 0.5 * df;
  let ibetaP = betainc(a, b, x);
  let ibetaQ = betainc(a + 0.5, b, x);
  const stepTerm = (av) => Math.exp(
    lgamma(av + b) - lgamma(av + 1.0) - lgamma(b) + av * Math.log(x) + b * Math.log1p(-x),
  );
  let termP = stepTerm(a);
  let termQ = stepTerm(a + 0.5);
  let total = 0.0;
  let converged = false;
  for (let j = 0; j < 1000; j += 1) {
    total += p * ibetaP + q * ibetaQ;
    if (j > halfD2 && (p + q) * (ibetaP + ibetaQ) < 1e-17) { converged = true; break; }
    ibetaP -= termP;
    ibetaQ -= termQ;
    termP *= (x * (a + b + j)) / (a + j + 1.0);
    termQ *= (x * (a + 0.5 + b + j)) / (a + 1.5 + j);
    p *= halfD2 / (j + 1.0);
    q *= halfD2 / (j + 1.5);
  }
  if (!converged) throw new Error(`AS 243 series did not converge, t=${t} df=${df} ncp=${ncp}`);
  return Math.min(1, Math.max(0, normCdf(-ncp) + 0.5 * total));
}

function gaussLegendre(n) {
  const nodes = [];
  const weights = [];
  for (let i = 1; i <= n; i += 1) {
    let x = Math.cos((Math.PI * (i - 0.25)) / (n + 0.5));
    let dp = 0;
    for (let it = 0; it < 100; it += 1) {
      let p0 = 1.0;
      let p1 = 0.0;
      for (let j = 1; j <= n; j += 1) {
        const p2 = p1;
        p1 = p0;
        p0 = ((2 * j - 1) * x * p1 - (j - 1) * p2) / j;
      }
      dp = (n * (x * p0 - p1)) / (x * x - 1);
      const dx = -p0 / dp;
      x += dx;
      if (Math.abs(dx) < 1e-15) break;
    }
    nodes.push(x);
    weights.push(2 / ((1 - x * x) * dp * dp));
  }
  return { nodes, weights };
}

const GL = gaussLegendre(128);

export function chiPdf(u, df) {
  if (u <= 0) return 0;
  return Math.exp((df - 1) * Math.log(u) - 0.5 * u * u
    - (0.5 * df - 1) * Math.LN2 - lgamma(0.5 * df));
}

function nctQuadrature(t, df, ncp) {
  const mean = Math.SQRT2 * Math.exp(lgamma(0.5 * (df + 1)) - lgamma(0.5 * df));
  const sd = Math.sqrt(Math.max(df - mean * mean, 1e-12));
  const lo = Math.max(1e-12, mean - 14 * sd);
  const hi = mean + 14 * sd;
  const half = 0.5 * (hi - lo);
  const mid = 0.5 * (hi + lo);
  const scale = t / Math.sqrt(df);
  let total = 0;
  for (let i = 0; i < GL.nodes.length; i += 1) {
    const u = mid + half * GL.nodes[i];
    total += GL.weights[i] * chiPdf(u, df) * normCdf(scale * u - ncp);
  }
  return Math.min(1, Math.max(0, half * total));
}

export function nctCdf(t, df, ncp, method = "auto") {
  if (df <= 0) throw new Error(`nctCdf needs df > 0, got ${df}`);
  if (method === "quadrature") return nctQuadrature(t, df, ncp);
  if (method === "auto" && Math.abs(ncp) > 12) return nctQuadrature(t, df, ncp);
  const value = t >= 0 ? nctSeries(t, df, ncp) : 1 - nctSeries(-t, df, -ncp);
  // See src/distributions.py: below 1e-8 the AS 243 series has lost its relative
  // accuracy to cancellation, and the quadrature has not. Same rule in both ports.
  if (method === "auto" && value < 1e-8) return nctQuadrature(t, df, ncp);
  return value;
}

// --------------------------------------------------------------------------
// design effect and power
// --------------------------------------------------------------------------

export function designEffect(m, icc, cv = 0.0, model = "eldridge") {
  if (!(m > 0)) throw new Error(`cluster size must be positive, got ${m}`);
  if (!(icc >= 0 && icc <= 1)) throw new Error(`icc must lie in [0, 1], got ${icc}`);
  if (!(cv >= 0)) throw new Error(`cv must be non-negative, got ${cv}`);
  if (model === "kish") return 1 + (m - 1) * icc;
  if (model !== "eldridge") throw new Error(`unknown design effect model ${model}`);
  return 1 + ((1 + cv * cv) * m - 1) * icc;
}

export function deffShorthandRatio(m, icc, cv) {
  const equal = designEffect(m, icc, 0);
  const exact = designEffect(m, icc, cv);
  const shorthand = equal * (1 + cv * cv);
  return {
    deff_equal_sizes: equal,
    deff_unequal_sizes: exact,
    deff_shorthand: shorthand,
    exact_over_equal: exact / equal,
    shorthand_over_equal: shorthand / equal,
    shorthand_error: shorthand - exact,
  };
}

export function cohenH(p1, p2) {
  return 2 * Math.asin(Math.sqrt(p1)) - 2 * Math.asin(Math.sqrt(p2));
}

export function proportionSmd(p1, p2) {
  const pbar = 0.5 * (p1 + p2);
  const v = pbar * (1 - pbar);
  if (v <= 0) throw new Error("no effect is defined when both proportions are 0 or both are 1");
  return (p1 - p2) / Math.sqrt(v);
}

function criticalAlpha(alpha, sides) {
  if (!(alpha > 0 && alpha < 1)) throw new Error(`alpha must lie in (0, 1), got ${alpha}`);
  if (sides !== 1 && sides !== 2) throw new Error(`sides must be 1 or 2, got ${sides}`);
  return alpha / sides;
}

export function powerTwoSample(effect, nPerArm, alpha = 0.05, sides = 2, method = "t") {
  if (nPerArm <= 1) return alpha / sides;
  const tail = criticalAlpha(alpha, sides);
  const ncp = Math.abs(effect) * Math.sqrt(nPerArm / 2);
  if (method === "normal") {
    const crit = normPpf(1 - tail);
    let pw = 1 - normCdf(crit - ncp);
    if (sides === 2) pw += normCdf(-crit - ncp);
    return pw;
  }
  if (method !== "t") throw new Error(`unknown method ${method}`);
  const df = 2 * nPerArm - 2;
  const crit = tPpf(1 - tail, df);
  let pw = 1 - nctCdf(crit, df, ncp);
  if (sides === 2) pw += nctCdf(-crit, df, ncp);
  return pw;
}

function solveIncreasing(f, target, lo, hi) {
  if (f(lo) >= target) return lo;
  if (f(hi) < target) throw new Error(`target ${target} not reachable on [${lo}, ${hi}]`);
  for (let i = 0; i < 300; i += 1) {
    const mid = 0.5 * (lo + hi);
    if (f(mid) < target) lo = mid; else hi = mid;
    if (hi - lo <= 1e-10 * Math.max(1, Math.abs(lo))) break;
  }
  return 0.5 * (lo + hi);
}

export function nTwoSample(effect, power = 0.8, alpha = 0.05, sides = 2, method = "t") {
  if (!(power > 0 && power < 1)) throw new Error(`power must lie in (0, 1), got ${power}`);
  if (effect === 0) throw new Error("an effect size of zero needs an infinite sample");
  if (method === "normal") {
    const za = normPpf(1 - criticalAlpha(alpha, sides));
    const zb = normPpf(power);
    return (2 * (za + zb) ** 2) / (effect * effect);
  }
  return solveIncreasing(
    (n) => powerTwoSample(effect, n, alpha, sides, method), power, 2 + 1e-9, 1e7,
  );
}

export function effectiveNPerArm(kPerArm, m, icc, cv = 0, deffModel = "eldridge") {
  return (kPerArm * m) / designEffect(m, icc, cv, deffModel);
}

export function powerCrt(effect, m, icc, kPerArm, cv = 0, alpha = 0.05, sides = 2,
  dfRule = "cluster_t", deffModel = "eldridge") {
  if (!(kPerArm > 0)) throw new Error(`clusters per arm must be positive, got ${kPerArm}`);
  const nEff = effectiveNPerArm(kPerArm, m, icc, cv, deffModel);
  const tail = criticalAlpha(alpha, sides);
  const ncp = Math.abs(effect) * Math.sqrt(nEff / 2);
  if (dfRule === "normal") {
    const crit = normPpf(1 - tail);
    let pw = 1 - normCdf(crit - ncp);
    if (sides === 2) pw += normCdf(-crit - ncp);
    return pw;
  }
  let df;
  if (dfRule === "cluster_t") df = 2 * kPerArm - 2;
  else if (dfRule === "individual_t") df = 2 * kPerArm * m - 2;
  else throw new Error(`unknown df rule ${dfRule}`);
  if (df <= 0) throw new Error(`df rule ${dfRule} gives ${df} degrees of freedom at k=${kPerArm}`);
  const crit = tPpf(1 - tail, df);
  let pw = 1 - nctCdf(crit, df, ncp);
  if (sides === 2) pw += nctCdf(-crit, df, ncp);
  return pw;
}

export function clustersCrt(opts) {
  const {
    effect, m, icc, cv = 0, power = 0.8, alpha = 0.05, sides = 2,
    dfRule = "cluster_t", deffModel = "eldridge", effectKind = "d",
    maxClustersPerArm = 100000,
  } = opts;
  if (m < 1) throw new Error(`cluster size must be at least 1, got ${m}`);
  const deff = designEffect(m, icc, cv, deffModel);
  const nInd = nTwoSample(effect, power, alpha, sides, dfRule === "normal" ? "normal" : "t");
  const powerAt = (k) => powerCrt(effect, m, icc, k, cv, alpha, sides, dfRule, deffModel);
  let k = Math.max(2, Math.floor((nInd * deff) / m));
  while (k <= maxClustersPerArm && powerAt(k) < power) k += 1;
  if (k > maxClustersPerArm) {
    throw new Error(`target power ${power} needs more than ${maxClustersPerArm} clusters per arm`);
  }
  while (k > 2 && powerAt(k - 1) >= power) k -= 1;

  const notes = [];
  if (k < 15) {
    notes.push(`${2 * k} clusters in total is few. Below about 30 the t correction matters `
      + "and covariate imbalance between arms is likely; consider stratified or matched allocation.");
  }
  if (icc === 0) {
    notes.push("ICC is exactly 0, so the design effect is 1 and the answer equals the "
      + "individually randomised requirement.");
  }
  if (cv > 0) {
    notes.push("Unequal cluster sizes are accounted for through the Eldridge et al. (2006) "
      + "design effect. Assuming equal sizes would understate the requirement.");
  }
  if (m > 1 && icc > 0) {
    notes.push("Adding people to existing clusters cannot push effective sample size per arm "
      + `above k/ICC = ${(k / icc).toFixed(1)}. More clusters is the only way past that.`);
  }

  return {
    effect,
    effect_kind: effectKind,
    target_power: power,
    alpha,
    sides,
    icc,
    cluster_size: m,
    cv_cluster_size: cv,
    df_rule: dfRule,
    deff_model: deffModel,
    design_effect: deff,
    design_effect_equal_sizes: designEffect(m, icc, 0, deffModel),
    clusters_per_arm: k,
    clusters_total: 2 * k,
    individuals_per_arm: Math.ceil(k * m),
    individuals_total: Math.ceil(2 * k * m),
    effective_n_per_arm: effectiveNPerArm(k, m, icc, cv, deffModel),
    achieved_power: powerAt(k),
    degrees_of_freedom: dfRule === "normal"
      ? null : (dfRule === "cluster_t" ? 2 * k - 2 : 2 * k * m - 2),
    n_individually_randomised_per_arm: nInd,
    n_individually_randomised_total: Math.ceil(2 * nInd),
    inflation_vs_individual: (2 * k * m) / (2 * nInd),
    cost_of_assuming_equal_clusters: deffShorthandRatio(m, icc, cv),
    notes,
  };
}

export function powerCurveClusters(effect, m, icc, cv = 0, alpha = 0.05, sides = 2,
  dfRule = "cluster_t", deffModel = "eldridge", kMin = 2, kMax = 60) {
  const out = [];
  for (let k = kMin; k <= kMax; k += 1) {
    out.push({
      k_per_arm: k,
      individuals_total: Math.ceil(2 * k * m),
      power: powerCrt(effect, m, icc, k, cv, alpha, sides, dfRule, deffModel),
    });
  }
  return out;
}

export function operatingCharacteristic(kPerArm, m, icc, cv = 0, alpha = 0.05, sides = 2,
  dfRule = "cluster_t", deffModel = "eldridge", effectMin = 0, effectMax = 1, points = 101) {
  const out = [];
  for (let i = 0; i < points; i += 1) {
    const d = effectMin + ((effectMax - effectMin) * i) / (points - 1);
    const pw = d === 0 ? alpha : powerCrt(d, m, icc, kPerArm, cv, alpha, sides, dfRule, deffModel);
    out.push({ effect: d, power: pw, accept_null: 1 - pw });
  }
  return out;
}
