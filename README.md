# cluster-trial-power

An embeddable calculator for cluster randomised trials. Enter the effect size you
expect, the average cluster size and the intracluster correlation, and get back the
number of clusters and the number of individuals you need, with the power curve and
the operating characteristic drawn.

Catalog task: `EDU-039`. One of a public catalog of build ideas:
https://github.com/JesseRWeigel/722-things-to-build

Page: `docs/index.html`, published to GitHub Pages. It is one file, computes entirely
in the browser, loads nothing from a network, and sends nothing anywhere.

## What it does that most online calculators do not

**It applies the design effect.** Randomising clusters of m people with intracluster
correlation rho inflates the variance of a treatment mean by

```
DEFF = 1 + (m - 1) * rho
```

so the number of individuals you need is the individually randomised number times
that. At m = 30 and rho = 0.05 the design effect is 2.45, which means a study powered
for 200 people needs 490. It is a multiplier that grows with cluster size, so leaving
it out does not cost a fixed margin, and it is the single most common way a cluster
trial ends up underpowered.

**It handles unequal cluster sizes.** Real trials never recruit equal clusters.
Writing CV for the coefficient of variation of cluster size, the inflation becomes

```
DEFF = 1 + ((1 + CV^2) * m - 1) * rho
```

from Eldridge, Ashby and Kerry (2006), which reduces to the Kish form exactly at
CV = 0. A common shorthand is to multiply the equal-size design effect by (1 + CV^2).
That shorthand is the large `m * rho` limit and is conservative below it: at m = 30,
rho = 0.05 and CV = 0.65 the exact factor is 3.084 and the shorthand gives 3.485, 13
percent higher. The calculator uses the exact expression and reports what assuming
equal sizes would have cost you.

**It reports clusters, not only people.** What constrains a cluster trial is the
number of clusters. The effective sample size per arm cannot exceed k / rho however
large the clusters grow, so past a point the only way to buy power is to recruit more
clusters. Both numbers appear in every result, along with that ceiling.

**It uses a t reference on the clusters.** A cluster trial has as many independent
units as it has clusters, so with few clusters the normal approximation is optimistic.
The default is Student's t on (total clusters - 2) degrees of freedom, which is
2k - 2 for k clusters per arm and the same rule as Hayes and Moulton's 2(c - 1).
Every result names the rule it used. In the worked example in
`reference/SOURCES.md` the correction costs one extra cluster per arm: the normal
approximation claims power 0.815 at 23 clusters per arm where the t calculation says
0.798, below the 0.80 target.

**It makes you say which test and which effect size.** One sided or two sided is an
explicit argument with no hidden default, because one sided needs 21 percent fewer
people and the choice has to be deliberate. So is the type of effect size: Cohen's d
and a standardised mean difference are the same thing here, Cohen's arcsine h for two
proportions is not, and neither is the plain difference of proportions over the pooled
standard deviation. For 0.6 against 0.4 the arcsine h is 0.4027 and the standardised
difference is 0.4000. Every result echoes back which one it used.

## Running it

```bash
# the page
python3 -m http.server 0 --directory docs      # or just open docs/index.html

# one design from the command line
python3 src/cli.py --effect 0.2 --cluster-size 30 --icc 0.05

# a binary outcome, unequal clusters, one sided
python3 src/cli.py --effect-kind proportion_difference --p1 0.55 --p2 0.45 \
    --cluster-size 40 --icc 0.02 --cv 0.6 --sides 1

# everything
bash scripts/verify.sh
```

No dependencies beyond the Python standard library. Node and Chrome are needed for
the verify run only, to check the JavaScript port and load the page.

## What this calculator cannot tell you

**It assumes the effect size you supply is the true one.** That assumption is the
whole calculation and it is the part nobody can check in advance. A trial powered at
80 percent for d = 0.3, at 25 per cluster and an ICC of 0.05, has 48 percent power if
the real effect is 0.2. A study powered for an optimistic effect is likely to miss a
real effect and then be read as evidence of no effect. Where you have a plausible range, size
for the low end of it.

**It assumes the ICC you supply.** The design effect is linear in the ICC, so an ICC
guessed two-fold low understates the requirement badly at large cluster sizes.
Published ICCs for education outcomes commonly range from about 0.01 to 0.25
depending on the outcome and the level of clustering.

