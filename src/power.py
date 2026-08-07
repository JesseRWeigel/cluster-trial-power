"""Power and sample size for two-arm trials, individually or cluster randomised.

The one thing this calculator does that most online ones do not is apply the design
effect. For a trial that randomises clusters of m people with intracluster
correlation rho, the variance of a treatment mean is inflated by

    DEFF = 1 + (m - 1) * rho                                    (Kish 1965)

and the required number of individuals is the individually randomised requirement
multiplied by DEFF. At m = 30 and rho = 0.05 that factor is 2.45, so a trial powered
for 200 people needs 490. Omitting it does not make a study slightly optimistic, it
makes it underpowered by a factor that grows with cluster size.

Cluster sizes are never equal in practice. Writing CV for the coefficient of
variation of cluster size, the inflation becomes

    DEFF = 1 + ((1 + CV^2) * m_bar - 1) * rho                   (Eldridge et al. 2006)

which reduces to the Kish form exactly when CV = 0. A common shorthand is that
unequal sizes cost a further factor of (1 + CV^2). That shorthand is the large
m_bar * rho limit of the expression above: the ratio of the two design effects is
(1 + CV^2) - CV^2 * (1 - rho) / DEFF_kish, which tends to (1 + CV^2) as DEFF_kish
grows and is smaller than it otherwise. This module uses the exact expression and
reports the shorthand alongside so the difference is visible.

What constrains a cluster trial is the number of CLUSTERS, not the number of people.
Adding people to existing clusters buys progressively less: as m goes to infinity the
effective sample size per arm tends to k / rho, a hard ceiling set by the number of
clusters k. Both numbers are reported everywhere.

Degrees of freedom. With few clusters the normal approximation overstates power. The
analysis of a cluster trial has as many independent units as it has clusters, so the
t distribution on (total clusters - 2) degrees of freedom is the appropriate
reference. That is df = 2k - 2 for k clusters per arm, which is the same rule as
Hayes and Moulton's 2(c - 1). Every result records which rule produced it.

Sidedness and effect size type are explicit arguments with no default that hides the
choice, because conflating a one-sided with a two-sided test, or Cohen's d with
Cohen's arcsine h, is the second most common error after omitting the design effect.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, asdict, field

try:  # allow both `import power` and `from src import power`
    from .distributions import norm_cdf, norm_ppf, nct_cdf, t_ppf
except ImportError:  # pragma: no cover - exercised by the CLI and the tests
    from distributions import norm_cdf, norm_ppf, nct_cdf, t_ppf

__all__ = [
    "design_effect",
    "deff_shorthand_ratio",
    "cohen_h",
    "proportion_smd",
    "standardised_effect",
    "power_two_sample",
    "n_two_sample",
    "power_crt",
    "clusters_crt",
    "effective_n_per_arm",
    "CRTResult",
    "power_curve_clusters",
    "operating_characteristic",
]

DEFF_MODELS = ("eldridge", "kish")
DF_RULES = ("cluster_t", "normal", "individual_t")
TEST_METHODS = ("t", "normal")
EFFECT_KINDS = ("d", "smd", "cohen_h", "proportion_difference")


# --------------------------------------------------------------------------
# design effect
# --------------------------------------------------------------------------


def design_effect(m: float, icc: float, cv: float = 0.0, model: str = "eldridge") -> float:
    """Variance inflation factor for a cluster randomised design.

    m      average cluster size (number of individuals per cluster)
    icc    intracluster correlation, 0 <= icc <= 1
    cv     coefficient of variation of cluster size, 0 for equal clusters
    model  "eldridge" for 1 + ((1 + cv^2) m - 1) icc, the default
           "kish"     for 1 + (m - 1) icc, which ignores cv entirely
    """
    if m <= 0:
        raise ValueError(f"cluster size must be positive, got {m}")
    if not (0.0 <= icc <= 1.0):
        raise ValueError(f"icc must lie in [0, 1], got {icc}")
    if cv < 0.0:
        raise ValueError(f"cv must be non-negative, got {cv}")
    if model not in DEFF_MODELS:
        raise ValueError(f"unknown design effect model {model!r}, expected one of {DEFF_MODELS}")
    if model == "kish":
        return 1.0 + (m - 1.0) * icc
    return 1.0 + ((1.0 + cv * cv) * m - 1.0) * icc


def deff_shorthand_ratio(m: float, icc: float, cv: float) -> dict:
    """Compare the exact unequal-size inflation with the (1 + CV^2) shorthand.

    Returned so a caller can say what assuming equal clusters costs, and how far the
    common shorthand is from the exact factor at this m and icc.
    """
    equal = design_effect(m, icc, 0.0)
    exact = design_effect(m, icc, cv)
    shorthand = equal * (1.0 + cv * cv)
    return {
        "deff_equal_sizes": equal,
        "deff_unequal_sizes": exact,
        "deff_shorthand": shorthand,
        "exact_over_equal": exact / equal,
        "shorthand_over_equal": shorthand / equal,
        "shorthand_error": shorthand - exact,
    }


# --------------------------------------------------------------------------
# effect sizes
# --------------------------------------------------------------------------


def cohen_h(p1: float, p2: float) -> float:
    """Cohen's arcsine effect size for two proportions, the pwr.2p.test input."""
    for p in (p1, p2):
        if not (0.0 <= p <= 1.0):
            raise ValueError(f"proportion must lie in [0, 1], got {p}")
    return 2.0 * math.asin(math.sqrt(p1)) - 2.0 * math.asin(math.sqrt(p2))


