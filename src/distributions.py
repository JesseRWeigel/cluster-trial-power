"""Distribution functions the power calculator needs, standard library only.

Nothing here imports numpy or scipy. The whole point of the project is that the
engine can be read, ported to the browser, and checked against printed tables, so
every routine below is a named published algorithm rather than a library call.

Routines and their sources:

  norm_cdf   complementary error function, math.erfc
  norm_ppf   Wichura (1988), Algorithm AS 241, the PPND16 branch
  betainc    regularised incomplete beta by the Lentz continued fraction,
             Press et al., Numerical Recipes, section 6.4
  t_cdf      Student t from betainc
  t_ppf      bracketed bisection on t_cdf, no derivative needed
  nct_cdf    noncentral t. Two independent routes:
               series      Lenth (1989), Algorithm AS 243
               quadrature  Gauss-Legendre over the chi density
             They agree to about 1e-12 over the range this calculator uses, and
             tests/test_distributions.py asserts that agreement, which is worth
             more than either route alone.
"""

from __future__ import annotations

import math

__all__ = [
    "norm_cdf",
    "norm_ppf",
    "betainc",
    "t_cdf",
    "t_ppf",
    "nct_cdf",
    "chi_pdf",
]


# --------------------------------------------------------------------------
# normal
# --------------------------------------------------------------------------


def norm_cdf(x: float) -> float:
    """Standard normal CDF."""
    return 0.5 * math.erfc(-x / math.sqrt(2.0))


# Wichura AS 241, PPND16. Relative accuracy about 1e-16 over the whole range.
_A = (
    3.3871328727963666080e0,
    1.3314166789178437745e2,
    1.9715909503065514427e3,
    1.3731693765509461125e4,
    4.5921953931549871457e4,
    6.7265770927008700853e4,
    3.3430575583588128105e4,
    2.5090809287301226727e3,
)
_B = (
    1.0,
    4.2313330701600911252e1,
    6.8718700749205790830e2,
    5.3941960214247511077e3,
    2.1213794301586595867e4,
    3.9307895800092710610e4,
    2.8729085735721942674e4,
    5.2264952788528545610e3,
)
_C = (
    1.42343711074968357734e0,
    4.63033784615654529590e0,
    5.76949722146069140550e0,
    3.64784832476320460504e0,
    1.27045825245236838258e0,
    2.41780725177450611770e-1,
    2.27238449892691845833e-2,
    7.74545014278341407640e-4,
)
_D = (
    1.0,
    2.05319162663775882187e0,
    1.67638483018380384940e0,
    6.89767334985100004550e-1,
    1.48103976427480074590e-1,
    1.51986665636164571966e-2,
    5.47593808499534494600e-4,
    1.05075007164441684324e-9,
)
_E = (
    6.65790464350110377720e0,
    5.46378491116411436990e0,
    1.78482653991729133580e0,
    2.96560571828504891230e-1,
    2.65321895265761230930e-2,
    1.24266094738807843860e-3,
    2.71155556874348757815e-5,
    2.01033439929228813265e-7,
)
_F = (
    1.0,
    5.99832206555887937690e-1,
    1.36929880922735805310e-1,
    1.48753612908506148525e-2,
    7.86869131145613259100e-4,
    1.84631831751005468180e-5,
    1.42151175831644588870e-7,
    2.04426310338993978564e-15,
)


def _poly8(coef, r: float) -> float:
    out = 0.0
    for c in reversed(coef):
        out = out * r + c
    return out


def norm_ppf(p: float) -> float:
    """Standard normal quantile. Wichura (1988) AS 241, PPND16 branch."""
    if not (0.0 < p < 1.0):
        raise ValueError(f"norm_ppf needs 0 < p < 1, got {p}")
    q = p - 0.5
    if abs(q) <= 0.425:
        r = 0.180625 - q * q
        return q * _poly8(_A, r) / _poly8(_B, r)
    r = p if q < 0 else 1.0 - p
    r = math.sqrt(-math.log(r))
    if r <= 5.0:
        r -= 1.6
        value = _poly8(_C, r) / _poly8(_D, r)
    else:
        r -= 5.0
        value = _poly8(_E, r) / _poly8(_F, r)
    return -value if q < 0 else value


