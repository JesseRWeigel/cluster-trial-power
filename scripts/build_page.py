#!/usr/bin/env python3
"""Generate docs/index.html from the engine and the reference table.

The page is not hand maintained. Its worked numbers come from the Python engine, its
validation table comes from reference/reference_values.json, and its calculator is
src/power.js inlined verbatim. scripts/verify.sh rebuilds it into a temporary file
and diffs, so a page that has drifted from the code is a failed verify rather than a
thing somebody notices six months later.

Nothing here writes a timestamp or any other value that changes between runs. A
generator whose output differs on every run cannot be checked by diffing.

  python3 scripts/build_page.py                 # write docs/index.html
  python3 scripts/build_page.py /tmp/page.html  # write somewhere else, for the diff
"""

from __future__ import annotations

import html
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

import power as P  # noqa: E402

DEFAULT_OUT = os.path.join(ROOT, "docs", "index.html")
ENGINE = os.path.join(ROOT, "src", "power.js")
REFERENCE = os.path.join(ROOT, "reference", "reference_values.json")

PROVENANCE_LABEL = {
    "published_table": "published table",
    "published_package_output": "published package output",
    "exact_arithmetic": "exact arithmetic",
    "structural_identity": "structural identity",
    "pinned_regression": "pinned regression",
}


def worked_numbers() -> dict:
    """The numbers the prose quotes, computed rather than typed."""
    headline = P.clusters_crt(0.2, 30, 0.05, power=0.8)
    optimistic = P.clusters_crt(0.3, 25, 0.05, power=0.8)
    truth = P.power_crt(0.2, 25, 0.05, optimistic.clusters_per_arm)
    cv_cost = P.deff_shorthand_ratio(30, 0.05, 0.65)
    return {
        "deff_30_005": P.design_effect(30, 0.05),
        "n_individual_200": 200,
        "n_cluster_200": round(200 * P.design_effect(30, 0.05)),
        "headline_clusters": headline.clusters_per_arm,
        "headline_individuals": headline.individuals_total,
        "headline_individual_only": headline.n_individually_randomised_total,
        "optimistic_clusters": optimistic.clusters_per_arm,
        "optimistic_power_if_wrong": truth,
        "cv_exact": cv_cost["deff_unequal_sizes"],
        "cv_equal": cv_cost["deff_equal_sizes"],
        "cv_shorthand": cv_cost["deff_shorthand"],
    }


def reference_rows() -> list:
    with open(REFERENCE) as fh:
        data = json.load(fh)
    rows = []
    for row in data["values"]:
        rows.append({
            "id": row["id"],
            "expected": row["expected"],
            "provenance": PROVENANCE_LABEL[row["provenance"]],
            "source": row["source"],
        })
    return rows


def render_reference_table(rows: list) -> str:
    counts = {}
    for row in rows:
        counts[row["provenance"]] = counts.get(row["provenance"], 0) + 1
    summary = ", ".join(f"{count} {name}" for name, count in sorted(counts.items()))
    body = "\n".join(
        "        <tr><td><code>{}</code></td><td class=\"num\">{}</td>"
        "<td>{}</td><td>{}</td></tr>".format(
            html.escape(row["id"]),
            html.escape(f"{row['expected']:.10g}"),
            html.escape(row["provenance"]),
            html.escape(row["source"]),
        )
        for row in rows
    )
    return (
        f"      <p class=\"muted\">{len(rows)} reference values: {summary}. "
        "Every one is checked by <code>scripts/check_reference.py</code>, which also "
        "runs 13 deliberately wrong calculations and requires the same tolerances to "
        "reject all of them.</p>\n"
        "      <div class=\"scroller\">\n"
        "      <table>\n"
        "        <thead><tr><th>case</th><th class=\"num\">expected</th>"
        "<th>provenance</th><th>source</th></tr></thead>\n"
        "        <tbody>\n" + body + "\n        </tbody>\n      </table>\n      </div>"
    )


TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Cluster trial power calculator</title>
<meta name="description" content="Sample size for a cluster randomised trial: effect
size, cluster size and ICC in, required number of clusters and individuals out, with
the operating characteristic curve.">
<style>
:root {
  --ink: #14181d;
  --muted: #5b6672;
  --line: #d8dee6;
  --bg: #ffffff;
  --panel: #f6f8fa;
  --accent: #1f5f8b;
  --warn: #9a3412;
  --grid: #e6ebf1;
}
@media (prefers-color-scheme: dark) {
  :root {
    --ink: #e7edf3; --muted: #9aa7b4; --line: #2c343d; --bg: #10141a;
    --panel: #171d25; --accent: #6cb6e8; --warn: #f0a878; --grid: #232b34;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--bg); color: var(--ink);
  font: 16px/1.55 ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
}
main { max-width: 60rem; margin: 0 auto; padding: 1.5rem 1rem 4rem; }
h1 { font-size: 1.6rem; line-height: 1.2; margin: 0 0 .35rem; letter-spacing: -.01em; }
h2 { font-size: 1.15rem; margin: 2.25rem 0 .6rem; letter-spacing: -.01em; }
h3 { font-size: .95rem; margin: 1.25rem 0 .4rem; }
p { margin: .6rem 0; }
.lede { color: var(--muted); max-width: 46rem; }
.muted { color: var(--muted); font-size: .875rem; }
code { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: .9em; }
a { color: var(--accent); }
.grid { display: grid; grid-template-columns: minmax(0, 20rem) minmax(0, 1fr); gap: 1.25rem; }
@media (max-width: 46rem) { .grid { grid-template-columns: minmax(0, 1fr); } }
form { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 1rem; }
fieldset { border: 0; margin: 0 0 .9rem; padding: 0; min-inline-size: 0; }
legend { padding: 0; font-size: .8rem; text-transform: uppercase; letter-spacing: .06em;
  color: var(--muted); margin-bottom: .35rem; }
label { display: block; font-size: .875rem; margin: .5rem 0 .15rem; }
input, select {
  width: 100%; max-width: 100%; padding: .4rem .5rem; font: inherit; color: var(--ink);
  background: var(--bg); border: 1px solid var(--line); border-radius: 5px;
}
.row { display: grid; grid-template-columns: 1fr 1fr; gap: .5rem; }
.answer { border: 1px solid var(--line); border-radius: 8px; padding: 1rem; }
.headline { font-size: 2.4rem; line-height: 1.05; font-variant-numeric: tabular-nums;
  letter-spacing: -.02em; margin: .1rem 0; }
.headline small { display: block; font-size: .8rem; font-weight: 400; color: var(--muted);
  letter-spacing: 0; }
.figs { display: grid; grid-template-columns: repeat(auto-fit, minmax(8.5rem, 1fr)); gap: .75rem;
  margin: 1rem 0 0; }
.fig { border-top: 2px solid var(--line); padding-top: .4rem; }
.fig b { display: block; font-size: 1.25rem; font-variant-numeric: tabular-nums; }
.fig span { font-size: .8rem; color: var(--muted); }
.warn { color: var(--warn); }
ul.notes { margin: .9rem 0 0; padding-left: 1.1rem; font-size: .875rem; color: var(--muted); }
ul.notes li { margin: .3rem 0; }
figure { margin: 1.25rem 0 0; }
figcaption { font-size: .8rem; color: var(--muted); margin-top: .35rem; }
svg { display: block; width: 100%; height: auto; }
.scroller { overflow-x: auto; }
table { border-collapse: collapse; font-size: .8rem; min-width: 34rem; }
th, td { text-align: left; padding: .3rem .6rem .3rem 0; border-bottom: 1px solid var(--line);
  white-space: nowrap; }
th { color: var(--muted); font-weight: 600; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
.err { color: var(--warn); font-size: .875rem; }
footer { margin-top: 3rem; padding-top: 1rem; border-top: 1px solid var(--line);
  font-size: .8rem; color: var(--muted); }
</style>
</head>
<body>
<main>
  <h1>Cluster trial power calculator</h1>
  <p class="lede">Effect size, cluster size and intracluster correlation in. Required
  number of clusters and individuals out, with the curve of power against design size
  and the operating characteristic against the true effect. Everything is computed in
  the page; nothing is sent anywhere.</p>

  <div class="grid">
    <form id="inputs" autocomplete="off">
      <fieldset>
        <legend>Effect</legend>
        <label for="kind">Effect size type</label>
        <select id="kind">
          <option value="d">Cohen's d / standardised mean difference</option>
          <option value="cohen_h">Two proportions, Cohen's arcsine h</option>
          <option value="proportion_difference">Two proportions, difference over pooled SD</option>
        </select>
        <div id="dwrap">
          <label for="effect">Effect size</label>
          <input id="effect" type="number" value="0.2" step="0.01" min="0.001">
        </div>
        <div id="pwrap" class="row" hidden>
          <div><label for="p1">Proportion, treated</label>
            <input id="p1" type="number" value="0.55" step="0.01" min="0" max="1"></div>
          <div><label for="p2">Proportion, control</label>
            <input id="p2" type="number" value="0.45" step="0.01" min="0" max="1"></div>
        </div>
      </fieldset>
      <fieldset>
        <legend>Clustering</legend>
        <div class="row">
          <div><label for="m">Average cluster size</label>
            <input id="m" type="number" value="30" step="1" min="1"></div>
          <div><label for="icc">ICC</label>
            <input id="icc" type="number" value="0.05" step="0.005" min="0" max="1"></div>
        </div>
        <label for="cv">Coefficient of variation of cluster size</label>
        <input id="cv" type="number" value="0" step="0.05" min="0">
      </fieldset>
      <fieldset>
        <legend>Test</legend>
        <div class="row">
          <div><label for="power">Target power</label>
            <input id="power" type="number" value="0.8" step="0.05" min="0.05" max="0.999"></div>
          <div><label for="alpha">Alpha</label>
            <input id="alpha" type="number" value="0.05" step="0.01" min="0.001" max="0.5"></div>
        </div>
        <label for="sides">Sidedness</label>
        <select id="sides">
          <option value="2">Two sided</option>
          <option value="1">One sided</option>
        </select>
        <label for="dfrule">Reference distribution</label>
        <select id="dfrule">
          <option value="cluster_t">t on (total clusters - 2) df</option>
          <option value="normal">Normal approximation</option>
        </select>
      </fieldset>
      <p class="muted" id="err" role="status" aria-live="polite"></p>
    </form>

    <section class="answer" aria-labelledby="answer-heading">
      <h2 id="answer-heading" style="margin-top:0">Required size</h2>
      <div class="headline"><span id="k-total">-</span>
        <small>clusters in total, <span id="k-arm">-</span> per arm</small></div>
      <div class="headline"><span id="n-total">-</span>
        <small>individuals in total, at <span id="m-echo">-</span> per cluster</small></div>
      <div class="figs">
        <div class="fig"><b id="deff">-</b><span>design effect</span></div>
        <div class="fig"><b id="neff">-</b><span>effective n per arm</span></div>
        <div class="fig"><b id="achieved">-</b><span>power achieved</span></div>
        <div class="fig"><b id="df">-</b><span>degrees of freedom</span></div>
      </div>
      <p class="muted" id="comparison"></p>
      <ul class="notes" id="notes"></ul>
    </section>
  </div>

  <h2>Power against the size of the trial</h2>
  <figure>
    <svg id="chart-power" viewBox="0 0 720 320" role="img"
         aria-label="Power rising with the number of clusters per arm"></svg>
    <figcaption>Power against clusters per arm, at the effect size you entered. The
    marker is the smallest design that reaches the target. Adding people to existing
    clusters moves this curve far less than adding clusters does.</figcaption>
  </figure>

  <h2>Operating characteristic</h2>
  <figure>
    <svg id="chart-oc" viewBox="0 0 720 320" role="img"
         aria-label="Power and the probability of not rejecting, against the true effect size"></svg>
    <figcaption>For the design above, held fixed, against the true effect size. The
    upper curve is power, the lower one is the probability of failing to reject, which
    is the operating characteristic in its strict sense. At a true effect of zero the
    curve passes through alpha, and the vertical line marks the effect you assumed.
    Read the gap between them as the cost of being optimistic.</figcaption>
  </figure>

  <h2>What this cannot tell you</h2>
  <p>It assumes the effect size you supplied is the true one. That is the whole
  calculation, and it is the part nobody can check in advance. A trial powered at 80
  percent for an effect of 0.3 has about
  <b id="optimism">__OPTIMISM__ percent</b> power if the real effect is 0.2, so an
  optimistic guess does not produce a slightly smaller study, it produces a study
  likely to miss a real effect. Where a plausible range exists, size for the low end
  of it.</p>
  <p>It also assumes the ICC you supplied. Published ICCs for education outcomes
  commonly run from 0.01 to 0.25 depending on the outcome and the level of clustering,
  and the design effect is linear in the ICC, so an ICC guessed two-fold low
  understates the requirement badly at large cluster sizes. Enter the largest ICC you
  would not be surprised by, then check what it costs.</p>
  <p>Beyond that: it covers a two-arm parallel design with one measurement per person
  and no covariates. Baseline covariate adjustment, matched or stratified allocation,
  repeated measures and stepped wedge designs all change the arithmetic, usually in
  your favour, and none of them are modelled here. Attrition is not modelled either;
  inflate the answer for it separately.</p>

  <h2>Why the design effect is not optional</h2>
  <p>Randomising clusters rather than individuals inflates the variance of a treatment
  mean by <code>DEFF = 1 + (m - 1) x ICC</code>. At a cluster size of 30 and an ICC of
  0.05 that is <b>__DEFF_30_005__</b>, so a study powered for __N_IND_200__ people
  needs __N_CLU_200__. Most online calculators leave this out, and the error grows
  with cluster size rather than staying a fixed margin.</p>
  <p>Cluster sizes are never equal. With a coefficient of variation of cluster size of
  0.65 at the same m and ICC, the exact inflation is <b>__CV_EXACT__</b> against
  __CV_EQUAL__ for equal clusters. The common shorthand of multiplying by
  (1 + CV squared) gives __CV_SHORTHAND__, which is conservative here; this calculator
  uses the exact expression from Eldridge et al. (2006) and shows both.</p>
  <p>What constrains a cluster trial is the number of clusters. Effective sample size
  per arm cannot exceed k / ICC however large the clusters grow, so past a point the
  only way to buy power is more clusters. Both numbers are reported above, and with
  few clusters the t reference on total clusters minus 2 degrees of freedom is used
  rather than the normal approximation, which is optimistic exactly where trials are
  smallest.</p>

  <h2>Validation</h2>
__REFERENCE_TABLE__

  <footer>
    <p>Catalog task EDU-039. Source, reference table and verification harness:
    <a href="https://github.com/JesseRWeigel/cluster-trial-power">github.com/JesseRWeigel/cluster-trial-power</a>.
    Generated by <code>scripts/build_page.py</code>; edits to this file are overwritten.</p>
  </footer>
</main>

<script type="module">
__ENGINE_JS__

// ---------------------------------------------------------------------------
// wiring
// ---------------------------------------------------------------------------

const $ = (id) => document.getElementById(id);
const FIELDS = ["kind", "effect", "p1", "p2", "m", "icc", "cv", "power", "alpha",
  "sides", "dfrule"];

function readInputs() {
  const kind = $("kind").value;
  const num = (id) => Number($(id).value);
  let effect;
  if (kind === "cohen_h") effect = cohenH(num("p1"), num("p2"));
  else if (kind === "proportion_difference") effect = proportionSmd(num("p1"), num("p2"));
  else effect = num("effect");
  return {
    kind,
    effect: Math.abs(effect),
    m: num("m"),
    icc: num("icc"),
    cv: num("cv"),
    power: num("power"),
    alpha: num("alpha"),
    sides: Number($("sides").value),
    dfRule: $("dfrule").value,
  };
}

function fmt(x, digits = 2) {
  if (!Number.isFinite(x)) return "-";
  return x.toLocaleString(undefined, {
    minimumFractionDigits: digits, maximumFractionDigits: digits,
  });
}

// ---------------------------------------------------------------------------
// charts, drawn by hand. No charting library: the whole page is one file and
// has to work with no network.
// ---------------------------------------------------------------------------

const NS = "http://www.w3.org/2000/svg";
// Kept so the browser check can read the numbers the curves were drawn from rather
// than reverse engineering them out of SVG path geometry.
const lastCurves = { power: [], oc: [] };
const PAD = { left: 54, right: 16, top: 14, bottom: 40 };
const W = 720;
const H = 320;

function el(name, attrs, text) {
  const node = document.createElementNS(NS, name);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, String(value));
  if (text !== undefined) node.textContent = text;
  return node;
}

function drawFrame(svg, xTicks, yTicks, xLabel, yLabel, xScale, yScale) {
  svg.replaceChildren();
  const plotRight = W - PAD.right;
  const plotBottom = H - PAD.bottom;
  for (const tick of yTicks) {
    const y = yScale(tick.value);
    svg.append(el("line", {
      x1: PAD.left, x2: plotRight, y1: y, y2: y, stroke: "var(--grid)", "stroke-width": 1,
    }));
    svg.append(el("text", {
      x: PAD.left - 8, y: y + 4, "text-anchor": "end", "font-size": 11, fill: "var(--muted)",
    }, tick.label));
  }
  for (const tick of xTicks) {
    const x = xScale(tick.value);
    svg.append(el("text", {
      x, y: plotBottom + 18, "text-anchor": "middle", "font-size": 11, fill: "var(--muted)",
    }, tick.label));
  }
  svg.append(el("line", {
    x1: PAD.left, x2: plotRight, y1: plotBottom, y2: plotBottom,
    stroke: "var(--line)", "stroke-width": 1.5,
  }));
  svg.append(el("line", {
    x1: PAD.left, x2: PAD.left, y1: PAD.top, y2: plotBottom,
    stroke: "var(--line)", "stroke-width": 1.5,
  }));
  svg.append(el("text", {
    x: (PAD.left + plotRight) / 2, y: H - 6, "text-anchor": "middle",
    "font-size": 12, fill: "var(--muted)",
  }, xLabel));
  svg.append(el("text", {
    x: 14, y: (PAD.top + plotBottom) / 2, "text-anchor": "middle", "font-size": 12,
    fill: "var(--muted)", transform: `rotate(-90 14 ${(PAD.top + plotBottom) / 2})`,
  }, yLabel));
}

function pathFrom(points, xScale, yScale) {
  return points.map((p, i) => `${i === 0 ? "M" : "L"}${xScale(p.x).toFixed(2)},${yScale(p.y).toFixed(2)}`).join(" ");
}

function drawPowerChart(state, result) {
  const svg = $("chart-power");
  const kMax = Math.max(6, Math.min(400, Math.ceil(result.clusters_per_arm * 2)));
  const curve = [];
  for (let k = 2; k <= kMax; k += 1) {
    curve.push({
      x: k,
      y: powerCrt(state.effect, state.m, state.icc, k, state.cv, state.alpha,
        state.sides, state.dfRule),
    });
  }
  const xScale = (v) => PAD.left + ((v - 2) / (kMax - 2)) * (W - PAD.left - PAD.right);
  const yScale = (v) => H - PAD.bottom - v * (H - PAD.bottom - PAD.top);
  const xTicks = [];
  const step = Math.max(1, Math.round(kMax / 8));
  for (let k = 2; k <= kMax; k += step) xTicks.push({ value: k, label: String(k) });
  const yTicks = [0, 0.2, 0.4, 0.6, 0.8, 1].map((v) => ({ value: v, label: v.toFixed(1) }));
  drawFrame(svg, xTicks, yTicks, "clusters per arm", "power", xScale, yScale);

  svg.append(el("line", {
    x1: PAD.left, x2: W - PAD.right, y1: yScale(state.power), y2: yScale(state.power),
    stroke: "var(--warn)", "stroke-width": 1, "stroke-dasharray": "4 4",
  }));
  svg.append(el("text", {
    x: W - PAD.right, y: yScale(state.power) - 6, "text-anchor": "end",
    "font-size": 11, fill: "var(--warn)",
  }, `target ${fmt(state.power, 2)}`));
  svg.append(el("path", {
    d: pathFrom(curve, xScale, yScale), fill: "none", stroke: "var(--accent)",
    "stroke-width": 2.5, id: "power-path",
  }));
  lastCurves.power = curve;
  const kx = xScale(result.clusters_per_arm);
  const ky = yScale(result.achieved_power);
  svg.append(el("line", {
    x1: kx, x2: kx, y1: ky, y2: H - PAD.bottom, stroke: "var(--accent)",
    "stroke-width": 1, "stroke-dasharray": "3 3",
  }));
  svg.append(el("circle", { cx: kx, cy: ky, r: 5, fill: "var(--accent)", id: "power-marker" }));
  svg.append(el("text", {
    x: Math.min(kx + 10, W - PAD.right - 4), y: Math.max(ky - 10, PAD.top + 10),
    "text-anchor": kx > W * 0.7 ? "end" : "start", "font-size": 12, fill: "var(--accent)",
  }, `${result.clusters_per_arm} per arm`));
}

function drawOcChart(state, result) {
  const svg = $("chart-oc");
  const dMax = Math.max(0.05, state.effect * 2);
  const points = 121;
  const power = [];
  const accept = [];
  for (let i = 0; i < points; i += 1) {
    const d = (dMax * i) / (points - 1);
    const pw = d === 0 ? state.alpha
      : powerCrt(d, state.m, state.icc, result.clusters_per_arm, state.cv, state.alpha,
        state.sides, state.dfRule);
    power.push({ x: d, y: pw });
    accept.push({ x: d, y: 1 - pw });
  }
  const xScale = (v) => PAD.left + (v / dMax) * (W - PAD.left - PAD.right);
  const yScale = (v) => H - PAD.bottom - v * (H - PAD.bottom - PAD.top);
  const xTicks = [];
  for (let i = 0; i <= 6; i += 1) {
    const v = (dMax * i) / 6;
    xTicks.push({ value: v, label: v.toFixed(2) });
  }
  const yTicks = [0, 0.2, 0.4, 0.6, 0.8, 1].map((v) => ({ value: v, label: v.toFixed(1) }));
  drawFrame(svg, xTicks, yTicks, "true effect size", "probability", xScale, yScale);

  svg.append(el("path", {
    d: pathFrom(accept, xScale, yScale), fill: "none", stroke: "var(--muted)",
    "stroke-width": 1.75, "stroke-dasharray": "5 4", id: "oc-accept-path",
  }));
  svg.append(el("path", {
    d: pathFrom(power, xScale, yScale), fill: "none", stroke: "var(--accent)",
    "stroke-width": 2.5, id: "oc-power-path",
  }));
  lastCurves.oc = power.map((p, i) => ({ effect: p.x, power: p.y, accept_null: accept[i].y }));
  const ax = xScale(state.effect);
  svg.append(el("line", {
    x1: ax, x2: ax, y1: PAD.top, y2: H - PAD.bottom, stroke: "var(--warn)",
    "stroke-width": 1, "stroke-dasharray": "4 4",
  }));
  svg.append(el("text", {
    x: ax - 6, y: PAD.top + 12, "text-anchor": "end", "font-size": 11, fill: "var(--warn)",
  }, "assumed effect"));
  svg.append(el("text", {
    x: xScale(0) + 6, y: yScale(state.alpha) - 6, "font-size": 11, fill: "var(--muted)",
  }, `power = alpha at zero effect`));
}

// ---------------------------------------------------------------------------

function update() {
  const state = readInputs();
  const err = $("err");
  const kindLabel = { d: "standardised mean difference", cohen_h: "Cohen's arcsine h",
    proportion_difference: "difference of proportions over the pooled SD" }[state.kind];
  let result;
  try {
    result = clustersCrt({
      effect: state.effect, m: state.m, icc: state.icc, cv: state.cv,
      power: state.power, alpha: state.alpha, sides: state.sides, dfRule: state.dfRule,
      maxClustersPerArm: 20000,
    });
  } catch (e) {
    err.className = "err";
    err.textContent = e.message;
    return;
  }
  err.className = "muted";
  err.textContent = `${state.sides === 1 ? "One" : "Two"} sided test at alpha `
    + `${state.alpha}, effect read as a ${kindLabel} of ${fmt(state.effect, 3)}.`;

  $("k-total").textContent = result.clusters_total.toLocaleString();
  $("k-arm").textContent = result.clusters_per_arm.toLocaleString();
  $("n-total").textContent = result.individuals_total.toLocaleString();
  $("m-echo").textContent = fmt(state.m, 0);
  $("deff").textContent = fmt(result.design_effect, 3);
  $("neff").textContent = fmt(result.effective_n_per_arm, 1);
  $("achieved").textContent = fmt(result.achieved_power, 3);
  $("df").textContent = result.degrees_of_freedom === null
    ? "normal" : fmt(result.degrees_of_freedom, 0);

  const naive = result.n_individually_randomised_total;
  const cost = result.cost_of_assuming_equal_clusters;
  let comparison = `Ignoring clustering entirely would give ${Math.ceil(naive).toLocaleString()} `
    + `individuals, which is ${fmt(result.inflation_vs_individual, 2)} times too few. `;
  if (state.cv > 0) {
    comparison += `Assuming equal cluster sizes would use a design effect of `
      + `${fmt(cost.deff_equal_sizes, 3)} instead of ${fmt(cost.deff_unequal_sizes, 3)}, `
      + `understating the requirement by ${fmt(100 * (cost.exact_over_equal - 1), 1)} percent.`;
  } else {
    comparison += "Set a coefficient of variation above zero to see what unequal "
      + "cluster sizes cost.";
  }
  $("comparison").textContent = comparison;

  const notes = $("notes");
  notes.replaceChildren();
  for (const note of result.notes) {
    const li = document.createElement("li");
    li.textContent = note;
    notes.append(li);
  }

  drawPowerChart(state, result);
  drawOcChart(state, result);

  // Exposed so the browser check can read what the page actually computed rather
  // than scraping formatted text.
  window.__ctp = { state, result, curves: lastCurves };
}

function onKindChange() {
  const proportions = $("kind").value !== "d";
  $("pwrap").hidden = !proportions;
  $("dwrap").hidden = proportions;
}

for (const id of FIELDS) {
  $(id).addEventListener("input", () => { onKindChange(); update(); });
  $(id).addEventListener("change", () => { onKindChange(); update(); });
}
onKindChange();
update();
</script>
</body>
</html>
"""


def build() -> str:
    with open(ENGINE) as fh:
        engine_js = fh.read()
    # The engine is an ES module for node; inlined in a module script the export
    # keywords are legal but the names would not be in scope, so they are stripped.
    engine_js = engine_js.replace("\nexport function ", "\nfunction ")

    numbers = worked_numbers()
    placeholders = [tok for tok in TEMPLATE.split() if tok.startswith("__") and tok.endswith("__")]
    page = TEMPLATE
    page = page.replace("__ENGINE_JS__", engine_js)
    page = page.replace("__REFERENCE_TABLE__", render_reference_table(reference_rows()))
    page = page.replace("__DEFF_30_005__", f"{numbers['deff_30_005']:.2f}")
    page = page.replace("__N_IND_200__", str(numbers["n_individual_200"]))
    page = page.replace("__N_CLU_200__", str(numbers["n_cluster_200"]))
    page = page.replace("__CV_EXACT__", f"{numbers['cv_exact']:.4g}")
    page = page.replace("__CV_EQUAL__", f"{numbers['cv_equal']:.4g}")
    page = page.replace("__CV_SHORTHAND__", f"{numbers['cv_shorthand']:.4g}")
    page = page.replace("__OPTIMISM__", f"{100 * numbers['optimistic_power_if_wrong']:.0f}")
    # Every placeholder the template declared must be gone. Checked by name rather
    # than by scanning for a double underscore, which the engine's own identifiers use.
    leftovers = sorted({tok for tok in placeholders if tok in page})
    if leftovers:
        raise SystemExit(f"unsubstituted placeholders remain: {leftovers}")
    return page


def main() -> int:
    out = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OUT
    page = build()
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w") as fh:
        fh.write(page)
    print(f"wrote {out} ({len(page)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