def proportion_smd(p1: float, p2: float) -> float:
    """Standardised mean difference for a binary outcome.

    (p1 - p2) divided by the standard deviation at the average of the two
    proportions. This is NOT Cohen's h and gives a different answer; which one is
    right depends on the analysis you plan. Reported separately everywhere.
    """
    for p in (p1, p2):
        if not (0.0 <= p <= 1.0):
            raise ValueError(f"proportion must lie in [0, 1], got {p}")
    pbar = 0.5 * (p1 + p2)
    var = pbar * (1.0 - pbar)
    if var <= 0.0:
        raise ValueError("both proportions are 0 or both are 1, no effect is defined")
    return (p1 - p2) / math.sqrt(var)


def standardised_effect(kind: str, **kwargs) -> float:
    """Turn a user-facing effect size into the standardised effect the maths uses.

    kind = "d" or "smd"                 value=<Cohen's d / standardised mean difference>
    kind = "cohen_h"                    p1=, p2=   (arcsine transformed)
    kind = "proportion_difference"      p1=, p2=   (difference over pooled SD)
    """
    if kind in ("d", "smd"):
        return float(kwargs["value"])
    if kind == "cohen_h":
        return cohen_h(float(kwargs["p1"]), float(kwargs["p2"]))
    if kind == "proportion_difference":
        return proportion_smd(float(kwargs["p1"]), float(kwargs["p2"]))
    raise ValueError(f"unknown effect kind {kind!r}, expected one of {EFFECT_KINDS}")


# --------------------------------------------------------------------------
# individually randomised two-sample test
# --------------------------------------------------------------------------


def _critical_alpha(alpha: float, sides: int) -> float:
    if not (0.0 < alpha < 1.0):
        raise ValueError(f"alpha must lie in (0, 1), got {alpha}")
    if sides not in (1, 2):
        raise ValueError(f"sides must be 1 or 2, got {sides}")
    return alpha / sides


def power_two_sample(
    effect: float,
    n_per_arm: float,
    alpha: float = 0.05,
    sides: int = 2,
    method: str = "t",
) -> float:
    """Power of a two-sample comparison with n_per_arm individuals in each arm.

    method "t"      noncentral t on 2n - 2 degrees of freedom, what pwr.t.test does
    method "normal" the normal approximation, which ignores the estimation of the
                    variance and is optimistic at small n
    """
    if method not in TEST_METHODS:
        raise ValueError(f"unknown method {method!r}, expected one of {TEST_METHODS}")
    if n_per_arm <= 1:
        return alpha / sides  # nothing to estimate the variance with
    tail = _critical_alpha(alpha, sides)
    ncp = abs(effect) * math.sqrt(n_per_arm / 2.0)
    if method == "normal":
        crit = norm_ppf(1.0 - tail)
        power = 1.0 - norm_cdf(crit - ncp)
        if sides == 2:
            power += norm_cdf(-crit - ncp)
        return power
    df = 2.0 * n_per_arm - 2.0
    crit = t_ppf(1.0 - tail, df)
    power = 1.0 - nct_cdf(crit, df, ncp)
    if sides == 2:
        power += nct_cdf(-crit, df, ncp)
    return power


def _solve_increasing(f, target: float, lo: float, hi: float, tol: float = 1e-10) -> float:
    """Bisection for the smallest x in [lo, hi] with f(x) = target, f increasing."""
    f_lo, f_hi = f(lo), f(hi)
    if f_lo >= target:
        return lo
    if f_hi < target:
        raise ValueError(
            f"target {target} not reachable on [{lo}, {hi}]; f(hi) = {f_hi}. "
            "Widen the bracket or accept less power."
        )
    for _ in range(300):
        mid = 0.5 * (lo + hi)
        if f(mid) < target:
            lo = mid
        else:
            hi = mid
        if hi - lo <= tol * max(1.0, abs(lo)):
            break
    return 0.5 * (lo + hi)


