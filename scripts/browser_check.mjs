/**
 * Load docs/index.html in real headless Chrome and measure it from inside the page.
 *
 * Unit tests here import the engine directly and never load the page, so a page whose
 * inline script fails to parse would pass every one of them while rendering as static
 * HTML with dashes where the numbers should be. Only a browser catches that.
 *
 * A screenshot is not evidence either: `chrome --headless --screenshot --window-size=`
 * can render at a width other than the one it captures. Every assertion below runs as
 * JavaScript in the page and reports a number the page's own script must have produced.
 *
 * The expected values are not written here. They come from a JSON file that
 * scripts/verify.sh generates by running the PYTHON engine, so this stage also checks
 * that the browser and the validated engine agree on the same design.
 *
 * Two viewports, desktop and 390 CSS pixels. Overflow is found by walking the elements
 * and comparing each right edge against the document's clientWidth, skipping anything
 * inside an ancestor that scrolls horizontally on purpose. `overflow-x: hidden` on the
 * body is never used, and this script fails if it appears, because it would hide the
 * defect and make the probe vacuous at the same time.
 *
 * The browser is shared between agents on this machine, so page identity is asserted
 * inside every evaluation and navigate-then-measure is one atomic step.
 *
 * usage: node scripts/browser_check.mjs <expected.json>
 */

import { spawn } from "node:child_process";
import { mkdtemp, rm } from "node:fs/promises";
import { existsSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, "..");
const PAGE = join(ROOT, "docs", "index.html");
const EXPECTED_TITLE = "Cluster trial power calculator";
const TIMEOUT_MS = Number(process.env.CTP_BROWSER_TIMEOUT || 45) * 1000;

const CHROME_CANDIDATES = [
  process.env.CHROME_PATH,
  "/usr/bin/google-chrome",
  "/usr/bin/google-chrome-stable",
  "/usr/bin/chromium",
  "/usr/bin/chromium-browser",
].filter(Boolean);

function findChrome() {
  for (const candidate of CHROME_CANDIDATES) if (existsSync(candidate)) return candidate;
  throw new Error(
    "no Chrome binary found. Install one with `sudo apt-get install google-chrome-stable` "
    + "or set CHROME_PATH. This stage cannot be skipped: the unit suite imports the "
    + "engine directly and never loads the page, so nothing else in this repository "
    + "would notice a page whose script does not run."
  );
}

class Chrome {
  constructor(binary, profileDir) {
    this.binary = binary;
    this.profileDir = profileDir;
    this.messageId = 0;
    this.pending = new Map();
  }

  async start() {
    const args = [
      "--headless=new",
      "--remote-debugging-port=0",
      `--user-data-dir=${this.profileDir}`,
      "--no-first-run",
      "--no-default-browser-check",
      "--disable-extensions",
      "--disable-gpu",
      "--no-sandbox",
      "--allow-file-access-from-files",
      "--hide-scrollbars",
      // Never --disable-crashpad-for-testing or --disable-features=Crashpad. On this
      // machine those two put Chrome into a crash-restart loop that never returns.
      "about:blank",
    ];
    this.process = spawn(this.binary, args, { stdio: ["ignore", "ignore", "pipe"] });

    const endpoint = await new Promise((resolveEndpoint, rejectEndpoint) => {
      let buffer = "";
      const timer = setTimeout(() => {
        rejectEndpoint(new Error(`Chrome did not report a DevTools endpoint within ${TIMEOUT_MS} ms`));
      }, TIMEOUT_MS);
      this.process.stderr.on("data", (chunk) => {
        buffer += chunk.toString();
        const match = buffer.match(/ws:\/\/[^\s]+/);
        if (match) { clearTimeout(timer); resolveEndpoint(match[0]); }
      });
      this.process.on("exit", (code) => {
        clearTimeout(timer);
        rejectEndpoint(new Error(`Chrome exited with code ${code} before starting.\n${buffer}`));
      });
    });

    const httpBase = endpoint.replace(/^ws:\/\/([^/]+).*$/, "http://$1");
    const target = await fetch(`${httpBase}/json/new?about:blank`, { method: "PUT" })
      .then((r) => r.json());
    this.socket = new WebSocket(target.webSocketDebuggerUrl);
    await new Promise((ready, failed) => {
      this.socket.addEventListener("open", ready, { once: true });
      this.socket.addEventListener("error", () => failed(new Error("DevTools socket failed")), { once: true });
    });
    this.socket.addEventListener("message", (event) => {
      const message = JSON.parse(event.data);
      const waiting = this.pending.get(message.id);
      if (waiting) {
        this.pending.delete(message.id);
        if (message.error) waiting.reject(new Error(JSON.stringify(message.error)));
        else waiting.resolve(message.result);
      }
    });
  }