**It models a two-arm parallel design only,** with one measurement per person and no
covariates. Baseline adjustment, matched or stratified allocation, repeated measures
and stepped wedge designs all change the arithmetic, usually in your favour, and none
of them are here. Attrition is not modelled; inflate the answer for it separately.
The unequal-cluster-size correction assumes the analysis weights individuals equally,
which is the design effect Eldridge et al. derive; an unweighted analysis of cluster
means has a different one.

## Validation, and what it does and does not establish

The task's done condition is agreement with `pwr` and `clusterPower`. **R is not
installed on the machine this was built on.** `which R` and `which Rscript` both
return nothing, and no number here was produced by running R. Saying so plainly
matters more than the alternative, which would be to write down numbers that look
like R output.

What was done instead, in `reference/reference_values.json` and
`reference/SOURCES.md`, each row carrying its provenance and its citation:

- **Published tables.** Normal and Student t quantiles from Abramowitz and Stegun and
  from Fisher and Yates, and six entries of Cohen (1988) Table 2.4.1, the n per group
  for the two-tailed t test at alpha = .05. All six agree, and they agree only under
  rounding to nearest: the table's 393 at d = 0.2 is round(393.4057), and rounding up
  would give 394.
- **Published package output.** Four values of `pwr.t.test` recorded from its
  documentation rather than from a run. These are the weakest rows here and are
  labelled as such, because a value recalled after seeing the computed one is not
  independent of it. They do not carry the validation on their own.
- **Exact arithmetic.** Design effects, closed-form normal-approximation sample sizes,
  and one worked cluster design carried through by hand from published z quantiles to
  a cluster count. The arithmetic is written out in `reference/SOURCES.md` so anyone
  can redo it on paper.
- **Structural identities**, checked as exact floating point equality. At ICC = 0 the
  design effect is exactly 1 and the cluster design must give back the individually
  randomised answer bit for bit, which exercises the entire pipeline. At m = 1 the
  cluster path reduces exactly to the individually randomised t test, degrees of
  freedom included, which is what makes every Cohen and pwr row above a test of the
  cluster code rather than of a simpler separate path.
- **A second published derivation.** Hayes and Moulton size a trial from the variance
  components with no design effect in the expression at all. The two routes are shown
  algebraically identical in `reference/SOURCES.md` and checked numerically over a
  grid.

For `clusterPower` specifically: no numeric output of it is asserted here, because no
value could be sourced that was worth trusting. What is asserted is the model
`cpa.normal` documents, a noncentral t on 2(k - 1) degrees of freedom with
noncentrality `d sqrt(k m / (2 DEFF))`, which is what `df_rule = "cluster_t"`
implements. That is a real gap and it is left visible rather than filled with a
plausible number. Installing R and running the two packages would close it, and
`scripts/verify.sh` prints whether R was found on every run.

**What carries the weight instead of R** is that the same numbers are reached by three
routes that share no code: the closed form, a Gauss-Legendre quadrature over the chi
density used as a second noncentral t, and a Monte Carlo simulation of the trial
itself. The simulation is the strongest of the three, because it builds synthetic
trials one individual at a time and counts rejections, which goes wrong for entirely
different reasons than algebra does. It agrees with the closed form on all eight
scenarios, including the unequal-cluster case that tests the Eldridge design effect,
and including a null case where the rejection rate must come out at alpha.

Tolerances are relative, not absolute, because the compared quantities run from 1.18
to 963.8 and an absolute tolerance means something different at each end. Each one is
derived from the precision of its source rather than chosen: half a unit in the last
printed place, divided by the expected value. And to show the tolerances are tight
enough to matter, `scripts/check_reference.py` runs 13 deliberately wrong
calculations, one for each error this calculator exists to prevent, and requires every
one of them to be rejected. The tightest margin among them is the Cohen row at
d = 0.2, where the normal approximation gives 392 against the tabled 393 and is
rejected at exactly twice the tolerance, which is the smallest a one-integer error can
be.

## What the verify run checks

| check | count |
|---|---|
| unit tests | 45 |
| reference values | 44 |
| negative controls | 13 |
| parity cases | 1018 |
| simulation scenarios | 8 |
| sabotages | 16 |
| browser assertions | 33 |

These counts are not decoration. `scripts/check_readme.py` reads them out of this
table, reads what the run actually produced out of the logs, and fails if they
disagree in either direction, so this table cannot go stale without the verify going
red.

Ten stages, in `scripts/verify.sh`:

1. **Unit tests.** Properties over a grid, exact identities, and a negative control
   beside each agreement test.
2. **Reference values** against published sources, with the negative controls
   described above.