def n_two_sample(
    effect: float,
    power: float = 0.80,
    alpha: float = 0.05,
    sides: int = 2,
    method: str = "t",
) -> float:
    """Individuals per arm for an individually randomised trial. Continuous, not rounded.

    Left unrounded on purpose so it can be compared against pwr.t.test, which also
    returns a non-integer n. Round up before quoting it to anybody.
    """
    if not (0.0 < power < 1.0):
        raise ValueError(f"power must lie in (0, 1), got {power}")
    if effect == 0.0:
        raise ValueError("an effect size of zero needs an infinite sample")
    if method == "normal":
        # Closed form, no iteration: n = 2 (z_{1-alpha/sides} + z_{power})^2 / d^2.
        # The lower tail of the two-sided test is dropped here, which is the
        # textbook formula; power_two_sample keeps it, so the two differ by the
        # negligible probability of rejecting in the wrong direction.
        za = norm_ppf(1.0 - _critical_alpha(alpha, sides))
        zb = norm_ppf(power)
        return 2.0 * (za + zb) ** 2 / (effect * effect)
    return _solve_increasing(
        lambda n: power_two_sample(effect, n, alpha, sides, method),
        power,
        lo=2.0 + 1e-9,
        hi=1e7,
    )


# --------------------------------------------------------------------------
# cluster randomised trial
# --------------------------------------------------------------------------


def effective_n_per_arm(k_per_arm: float, m: float, icc: float, cv: float = 0.0,
                        deff_model: str = "eldridge") -> float:
    """Individuals per arm divided by the design effect: the effective sample size."""
    return k_per_arm * m / design_effect(m, icc, cv, deff_model)


def power_crt(
    effect: float,
    m: float,
    icc: float,
    k_per_arm: float,
    cv: float = 0.0,
    alpha: float = 0.05,
    sides: int = 2,
    df_rule: str = "cluster_t",
    deff_model: str = "eldridge",
) -> float:
    """Power of a two-arm cluster randomised trial.

    k_per_arm  clusters allocated to each arm
    df_rule    "cluster_t"     t on (total clusters - 2) = 2k - 2 degrees of freedom
               "normal"        normal approximation, no degrees of freedom
               "individual_t"  t on (total individuals - 2), which treats people as
                               independent units. Wrong for a cluster trial and kept
                               only so the tests can show how wrong.
    """
    if df_rule not in DF_RULES:
        raise ValueError(f"unknown df rule {df_rule!r}, expected one of {DF_RULES}")
    if k_per_arm <= 0:
        raise ValueError(f"clusters per arm must be positive, got {k_per_arm}")
    n_eff = effective_n_per_arm(k_per_arm, m, icc, cv, deff_model)
    tail = _critical_alpha(alpha, sides)
    ncp = abs(effect) * math.sqrt(n_eff / 2.0)

    if df_rule == "normal":
        crit = norm_ppf(1.0 - tail)
        power = 1.0 - norm_cdf(crit - ncp)
        if sides == 2:
            power += norm_cdf(-crit - ncp)
        return power

    df = 2.0 * k_per_arm - 2.0 if df_rule == "cluster_t" else 2.0 * k_per_arm * m - 2.0
    if df <= 0:
        raise ValueError(
            f"df rule {df_rule!r} gives {df} degrees of freedom at k={k_per_arm}; "
            "a cluster trial needs at least 2 clusters per arm"
        )
    crit = t_ppf(1.0 - tail, df)
    power = 1.0 - nct_cdf(crit, df, ncp)
    if sides == 2:
        power += nct_cdf(-crit, df, ncp)
    return power