  send(method, params = {}) {
    const id = ++this.messageId;
    return new Promise((resolvePromise, rejectPromise) => {
      const timer = setTimeout(
        () => rejectPromise(new Error(`${method} timed out after ${TIMEOUT_MS} ms`)), TIMEOUT_MS,
      );
      this.pending.set(id, {
        resolve: (value) => { clearTimeout(timer); resolvePromise(value); },
        reject: (error) => { clearTimeout(timer); rejectPromise(error); },
      });
      this.socket.send(JSON.stringify({ id, method, params }));
    });
  }

  async run(expression, { navigate = null, width = null, height = null } = {}) {
    if (width) {
      await this.send("Emulation.setDeviceMetricsOverride", {
        width, height, deviceScaleFactor: 1, mobile: width < 500,
      });
    }
    if (navigate) {
      await this.send("Page.enable");
      await this.send("Page.navigate", { url: navigate });
    }
    // window.__ctp is set at the end of the module's first update(), so waiting for it
    // proves the whole inline script parsed, executed, and computed something.
    const guard = `
      (async () => {
        const deadline = Date.now() + 20000;
        while (!window.__ctp) {
          if (Date.now() > deadline) throw new Error("page script never produced window.__ctp");
          await new Promise((r) => setTimeout(r, 50));
        }
        if (document.title !== ${JSON.stringify(EXPECTED_TITLE)}) {
          throw new Error("wrong page loaded, title is " + JSON.stringify(document.title)
            + ". The browser is shared between agents and something navigated it away.");
        }
        return (${expression})();
      })()
    `;
    const result = await this.send("Runtime.evaluate", {
      expression: guard, awaitPromise: true, returnByValue: true,
    });
    if (result.exceptionDetails) {
      throw new Error("page evaluation threw: "
        + (result.exceptionDetails.exception?.description
          || JSON.stringify(result.exceptionDetails)));
    }
    return result.result.value;
  }

  async stop() {
    try { this.socket?.close(); } catch { /* already gone */ }
    if (this.process && this.process.exitCode === null) {
      this.process.kill("SIGTERM");
      await new Promise((done) => {
        const timer = setTimeout(() => { this.process.kill("SIGKILL"); done(); }, 5000);
        this.process.on("exit", () => { clearTimeout(timer); done(); });
      });
    }
  }
}

const OVERFLOW_PROBE = `() => {
  const limit = document.documentElement.clientWidth;
  const scrollers = new Set();
  document.querySelectorAll("*").forEach((node) => {
    const style = getComputedStyle(node);
    if (style.overflowX === "auto" || style.overflowX === "scroll") scrollers.add(node);
  });
  const insideScroller = (node) => {
    for (let p = node.parentElement; p; p = p.parentElement) if (scrollers.has(p)) return true;
    return false;
  };
  const offenders = [];
  document.querySelectorAll("body *").forEach((node) => {
    if (insideScroller(node)) return;
    const rect = node.getBoundingClientRect();
    if (rect.width === 0 && rect.height === 0) return;
    if (rect.right > limit + 0.5) {
      offenders.push({
        tag: node.tagName.toLowerCase(),
        id: node.id || null,
        cls: typeof node.className === "string" ? node.className : null,
        right: Math.round(rect.right * 100) / 100,
      });
    }
  });
  return {
    limit,
    documentScrollWidth: document.documentElement.scrollWidth,
    bodyOverflowX: getComputedStyle(document.body).overflowX,
    htmlOverflowX: getComputedStyle(document.documentElement).overflowX,
    offenders: offenders.slice(0, 8),
  };
}`;