3. **Parity** between the Python engine and the JavaScript port over 1018 cases, at a
   relative tolerance of 1e-10. The page computes in the browser, so a port that has
   drifted would be showing numbers no reference table has ever checked.
4. **Independent recomputation** by Monte Carlo. `scripts/check_independent.py`
   imports nothing from `src/`, proved by walking its own syntax tree with `ast`
   rather than by grep, and reaches the calculator only by running `src/cli.py` as a
   subprocess. It reports its own Monte Carlo standard error, which at 20000
   replications is 0.0028 near a power of 0.8, so it can detect a systematic error of
   about one percent of power and no smaller. That limit is stated rather than
   glossed.
5. **The published page rebuilds identically.** `docs/index.html` is generated from
   the engine and the reference table by `scripts/build_page.py`. The verify rebuilds
   it into a temporary file and diffs, so the page cannot quietly go stale.
6. **Real headless Chrome** at 1280px and at 390px. Every assertion runs as JavaScript
   inside the page, because a screenshot is not evidence and because unit tests import
   the engine directly and would never notice a page whose inline script failed to
   parse. Overflow is found by walking elements and comparing right edges against the
   document width; `overflow-x: hidden` is never used and the check fails if it
   appears, since it would hide the defect and make the probe vacuous at once. The
   expected numbers come from the Python engine, so this stage is also a
   cross-language agreement test.
7. **A privacy scan with a positive control.** Credential-shaped strings are planted
   in a temporary file and the scanner must find them before any clean result is
   believed. The patterns are assembled from fragments at run time so the scanner does
   not match its own pattern list, and a NUL byte in a text file is a failure rather
   than a silently skipped file.
8. **Sabotage under the three-gate rule.** Sixteen deliberate breakages, each of which
   must apply, move the measured output, and then be caught. A null control runs
   first: an unmodified copy of the tree must fingerprint identically, or the
   measurement tracks the working directory rather than the code and the whole run is
   void. Guard sabotages invert the second gate, requiring the output to be unchanged
   and the suite to fail anyway.
9. **This README.** It must have a Status section holding real pasted output, no
   scaffold markers outside fenced code blocks, and counts that match the run.
10. **The tree is unchanged.** Every tracked file is digested before and after, and
    any modification or new untracked file is a named failure.

A sabotage run found a real defect while this was being built: removing the guard
against a zero effect size changed nothing, because the solver raised the same
exception type from its bracket. The test asserted the type and not the message, so it
passed against a broken guard. Both were fixed. A second defect, a plateau in the
Student t CDF near zero at large degrees of freedom that made the quantile search
converge to the edge of it rather than the root, was found by a round-trip test.

## Layout

```
src/distributions.py   normal, Student t, and two independent noncentral t routines
src/power.py           design effects, power, sample size, the curves
src/power.js           the same engine in JavaScript, for the page
src/cli.py             JSON on stdout
reference/             the reference table and the provenance of every value in it
tests/test_power.py    the unit suite
scripts/verify.sh      the ten stages above; its exit code is the result
docs/index.html        the generated page
```

## Status

Verbatim output of `bash scripts/verify.sh`, run on 2026-08-07. Each stage's output is
tailed by the script, so what appears below is the last lines of each rather than
every line; the exit code covers all of them. Rerunning reproduces this exactly apart
from the elapsed time on the unit test line.