# --------------------------------------------------------------------------
# incomplete beta and Student t
# --------------------------------------------------------------------------

_FPMIN = 1e-300
_BETA_EPS = 3e-16
_BETA_MAXIT = 500


def _betacf(a: float, b: float, x: float) -> float:
    """Continued fraction for the incomplete beta, modified Lentz method."""
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < _FPMIN:
        d = _FPMIN
    d = 1.0 / d
    h = d
    for m in range(1, _BETA_MAXIT + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < _FPMIN:
            d = _FPMIN
        c = 1.0 + aa / c
        if abs(c) < _FPMIN:
            c = _FPMIN
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < _FPMIN:
            d = _FPMIN
        c = 1.0 + aa / c
        if abs(c) < _FPMIN:
            c = _FPMIN
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < _BETA_EPS:
            return h
    raise ArithmeticError(f"incomplete beta did not converge for a={a}, b={b}, x={x}")


def betainc(a: float, b: float, x: float) -> float:
    """Regularised incomplete beta I_x(a, b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    front = math.exp(
        math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
        + a * math.log(x) + b * math.log1p(-x)
    )
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - math.exp(
        math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
        + b * math.log1p(-x) + a * math.log(x)
    ) * _betacf(b, a, 1.0 - x) / b


def t_cdf(t: float, df: float) -> float:
    """Student t CDF."""
    if df <= 0:
        raise ValueError(f"t_cdf needs df > 0, got {df}")
    if t == 0.0:
        return 0.5
    x = df / (df + t * t)
    tail = 0.5 * betainc(0.5 * df, 0.5, x)
    return 1.0 - tail if t > 0 else tail


def t_ppf(p: float, df: float) -> float:
    """Student t quantile by bisection on t_cdf.

    Bisection rather than Newton because it cannot diverge, and 200 halvings of a
    bracket that starts inside +/- 1e6 leaves nothing measurable on the table.
    """
    if not (0.0 < p < 1.0):
        raise ValueError(f"t_ppf needs 0 < p < 1, got {p}")
    if df <= 0:
        raise ValueError(f"t_ppf needs df > 0, got {df}")
    lo, hi = -1e6, 1e6
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if t_cdf(mid, df) < p:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-13 * max(1.0, abs(lo)):
            break
    return 0.5 * (lo + hi)


# --------------------------------------------------------------------------
# noncentral t
# --------------------------------------------------------------------------


def _nct_cdf_series(t: float, df: float, ncp: float) -> float:
    """Lenth (1989) AS 243. Valid for t >= 0; the caller reflects negative t."""
    x = t * t / (t * t + df)
    if x <= 0.0:
        return norm_cdf(-ncp)

    half_d2 = 0.5 * ncp * ncp
    # p_j and q_j are the Poisson-like weights of AS 243:
    #   p_j = exp(-d^2/2) (d^2/2)^j / j!
    #   q_j = exp(-d^2/2) (d^2/2)^j d / (sqrt(2) Gamma(j + 3/2))
    # At j = 0, Gamma(3/2) = sqrt(pi)/2, so q_0 = d exp(-d^2/2) sqrt(2/pi).
    p = math.exp(-half_d2)
    q = math.sqrt(2.0 / math.pi) * ncp * math.exp(-half_d2)

    total = 0.0
    a = 0.5
    b = 0.5 * df
    ibeta_p = betainc(a, b, x)          # I_x(1/2, df/2)
    ibeta_q = betainc(a + 0.5, b, x)    # I_x(1, df/2)

    # Stepping the first argument of the incomplete beta up by one:
    #   I_x(a+1, b) = I_x(a, b) - Gamma(a+b) / (Gamma(a+1) Gamma(b)) x^a (1-x)^b
    def _step_term(a_val: float) -> float:
        return math.exp(
            math.lgamma(a_val + b) - math.lgamma(a_val + 1.0) - math.lgamma(b)
            + a_val * math.log(x) + b * math.log1p(-x)
        )

    term_p = _step_term(a)
    term_q = _step_term(a + 0.5)

    for j in range(0, 1000):
        total += p * ibeta_p + q * ibeta_q
        if j > half_d2 and (p + q) * (ibeta_p + ibeta_q) < 1e-17:
            break
        # I_x(a+1, b) = I_x(a, b) - term,  term = Gamma(a+b)/(Gamma(a+1)Gamma(b)) x^a (1-x)^b
        ibeta_p -= term_p
        ibeta_q -= term_q
        term_p *= x * (a + b + j) / (a + j + 1.0)
        term_q *= x * (a + 0.5 + b + j) / (a + 1.5 + j)
        p *= half_d2 / (j + 1.0)
        q *= half_d2 / (j + 1.5)
    else:  # pragma: no cover - only if the series genuinely fails to converge
        raise ArithmeticError(f"AS 243 series did not converge, t={t} df={df} ncp={ncp}")

    return min(1.0, max(0.0, norm_cdf(-ncp) + 0.5 * total))


# 64-point Gauss-Legendre nodes and weights on [-1, 1], generated once by Newton
# iteration on the Legendre polynomial. Computing them here keeps the table honest:
# a mistyped constant would show up immediately as disagreement with the series.
def _gauss_legendre(n: int):
    nodes, weights = [], []
    for i in range(1, n + 1):
        x = math.cos(math.pi * (i - 0.25) / (n + 0.5))
        for _ in range(100):
            p0, p1 = 1.0, 0.0
            for j in range(1, n + 1):
                p2 = p1
                p1 = p0
                p0 = ((2.0 * j - 1.0) * x * p1 - (j - 1.0) * p2) / j
            dp = n * (x * p0 - p1) / (x * x - 1.0)
            dx = -p0 / dp
            x += dx
            if abs(dx) < 1e-15:
                break
        nodes.append(x)
        weights.append(2.0 / ((1.0 - x * x) * dp * dp))
    return nodes, weights


_GL_N = 128
_GL_NODES, _GL_WEIGHTS = _gauss_legendre(_GL_N)


def chi_pdf(u: float, df: float) -> float:
    """Density of the chi distribution with df degrees of freedom (not chi squared)."""
    if u <= 0.0:
        return 0.0
    log_pdf = (
        (df - 1.0) * math.log(u)
        - 0.5 * u * u
        - (0.5 * df - 1.0) * math.log(2.0)
        - math.lgamma(0.5 * df)
    )
    return math.exp(log_pdf)


def _nct_cdf_quadrature(t: float, df: float, ncp: float) -> float:
    """P(T' <= t) by integrating the normal CDF against the chi density.

    If S ~ chi_df / sqrt(df) then T' = (Z + ncp) / S, so

        P(T' <= t) = E_u[ Phi( t * u / sqrt(df) - ncp ) ],  u ~ chi_df.

    This shares no algebra with the AS 243 series, which is why both are kept.
    """
    mean = math.sqrt(2.0) * math.exp(math.lgamma(0.5 * (df + 1.0)) - math.lgamma(0.5 * df))
    sd = math.sqrt(max(df - mean * mean, 1e-12))
    lo = max(1e-12, mean - 14.0 * sd)
    hi = mean + 14.0 * sd
    half, mid = 0.5 * (hi - lo), 0.5 * (hi + lo)
    total = 0.0
    scale = t / math.sqrt(df)
    for node, weight in zip(_GL_NODES, _GL_WEIGHTS):
        u = mid + half * node
        total += weight * chi_pdf(u, df) * norm_cdf(scale * u - ncp)
    return min(1.0, max(0.0, half * total))


def nct_cdf(t: float, df: float, ncp: float, method: str = "auto") -> float:
    """Noncentral t CDF, P(T' <= t) for T' with df degrees of freedom and given ncp.

    method:
      "auto"        series where AS 243 is reliable, quadrature elsewhere
      "series"      Lenth (1989) AS 243
      "quadrature"  Gauss-Legendre over the chi density
    """
    if df <= 0:
        raise ValueError(f"nct_cdf needs df > 0, got {df}")
    if method == "quadrature":
        return _nct_cdf_quadrature(t, df, ncp)
    if method == "auto":
        # AS 243 sums about ncp^2/2 Poisson terms and loses digits once that count
        # grows large, so hand those cases to the quadrature.
        if abs(ncp) > 12.0:
            return _nct_cdf_quadrature(t, df, ncp)
    if t >= 0.0:
        return _nct_cdf_series(t, df, ncp)
    return 1.0 - _nct_cdf_series(-t, df, -ncp)