@dataclass
class CRTResult:
    """Everything a reader needs to see, including the answer they would have got wrong."""

    effect: float
    effect_kind: str
    target_power: float
    alpha: float
    sides: int
    icc: float
    cluster_size: float
    cv_cluster_size: float
    df_rule: str
    deff_model: str

    design_effect: float
    design_effect_equal_sizes: float
    clusters_per_arm: int
    clusters_total: int
    individuals_per_arm: int
    individuals_total: int
    effective_n_per_arm: float
    achieved_power: float
    degrees_of_freedom: float | None

    n_individually_randomised_per_arm: float
    n_individually_randomised_total: int
    inflation_vs_individual: float
    cost_of_assuming_equal_clusters: dict = field(default_factory=dict)
    notes: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def clusters_crt(
    effect: float,
    m: float,
    icc: float,
    cv: float = 0.0,
    power: float = 0.80,
    alpha: float = 0.05,
    sides: int = 2,
    df_rule: str = "cluster_t",
    deff_model: str = "eldridge",
    effect_kind: str = "d",
    max_clusters_per_arm: int = 100000,
) -> CRTResult:
    """Smallest integer number of clusters per arm reaching the target power.

    Searched as an integer rather than derived from a rounded-up continuous n,
    because with the t correction the degrees of freedom depend on the answer and
    the continuous solution can round to a k that misses the target.
    """
    if m < 1:
        raise ValueError(f"cluster size must be at least 1, got {m}")
    deff = design_effect(m, icc, cv, deff_model)
    n_ind = n_two_sample(effect, power, alpha, sides,
                         method="normal" if df_rule == "normal" else "t")

    def power_at(k: float) -> float:
        return power_crt(effect, m, icc, k, cv, alpha, sides, df_rule, deff_model)

    k_start = max(2, int(math.floor(n_ind * deff / m)))
    k = k_start
    while k <= max_clusters_per_arm and power_at(k) < power:
        k += 1
    if k > max_clusters_per_arm:
        raise ValueError(
            f"target power {power} needs more than {max_clusters_per_arm} clusters per arm "
            f"at effect={effect}, m={m}, icc={icc}. The design is not feasible as specified."
        )
    # The search walks up, so step back down in case k_start was already too large.
    while k > 2 and power_at(k - 1) >= power:
        k -= 1

    notes = []
    if k < 15:
        notes.append(
            f"{2 * k} clusters in total is few. Below about 30 the t correction matters "
            "and covariate imbalance between arms is likely; consider stratified or "
            "matched allocation."
        )
    if icc == 0.0:
        notes.append(
            "ICC is exactly 0, so the design effect is 1 and the answer equals the "
            "individually randomised requirement."
        )
    if cv > 0.0:
        notes.append(
            "Unequal cluster sizes are accounted for through the Eldridge et al. (2006) "
            "design effect. Assuming equal sizes would understate the requirement."
        )
    if m > 1 and icc > 0:
        ceiling = k / icc
        notes.append(
            f"Adding people to existing clusters cannot push effective sample size per arm "
            f"above k/ICC = {ceiling:.1f}. More clusters is the only way past that."
        )

    return CRTResult(
        effect=effect,
        effect_kind=effect_kind,
        target_power=power,
        alpha=alpha,
        sides=sides,
        icc=icc,
        cluster_size=m,
        cv_cluster_size=cv,
        df_rule=df_rule,
        deff_model=deff_model,
        design_effect=deff,
        design_effect_equal_sizes=design_effect(m, icc, 0.0, deff_model),
        clusters_per_arm=k,
        clusters_total=2 * k,
        individuals_per_arm=int(math.ceil(k * m)),
        individuals_total=int(math.ceil(2 * k * m)),
        effective_n_per_arm=effective_n_per_arm(k, m, icc, cv, deff_model),
        achieved_power=power_at(k),
        degrees_of_freedom=None if df_rule == "normal" else (
            2.0 * k - 2.0 if df_rule == "cluster_t" else 2.0 * k * m - 2.0
        ),
        n_individually_randomised_per_arm=n_ind,
        n_individually_randomised_total=int(math.ceil(2 * n_ind)),
        inflation_vs_individual=(2 * k * m) / (2 * n_ind),
        cost_of_assuming_equal_clusters=deff_shorthand_ratio(m, icc, cv),
        notes=notes,
    )


# --------------------------------------------------------------------------
# curves
# --------------------------------------------------------------------------


def power_curve_clusters(
    effect: float, m: float, icc: float, cv: float = 0.0, alpha: float = 0.05,
    sides: int = 2, df_rule: str = "cluster_t", deff_model: str = "eldridge",
    k_min: int = 2, k_max: int = 60,
) -> list:
    """Power against clusters per arm. The curve the widget draws on its x axis."""
    return [
        {"k_per_arm": k,
         "individuals_total": int(math.ceil(2 * k * m)),
         "power": power_crt(effect, m, icc, k, cv, alpha, sides, df_rule, deff_model)}
        for k in range(k_min, k_max + 1)
    ]


def operating_characteristic(
    k_per_arm: int, m: float, icc: float, cv: float = 0.0, alpha: float = 0.05,
    sides: int = 2, df_rule: str = "cluster_t", deff_model: str = "eldridge",
    effect_min: float = 0.0, effect_max: float = 1.0, points: int = 101,
) -> list:
    """The operating characteristic of a fixed design, over the true effect size.

    Strictly the operating characteristic is the probability of NOT rejecting, so
    both are returned: "power" and "accept_null" = 1 - power. At a true effect of
    zero, power equals the significance level, which is a useful thing to be able to
    read off the curve.
    """
    out = []
    for i in range(points):
        d = effect_min + (effect_max - effect_min) * i / (points - 1)
        if d == 0.0:
            pw = alpha  # by construction of the test, at the nominal level
        else:
            pw = power_crt(d, m, icc, k_per_arm, cv, alpha, sides, df_rule, deff_model)
        out.append({"effect": d, "power": pw, "accept_null": 1.0 - pw})
    return out