```
$ bash scripts/verify.sh
cluster-trial-power verify
python: Python 3.12.3
node:   v24.13.0
R:      absent, see README on what validation this run does and does not establish
tracked files digested: 23

=== unit tests ===
----------------------------------------------------------------------
Ran 45 tests in 2.097s

OK
[ok] unit tests

=== reference values against published sources, with negative controls ===
      t quantile taken at the wrong degrees of freedom, 44 instead of 46
  smd-060-040                                0.4027158416 rel  6.79e-03 = 6789603951.7x tol  rejected
      Cohen's arcsine h used where the standardised proportion difference was meant

reference rows: 44   negative controls: 13
reference check PASSED
[ok] reference values against published sources, with negative controls

=== python and javascript engines agree ===
parity cases: 1018, functions: 14, tolerance rel 1e-10 or abs 1e-12
worst relative anywhere:            1.109e-7  (nctCdf(5,46,11) python=5.731335929584706e-8 js=5.731336565315197e-8)
worst relative above 0.001:          6.295e-12  (nctCdf(-2,200,1) python=0.0014285477134704516 js=0.0014285477134614588)
worst absolute anywhere:            1.123e-12
parity check PASSED
[ok] python and javascript engines agree

=== independent monte carlo recomputation ===
few clusters, where the t correction bites       0.8771    0.0023      0.8764    +0.0007    0.29  ok
                                             simulated cluster sizes: mean 15.00 (asked 15), CV 0.000 (asked 0.0)
one sided                                        0.8501    0.0025      0.8449    +0.0052    2.06  ok
                                             simulated cluster sizes: mean 20.00 (asked 20), CV 0.000 (asked 0.0)
ICC zero, clustering irrelevant                  0.9567    0.0014      0.9556    +0.0011    0.75  ok
                                             simulated cluster sizes: mean 20.00 (asked 20), CV 0.000 (asked 0.0)
normal analysis, equal clusters                  0.7503    0.0031      0.7490    +0.0014    0.45  ok
                                             simulated cluster sizes: mean 20.00 (asked 20), CV 0.000 (asked 0.0)
normal analysis, unequal clusters CV 0.6         0.6774    0.0033      0.6764    +0.0010    0.32  ok
                                             simulated cluster sizes: mean 19.97 (asked 20), CV 0.599 (asked 0.6)
null effect, must reject at alpha                0.0504    0.0015      0.0500    +0.0004    0.26  ok
                                             simulated cluster sizes: mean 20.00 (asked 20), CV 0.000 (asked 0.0)

8 scenarios, 20000 replications each, seed 20260807, tolerance 4.0 Monte Carlo standard errors
Monte Carlo error is the honest limit here: at 20000 replications the standard error of a power near 0.8 is 0.0028, so this check can detect a systematic error of about 1 percent of power and no smaller.
independent check PASSED
[ok] independent monte carlo recomputation

=== published page rebuilds identically ===
docs/index.html matches what scripts/build_page.py produces
[ok] published page rebuilds identically

=== real headless chrome, desktop and 390px ===
browser expectations from the python engine: 34 clusters per arm, design effect 2.45, 44 reference rows to render
layout, 390px
  ok    the page still computes at 390px  34
  ok    the curves are still drawn at 390px
  ok    no element escapes the page at 390px  []
  ok    the document does not scroll sideways at 390px  scrollWidth 390 against clientWidth 390
  ok    body does not hedge with overflow-x hidden at 390px  body visible, html visible

browser check PASSED
[ok] real headless chrome, desktop and 390px

=== privacy scan with a positive control ===
positive control: 4 of 4 planted secrets found (aws access key id, github token, home directory path, openai style key)
negative control: ordinary prose does not match any pattern
scanned 23 tracked files against 11 patterns
privacy scan PASSED
[ok] privacy scan with a positive control

=== sabotage under the three gate rule, null control first ===
[ PROVEN  ] effect size validation removed  (guard, 1 site in src/power.py)
            a zero effect would run the solver to its bracket limit instead of failing
            fingerprint unchanged; output unchanged as a guard should be, and unit tests still fail

16 sabotages: 16 proven
sabotage run PASSED: all 16 applied, moved the measured output in the direction their kind requires, and were caught
[ok] sabotage under the three gate rule, null control first

=== README states the truth, including the counts ===
scaffold markers outside fenced blocks: 0
Status section carries the verify success line 'VERIFY PASSED'
counts claimed in the README: {'unit tests': 45, 'reference values': 44, 'negative controls': 13, 'parity cases': 1018, 'simulation scenarios': 8, 'sabotages': 16, 'browser assertions': 33}
counts observed in this run:  {'unit tests': 45, 'reference values': 44, 'negative controls': 13, 'parity cases': 1018, 'simulation scenarios': 8, 'sabotages': 16, 'browser assertions': 33}
README check PASSED
[ok] README states the truth, including the counts

=== tree unchanged by this run ===
[ok] all 23 tracked files have the same digest, and no new files appeared

========================================
VERIFY PASSED: 10 stages, 0 failures
$ echo $?
0
```

## Unfinished

- **No live R comparison.** R is not installed here. The gap is described in detail
  above. Installing R and running `pwr` and `clusterPower` would turn four
  documentation-recalled rows and the whole clusterPower section into measured
  agreement.
- **Only the two design effect models.** Kish and Eldridge, both for an analysis
  that weights individuals equally. An unweighted analysis of cluster means has a
  different one, `m rho + (1 - rho) m E[1/m]`, and it is not implemented.
- **No stepped wedge, no matched pairs, no covariate adjustment,** and no more than
  two arms.
- **Attrition is not modelled.** Inflate the answer yourself.
