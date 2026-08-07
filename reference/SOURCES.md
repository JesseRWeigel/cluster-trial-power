# Reference values: where each one comes from, and what it proves

`which R` and `which Rscript` both return nothing on the machine this was built on. No
number in `reference_values.json` was produced by running R. This file says where each
one did come from and, just as importantly, what each class of value can and cannot
establish.

## Provenance classes

| class | meaning | tolerance rule |
|---|---|---|
| `published_table` | a number printed in a standard statistical table | half a unit in the last printed place, expressed as a relative tolerance |
| `published_package_output` | a numeric output of an R package, recorded from its documentation rather than from a run on this machine | half a unit in the last significant figure claimed |
| `exact_arithmetic` | follows from a published formula by arithmetic anyone can redo on paper, written out below | 1e-12 relative |
| `structural_identity` | a relation that must hold whatever the numbers are, checked as exact floating point equality | 0 |
| `pinned_regression` | this implementation's own output, recorded so that a silent change is caught | 1e-12 relative |

`pinned_regression` rows are not evidence of correctness and are labelled so nobody
reads them as such. They exist to catch drift.

## Why the tolerance is relative

The quantities compared here run from 1.18 (a design effect) to 963.8 (a required N).
An absolute tolerance tight enough to mean something at N = 26 is satisfied by anything
at all at N = 963, and one loose enough for N = 963 accepts a 4 percent error at N = 26.
Relative tolerance is the only choice that means the same thing across three orders of
magnitude.

Each tolerance is derived from the precision of the source rather than chosen. For a
table printing three decimals the tolerance is 0.0005 / |expected|. Deriving it removes
the temptation to widen it until the test passes. `scripts/check_reference.py` then
proves the result is tight enough to matter by running six deliberately wrong
calculations against the same tolerances and requiring every one of them to be
rejected.

## Citations

- **Cohen, J. (1988).** *Statistical Power Analysis for the Behavioral Sciences*, 2nd
  edition. Lawrence Erlbaum. Table 2.4.1 tabulates n per group for the two-tailed t
  test at alpha = .05 against d and desired power.
- **Kish, L. (1965).** *Survey Sampling*. Wiley. The design effect, DEFF = 1 + (m - 1)
  rho.
- **Donner, A. and Klar, N. (2000).** *Design and Analysis of Cluster Randomization
  Trials in Health Research*. Arnold. The variance inflation factor and its use in
  sample size calculation for cluster randomised trials.
- **Hayes, R. J. and Moulton, L. H. (2017).** *Cluster Randomised Trials*, 2nd edition.
  CRC Press. Sample size by number of clusters, and the point that the number of
  clusters is what constrains the design.
- **Eldridge, S. M., Ashby, D. and Kerry, S. (2006).** Sample size for cluster
  randomized trials: effect of coefficient of variation of cluster size and analysis
  method. *International Journal of Epidemiology* 35(5), 1292-1300. The design effect
  1 + ((CV^2 + 1) m - 1) rho for unequal cluster sizes.
- **van Breukelen, G. J. P., Candel, M. J. J. M. and Berger, M. P. F. (2007).**
  Relative efficiency of unequal versus equal cluster sizes in cluster randomized and
  multicentre trials. *Statistics in Medicine* 26(13), 2589-2603.
- **pwr** R package. `pwr.t.test(type = "two.sample")` places the noncentrality at
  d sqrt(n / 2) with n per group and uses the noncentral t on 2n - 2 degrees of
  freedom. `pwr.2p.test` takes Cohen's arcsine h and uses the normal approximation.
- **clusterPower** R package, `cpa.normal` (formerly `crtpwr.2mean`). Its documented
  model is a noncentral t on 2(k - 1) degrees of freedom with noncentrality
  d sqrt(k m / (2 DEFF)), which is the model implemented here under `df_rule =
  "cluster_t"`.
- **Lenth, R. V. (1989).** Algorithm AS 243: Cumulative distribution function of the
  non-central t distribution. *Applied Statistics* 38(1), 185-189.
- **Wichura, M. J. (1988).** Algorithm AS 241: The percentage points of the normal
  distribution. *Applied Statistics* 37(3), 477-484.
- **Abramowitz, M. and Stegun, I. A. (1964).** *Handbook of Mathematical Functions*,
  tables 26.1 and 26.10, for the normal and Student t quantiles.
- **Fisher, R. A. and Yates, F. (1963).** *Statistical Tables for Biological,
  Agricultural and Medical Research*, 6th edition, Table III. The t critical values
  reproduced in the appendix of essentially every statistics textbook.

## Cohen Table 2.4.1 and the rounding rule

Cohen tabulates n per group at alpha = .05, two-tailed:

| d | power .80 | power .90 |
|---|---|---|
| 0.20 | 393 | 526 |
| 0.50 | 64 | 85 |
| 0.80 | 26 | 34 |

This calculator computes 393.40570, 526.33319, 63.76561, 85.03128, 25.52457, 33.82554.
Rounding to the nearest integer reproduces all six. Rounding up reproduces only three
of six, because 393.4 rounds up to 394 and 526.3 to 527. So the table rounds to
nearest, and the reference rows use that rule while the calculator itself reports the
ceiling, which is what you must actually recruit. Both are shown in the tests so the
difference cannot be mistaken for disagreement.

## The pwr rows, and their weakness