const READ_STATE = `() => {
  const text = (id) => document.getElementById(id).textContent.trim();
  const path = (id) => {
    const node = document.getElementById(id);
    if (!node) return null;
    const d = node.getAttribute("d");
    return { commands: (d.match(/[ML]/g) || []).length, length: d.length };
  };
  const oc = window.__ctp.curves.oc;
  return {
    title: document.title,
    result: window.__ctp.result,
    state: window.__ctp.state,
    kTotal: text("k-total"),
    kArm: text("k-arm"),
    nTotal: text("n-total"),
    deff: text("deff"),
    achieved: text("achieved"),
    df: text("df"),
    comparison: text("comparison"),
    noteCount: document.querySelectorAll("#notes li").length,
    powerPath: path("power-path"),
    ocPowerPath: path("oc-power-path"),
    ocAcceptPath: path("oc-accept-path"),
    markerPresent: !!document.getElementById("power-marker"),
    powerCurveLength: window.__ctp.curves.power.length,
    ocLength: oc.length,
    ocAtZero: oc[0],
    ocComplementMax: Math.max(...oc.map((p) => Math.abs(p.power + p.accept_null - 1))),
    powerCurveMonotone: window.__ctp.curves.power
      .every((p, i, arr) => i === 0 || p.y >= arr[i - 1].y),
    referenceRows: document.querySelectorAll("table tbody tr").length,
    dashes: Array.from(document.querySelectorAll(".headline span, .fig b"))
      .filter((n) => n.textContent.trim() === "-").length,
  };
}`;

function setInputs(values) {
  return `() => {
    for (const [id, value] of Object.entries(${JSON.stringify(values)})) {
      const node = document.getElementById(id);
      node.value = String(value);
      node.dispatchEvent(new Event(node.tagName === "SELECT" ? "change" : "input",
        { bubbles: true }));
    }
    return { clusters: window.__ctp.result.clusters_per_arm,
             deff: window.__ctp.result.design_effect,
             power: window.__ctp.result.achieved_power,
             effect: window.__ctp.state.effect,
             individuals: window.__ctp.result.individuals_total };
  }`;
}

// --------------------------------------------------------------------------

const expectedPath = process.argv[2];
if (!expectedPath) {
  console.error("usage: node scripts/browser_check.mjs <expected.json>");
  process.exit(2);
}
const expected = JSON.parse(readFileSync(expectedPath, "utf8"));
if (!existsSync(PAGE)) {
  console.error(`docs/index.html is missing. Run scripts/build_page.py first.`);
  process.exit(1);
}

const failures = [];
const check = (name, condition, detail) => {
  console.log(`  ${condition ? "ok  " : "FAIL"}  ${name}${detail ? `  ${detail}` : ""}`);
  if (!condition) failures.push(`${name}: ${detail}`);
};
const near = (a, b, tol) => Math.abs(a - b) <= tol;