Four rows carry `published_package_output`. They are recorded from the pwr
documentation and from tutorials that reproduce it, not from a run on this machine.
The obvious risk is that a value recalled after seeing the computed one is not
independent of it. That risk is real and is the reason those rows are not the load
bearing part of the validation. What carries the weight instead:

1. The six Cohen rows are a printed book table, and they constrain the same
   calculation to the nearest integer.
2. At m = 1 and ICC = 0 the cluster code path reduces exactly to the individually
   randomised t test, degrees of freedom included (2k - 2 with k = n is 2n - 2). So
   every row above tests the cluster pipeline, not a separate simpler one.
3. `scripts/check_independent.py` recomputes power by Monte Carlo simulation of the
   trial itself, which shares no algebra with any of this.

## Arithmetic written out

Every `exact_arithmetic` row can be redone by hand. Using the published quantiles
z(0.975) = 1.959964 and z(0.80) = 0.8416212:

**Design effects, Kish.** DEFF = 1 + (m - 1) rho.
- m = 30, rho = 0.05: 1 + 29(0.05) = **2.45**
- m = 20, rho = 0.02: 1 + 19(0.02) = **1.38**
- m = 100, rho = 0.01: 1 + 99(0.01) = **1.99**
- m = 10, rho = 0.02: 1 + 9(0.02) = **1.18**

**Design effect with unequal cluster sizes, Eldridge.** DEFF = 1 + ((1 + CV^2) m - 1) rho.
- m = 30, rho = 0.05, CV = 0.65: (1 + 0.4225)(30) = 42.675, so 1 + 41.675(0.05) = **3.08375**
- The shorthand DEFF_equal (1 + CV^2) would give 2.45(1.4225) = 3.4851, which is 0.401
  too high, an overstatement of 13 percent at this m and rho. The shorthand is the
  large m rho limit and is conservative below it.

**Normal approximation sample size.** n per arm = 2 (z(1 - alpha/2) + z(power))^2 / d^2.
- d = 0.5: 2(1.959964 + 0.8416212)^2 / 0.25 = 2(2.8015852)^2 / 0.25 = 2(7.848880) / 0.25
  = **62.79104**
- d = 0.25: the same numerator over 0.0625 gives **251.16415**

**Clusters from the design effect, normal approximation, entirely by hand.**
d = 0.25, m = 25, rho = 0.05, equal clusters.
- DEFF = 1 + 24(0.05) = 2.2
- individuals per arm = 251.16415 x 2.2 = 552.5611
- clusters per arm = 552.5611 / 25 = 22.102, so **23 clusters per arm**, 46 in total,
  1150 individuals.
- The t correction pushes this to **24 clusters per arm** on 2k - 2 = 46 degrees of
  freedom. One extra cluster per arm is what the correction costs here, and it is not
  optional: at k = 23 the normal approximation reports power 0.81539 while the t based
  calculation reports 0.79816, below the 0.80 target.

**Cohen's h at proportions with exact arcsines.** h = 2 asin(sqrt(p1)) - 2 asin(sqrt(p2)).
- p1 = 0.75, p2 = 0.50: 2(pi/3) - 2(pi/4) = 2pi/3 - pi/2 = **pi/6 = 0.5235987755982988**

**Standardised effect for a proportion difference.** (p1 - p2) / sqrt(pbar(1 - pbar)).
- p1 = 0.6, p2 = 0.4: 0.2 / sqrt(0.25) = **0.4**, which the implementation returns as
  0.3999999999999999, one unit in the last place away and the reason this row uses the
  1e-12 relative tolerance rather than exact equality. Note this is not Cohen's h,
  which for the same pair is 0.4027. Conflating the two is a real and common error, so
  the calculator names which one it used in every result.

## The exact agreement case

At ICC = 0 the design effect is exactly 1 and a cluster randomised design must give
back the individually randomised answer. Three rows assert this as floating point
equality rather than as approximate agreement, because there is no arithmetic between
the two paths that should introduce any difference at all:

- `design_effect(m, 0, cv) == 1.0` for any m and any CV
- `power_crt(d, m, 0, k, df_rule="normal") == power_two_sample(d, k m, method="normal")`
- `power_crt(d, m, 0, k, df_rule="individual_t") == power_two_sample(d, k m, method="t")`

If any of those drift, something in the design effect, the effective sample size, the
noncentrality, or the critical value has changed, and the whole pipeline is implicated.

## The Hayes and Moulton cross-derivation

Hayes and Moulton size a trial from the between-cluster and within-cluster variances
directly, with no design effect anywhere in the expression:

    k per arm = 1 + (z(1 - alpha/2) + z(power))^2  2 (sigma_w^2 / m + sigma_b^2) / delta^2

Writing sigma^2 = sigma_w^2 + sigma_b^2 and rho = sigma_b^2 / sigma^2 and d = delta /
sigma, the design effect route gives

    k = (2 (z + z)^2 / d^2)(1 + (m - 1) rho) / m
      = 2 (z + z)^2 (sigma^2 + (m - 1) sigma_b^2) / (delta^2 m)
      = 2 (z + z)^2 (sigma_w^2 / m + sigma_b^2) / delta^2

which is the Hayes and Moulton expression exactly, without their leading +1. That +1 is
their deliberately simple substitute for a t correction. So the two published routes
agree algebraically, and `tests/test_power.py` checks the equality numerically as well,
which catches a transcription error in either one.