const profileDir = await mkdtemp(join(tmpdir(), "ctp-chrome-"));
const chrome = new Chrome(findChrome(), profileDir);
try {
  await chrome.start();
  const url = `file://${PAGE}`;

  console.log("desktop, 1280x900");
  const desktop = await chrome.run(READ_STATE, { navigate: url, width: 1280, height: 900 });

  check("page title", desktop.title === EXPECTED_TITLE, desktop.title);
  check("no placeholder dashes left in the readouts", desktop.dashes === 0,
    `${desktop.dashes} readouts still show a dash`);
  check("clusters per arm matches the python engine",
    desktop.result.clusters_per_arm === expected.clusters_per_arm,
    `browser ${desktop.result.clusters_per_arm}, python ${expected.clusters_per_arm}`);
  check("individuals total matches the python engine",
    desktop.result.individuals_total === expected.individuals_total,
    `browser ${desktop.result.individuals_total}, python ${expected.individuals_total}`);
  check("achieved power matches the python engine to 1e-10",
    near(desktop.result.achieved_power, expected.achieved_power, 1e-10),
    `browser ${desktop.result.achieved_power}, python ${expected.achieved_power}`);
  check("design effect matches the python engine",
    near(desktop.result.design_effect, expected.design_effect, 1e-12),
    `browser ${desktop.result.design_effect}, python ${expected.design_effect}`);
  check("rendered cluster total is the computed one",
    desktop.kTotal === String(expected.clusters_total), desktop.kTotal);
  check("rendered design effect is formatted from the computed one",
    desktop.deff === expected.design_effect.toFixed(3), desktop.deff);
  check("rendered degrees of freedom", desktop.df === String(expected.degrees_of_freedom),
    desktop.df);
  check("comparison line names the unclustered answer",
    desktop.comparison.includes(expected.n_individually_randomised_total.toLocaleString()),
    desktop.comparison.slice(0, 90));
  check("notes rendered", desktop.noteCount >= 1, `${desktop.noteCount} notes`);
  check("reference table rendered from the json",
    desktop.referenceRows === expected.reference_rows,
    `${desktop.referenceRows} rows, expected ${expected.reference_rows}`);

  console.log("curves");
  check("power curve drawn with a real path",
    desktop.powerPath && desktop.powerPath.commands >= 50,
    `${desktop.powerPath?.commands} path commands`);
  check("power curve is monotone in the number of clusters", desktop.powerCurveMonotone);
  check("design marker drawn", desktop.markerPresent);
  check("operating characteristic drawn with a real path",
    desktop.ocPowerPath && desktop.ocPowerPath.commands >= 100,
    `${desktop.ocPowerPath?.commands} path commands`);
  check("the accept-null companion curve is drawn too",
    desktop.ocAcceptPath && desktop.ocAcceptPath.commands >= 100,
    `${desktop.ocAcceptPath?.commands} path commands`);
  check("operating characteristic passes through alpha at zero effect",
    near(desktop.ocAtZero.power, expected.alpha, 1e-12),
    `power at zero effect is ${desktop.ocAtZero.power}`);
  check("power and accept-null sum to one across the curve",
    desktop.ocComplementMax < 1e-12, `worst departure ${desktop.ocComplementMax}`);

  console.log("interaction");
  const iccZero = await chrome.run(setInputs({ icc: 0 }));
  check("setting ICC to zero gives back the individually randomised answer",
    iccZero.deff === 1 && iccZero.clusters === expected.icc_zero_clusters_per_arm,
    `deff ${iccZero.deff}, clusters per arm ${iccZero.clusters}, `
    + `expected ${expected.icc_zero_clusters_per_arm}`);
  const restored = await chrome.run(setInputs({ icc: 0.05, cv: 0.65 }));
  check("adding a coefficient of variation increases the requirement",
    restored.clusters > expected.clusters_per_arm
      && near(restored.deff, expected.cv065_design_effect, 1e-12),
    `deff ${restored.deff} vs python ${expected.cv065_design_effect}, `
    + `clusters ${restored.clusters} vs ${expected.clusters_per_arm} at CV 0`);
  check("clusters at CV 0.65 match the python engine",
    restored.clusters === expected.cv065_clusters_per_arm,
    `browser ${restored.clusters}, python ${expected.cv065_clusters_per_arm}`);
  const proportions = await chrome.run(setInputs({ cv: 0, kind: "proportion_difference" }));
  check("switching to a proportion difference recomputes the effect",
    near(proportions.effect, expected.proportion_smd, 1e-12),
    `browser ${proportions.effect}, python ${expected.proportion_smd}`);
  const oneSided = await chrome.run(setInputs({ kind: "d", sides: 1 }));
  check("one sided needs fewer clusters than two sided",
    oneSided.clusters < expected.clusters_per_arm,
    `${oneSided.clusters} vs ${expected.clusters_per_arm}`);
  const normalRule = await chrome.run(setInputs({ sides: 2, dfrule: "normal" }));
  check("the normal approximation asks for no more than the t rule",
    normalRule.clusters <= expected.clusters_per_arm,
    `${normalRule.clusters} vs ${expected.clusters_per_arm}`);
  const bad = await chrome.run(`() => {
    const node = document.getElementById("icc");
    node.value = "2";
    node.dispatchEvent(new Event("input", { bubbles: true }));
    const message = document.getElementById("err");
    return { cls: message.className, text: message.textContent.trim() };
  }`);
  check("an out of range ICC reports an error instead of a number",
    bad.cls === "err" && bad.text.length > 0, bad.text.slice(0, 80));

  console.log("layout, desktop");
  const wideOverflow = await chrome.run(OVERFLOW_PROBE, { width: 1280, height: 900 });
  check("no element escapes the page at 1280px", wideOverflow.offenders.length === 0,
    JSON.stringify(wideOverflow.offenders));
  check("body does not hedge with overflow-x hidden at 1280px",
    wideOverflow.bodyOverflowX !== "hidden" && wideOverflow.htmlOverflowX !== "hidden",
    `body ${wideOverflow.bodyOverflowX}, html ${wideOverflow.htmlOverflowX}`);

  console.log("layout, 390px");
  const narrow = await chrome.run(READ_STATE, { navigate: url, width: 390, height: 844 });
  check("the page still computes at 390px",
    narrow.result.clusters_per_arm === expected.clusters_per_arm,
    `${narrow.result.clusters_per_arm}`);
  check("the curves are still drawn at 390px",
    narrow.powerPath.commands >= 50 && narrow.ocPowerPath.commands >= 100);
  const narrowOverflow = await chrome.run(OVERFLOW_PROBE);
  check("no element escapes the page at 390px", narrowOverflow.offenders.length === 0,
    JSON.stringify(narrowOverflow.offenders));
  check("the document does not scroll sideways at 390px",
    narrowOverflow.documentScrollWidth <= narrowOverflow.limit + 0.5,
    `scrollWidth ${narrowOverflow.documentScrollWidth} against clientWidth ${narrowOverflow.limit}`);
  check("body does not hedge with overflow-x hidden at 390px",
    narrowOverflow.bodyOverflowX !== "hidden" && narrowOverflow.htmlOverflowX !== "hidden",
    `body ${narrowOverflow.bodyOverflowX}, html ${narrowOverflow.htmlOverflowX}`);
} finally {
  await chrome.stop();
  // Chrome keeps flushing its profile for a moment after the process exits, so a
  // recursive remove straight after SIGTERM loses a race with it and throws
  // ENOTEMPTY. That happened once here and failed a run in which every assertion
  // had passed. Cleaning up a temporary directory is not part of the verdict, so it
  // retries and then reports rather than throwing.
  let removed = false;
  for (let attempt = 0; attempt < 5 && !removed; attempt += 1) {
    try {
      await rm(profileDir, { recursive: true, force: true });
      removed = true;
    } catch {
      await new Promise((r) => setTimeout(r, 200 * (attempt + 1)));
    }
  }
  if (!removed) {
    console.log(`note: could not remove the temporary chrome profile, left it behind. `
      + "This does not affect any assertion above.");
  }
}

console.log();
if (failures.length) {
  console.error(`BROWSER CHECK FAILED: ${failures.length}`);
  for (const failure of failures) console.error(`  - ${failure}`);
  process.exit(1);
}
console.log("browser check PASSED");
