#!/usr/bin/env python3
"""Unit tests for the power engine.

Three kinds of test here, and the third is the one that keeps the other two honest.

  properties      relations that must hold for every input, checked over a grid:
                  power rises with clusters, the answer is minimal, one sided needs
                  fewer people than two sided.
  identities      relations that must hold to the last bit, most importantly that at
                  ICC = 0 a cluster design gives back the individually randomised
                  answer exactly.
  negative        a deliberately wrong version of each calculation, asserted to
  controls        produce a DIFFERENT answer. A test that passes whether or not the
                  code is right is worse than no test, so every agreement assertion
                  above has one of these beside it.
"""

from __future__ import annotations

import math
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

import distributions as dist  # noqa: E402
import power as P  # noqa: E402


class TestDistributions(unittest.TestCase):
    def test_norm_cdf_ppf_roundtrip(self):
        for p in (1e-9, 1e-4, 0.01, 0.3, 0.5, 0.7, 0.99, 1 - 1e-9):
            self.assertAlmostEqual(dist.norm_cdf(dist.norm_ppf(p)), p, delta=1e-12)

    def test_norm_symmetry(self):
        for x in (0.1, 1.0, 2.5, 4.0):
            self.assertAlmostEqual(dist.norm_cdf(x) + dist.norm_cdf(-x), 1.0, delta=1e-15)

    def test_t_cdf_ppf_roundtrip(self):
        for df in (1, 2, 5, 30, 200, 1e6):
            for p in (0.001, 0.025, 0.5, 0.975, 0.999):
                self.assertAlmostEqual(dist.t_cdf(dist.t_ppf(p, df), df), p, delta=1e-10)

    def test_t_approaches_normal(self):
        self.assertAlmostEqual(dist.t_ppf(0.975, 1e8), dist.norm_ppf(0.975), delta=1e-6)

    def test_nct_reduces_to_t_at_zero_ncp(self):
        for t, df in ((1.5, 7), (-2.3, 15), (0.4, 3), (2.0, 120)):
            self.assertAlmostEqual(dist.nct_cdf(t, df, 0.0), dist.t_cdf(t, df), delta=1e-13)

    def test_series_and_quadrature_agree(self):
        """AS 243 and Gauss-Legendre over the chi density share no algebra.

        Agreement between them is the main evidence that either is right, so it is
        checked over a grid rather than at a point. The criterion is relative where
        the probability is not tiny and absolute in the far tail, because a value of
        1e-23 agreeing to 1e-30 absolute is agreement in every sense that matters to
        a power calculation.
        """
        worst = 0.0
        checked = 0
        for df in (3, 10, 46, 200, 1000):
            for ncp in (0.0, 0.5, 2.0, 2.9, 6.0, 11.0):
                for t in (-2.0, 0.0, 1.5, 1.96, 2.5, 5.0):
                    a = dist.nct_cdf(t, df, ncp, method="series")
                    b = dist.nct_cdf(t, df, ncp, method="quadrature")
                    close = abs(a - b) <= 1e-11 + 1e-9 * abs(b)
                    self.assertTrue(
                        close,
                        f"series {a!r} vs quadrature {b!r} at t={t} df={df} ncp={ncp}",
                    )
                    # Relative agreement is asserted only where the probability is
                    # large enough for it to be meaningful. Both routes bottom out at
                    # an absolute 1e-14 or so, which at a probability of 3e-6 reads as
                    # a relative 1e-8 while being agreement to the last representable
                    # digit. A power calculation never turns on a probability of 1e-6.
                    if b > 1e-3:
                        worst = max(worst, abs(a - b) / b)
                    checked += 1
        self.assertGreater(checked, 150)
        self.assertLess(worst, 1e-10, f"worst relative disagreement {worst:.3e}")

    def test_nct_is_monotone_in_t(self):
        prev = -1.0
        for t in [x / 10 for x in range(-40, 41)]:
            v = dist.nct_cdf(t, 20, 1.7)
            self.assertGreaterEqual(v, prev)
            prev = v

    def test_bad_input_raises(self):
        for bad in (0.0, 1.0, -0.5, 1.5):
            with self.assertRaises(ValueError):
                dist.norm_ppf(bad)
        with self.assertRaises(ValueError):
            dist.t_ppf(0.5, 0)


class TestDesignEffect(unittest.TestCase):
    def test_kish_formula(self):
        self.assertEqual(P.design_effect(30, 0.05), 2.45)
        self.assertAlmostEqual(P.design_effect(20, 0.02), 1.38, delta=1e-15)

    def test_icc_zero_is_exactly_one(self):
        for m in (1, 5, 30, 1000):
            for cv in (0.0, 0.4, 1.7):
                self.assertEqual(P.design_effect(m, 0.0, cv), 1.0)

    def test_single_member_clusters_are_exactly_one(self):
        for icc in (0.0, 0.05, 0.5, 1.0):
            self.assertEqual(P.design_effect(1, icc, 0.0), 1.0)

    def test_eldridge_reduces_to_kish_at_cv_zero(self):
        for m in (2, 17, 250):
            for icc in (0.0, 0.01, 0.3):
                self.assertEqual(
                    P.design_effect(m, icc, 0.0, "eldridge"),
                    P.design_effect(m, icc, 0.0, "kish"),
                )

    def test_cv_inflates(self):
        self.assertGreater(P.design_effect(30, 0.05, 0.65), P.design_effect(30, 0.05, 0.0))

    def test_shorthand_is_conservative_and_named(self):
        """(1 + CV^2) is an upper bound approached only as m*icc grows."""
        for m, icc, cv in ((30, 0.05, 0.65), (10, 0.02, 0.3), (200, 0.2, 1.0)):
            r = P.deff_shorthand_ratio(m, icc, cv)
            self.assertGreaterEqual(r["deff_shorthand"], r["deff_unequal_sizes"])
            self.assertAlmostEqual(r["shorthand_over_equal"], 1 + cv * cv, delta=1e-12)
        big = P.deff_shorthand_ratio(100000, 0.5, 0.5)
        self.assertAlmostEqual(
            big["deff_shorthand"] / big["deff_unequal_sizes"], 1.0, delta=1e-4,
            msg="the shorthand should converge to the exact factor as m*icc grows",
        )

    def test_negative_control_off_by_one(self):
        wrong = 1.0 + 30 * 0.05
        self.assertNotAlmostEqual(wrong, P.design_effect(30, 0.05), delta=1e-6)

    def test_rejects_bad_input(self):
        with self.assertRaises(ValueError):
            P.design_effect(30, 1.5)
        with self.assertRaises(ValueError):
            P.design_effect(0, 0.05)
        with self.assertRaises(ValueError):
            P.design_effect(30, 0.05, -0.1)
        with self.assertRaises(ValueError):
            P.design_effect(30, 0.05, model="nonsense")


class TestEffectSizes(unittest.TestCase):
    def test_cohen_h_exact_case(self):
        self.assertAlmostEqual(P.cohen_h(0.75, 0.5), math.pi / 6, delta=1e-15)

    def test_h_is_antisymmetric(self):
        self.assertAlmostEqual(P.cohen_h(0.3, 0.7), -P.cohen_h(0.7, 0.3), delta=1e-15)

    def test_h_and_smd_differ(self):
        """Conflating them is a real error, so the test states the size of it."""
        h = P.cohen_h(0.6, 0.4)
        smd = P.proportion_smd(0.6, 0.4)
        self.assertAlmostEqual(smd, 0.4, delta=1e-12)
        self.assertAlmostEqual(h, 0.402716, delta=1e-6)
        self.assertNotAlmostEqual(h, smd, delta=1e-4)

    def test_dispatch(self):
        self.assertEqual(P.standardised_effect("d", value=0.3), 0.3)
        self.assertEqual(P.standardised_effect("smd", value=0.3), 0.3)
        self.assertEqual(P.standardised_effect("cohen_h", p1=0.6, p2=0.4), P.cohen_h(0.6, 0.4))
        self.assertEqual(
            P.standardised_effect("proportion_difference", p1=0.6, p2=0.4),
            P.proportion_smd(0.6, 0.4),
        )
        with self.assertRaises(ValueError):
            P.standardised_effect("cohens_d_probably", value=1)


class TestIndividualPower(unittest.TestCase):
    def test_power_rises_with_n(self):
        prev = 0.0
        for n in range(3, 200, 7):
            pw = P.power_two_sample(0.3, n)
            self.assertGreater(pw, prev)
            prev = pw

    def test_solved_n_hits_the_target(self):
        for d in (0.1, 0.25, 0.5, 1.2):
            for target in (0.5, 0.8, 0.9, 0.99):
                n = P.n_two_sample(d, target)
                self.assertAlmostEqual(P.power_two_sample(d, n), target, delta=1e-8)

    def test_one_sided_needs_fewer(self):
        two = P.n_two_sample(0.5, 0.8, 0.05, 2)
        one = P.n_two_sample(0.5, 0.8, 0.05, 1)
        self.assertLess(one, two)
        self.assertAlmostEqual(one / two, 0.786, delta=0.01)

    def test_normal_is_optimistic_relative_to_t(self):
        for d in (0.2, 0.5, 0.8):
            self.assertLess(
                P.n_two_sample(d, 0.8, method="normal"),
                P.n_two_sample(d, 0.8, method="t"),
            )

    def test_closed_form_matches_the_solver_under_the_normal_model(self):
        """The normal branch of n_two_sample is a closed form, so solve it numerically too.

        The closed form drops the probability of rejecting in the wrong direction,
        which is the textbook convention. So the numerical comparison uses the same
        one-tailed power expression at the two-sided critical value, and a second
        assertion bounds how much the dropped tail is worth.
        """
        z_crit = dist.norm_ppf(0.975)
        for d in (0.15, 0.5, 1.0):
            closed = P.n_two_sample(d, 0.8, 0.05, 2, "normal")
            solved = P._solve_increasing(
                lambda n: 1.0 - dist.norm_cdf(z_crit - d * math.sqrt(n / 2.0)),
                0.8, 2.001, 1e7,
            )
            self.assertAlmostEqual(closed, solved, delta=1e-8 * closed)
            # Keeping the wrong-direction tail makes the requirement slightly smaller.
            full = P._solve_increasing(
                lambda n: P.power_two_sample(d, n, 0.05, 2, "normal"), 0.8, 2.001, 1e7)
            self.assertLessEqual(full, closed)
            self.assertGreater(full, 0.999 * closed)

    def test_negative_control_wrong_sides(self):
        self.assertNotAlmostEqual(
            P.n_two_sample(0.5, 0.8, 0.05, 1), P.n_two_sample(0.5, 0.8, 0.05, 2), delta=1.0
        )

    def test_rejects_bad_input(self):
        # The message matters, not only the exception type. With the zero effect check
        # removed the solver still raises ValueError, from its bracket rather than
        # from the guard, so a bare assertRaises here passes on a broken guard. A
        # sabotage run found exactly that.
        with self.assertRaisesRegex(ValueError, "effect size of zero"):
            P.n_two_sample(0.0)
        with self.assertRaisesRegex(ValueError, "power must lie"):
            P.n_two_sample(0.5, power=1.0)
        with self.assertRaises(ValueError):
            P.power_two_sample(0.5, 30, alpha=0.0)
        with self.assertRaises(ValueError):
            P.power_two_sample(0.5, 30, sides=3)
        with self.assertRaises(ValueError):
            P.power_two_sample(0.5, 30, method="bayes")


class TestClusterPower(unittest.TestCase):
    def test_power_rises_with_clusters(self):
        prev = 0.0
        for k in range(2, 60):
            pw = P.power_crt(0.3, 20, 0.05, k)
            self.assertGreater(pw, prev)
            prev = pw

    def test_more_clusters_beats_more_people_per_cluster(self):
        """Doubling clusters beats doubling cluster size whenever the ICC is positive."""
        base = P.power_crt(0.3, 20, 0.05, 10)
        more_clusters = P.power_crt(0.3, 20, 0.05, 20)
        bigger_clusters = P.power_crt(0.3, 40, 0.05, 10)
        self.assertGreater(more_clusters, bigger_clusters)
        self.assertGreater(bigger_clusters, base)

    def test_effective_n_ceiling(self):
        """Effective n per arm cannot exceed k / ICC however large the clusters get."""
        k, icc = 12, 0.05
        for m in (10, 100, 10000, 10**7):
            self.assertLess(P.effective_n_per_arm(k, m, icc), k / icc)
        self.assertAlmostEqual(
            P.effective_n_per_arm(k, 10**9, icc), k / icc, delta=1e-3 * k / icc
        )

    def test_icc_zero_matches_individual_randomisation_exactly(self):
        """The exact agreement case. Not almost equal, equal."""
        for d in (0.2, 0.35, 0.9):
            for m in (1, 7, 40):
                for k in (3, 11, 30):
                    self.assertEqual(
                        P.power_crt(d, m, 0.0, k, df_rule="normal"),
                        P.power_two_sample(d, k * m, method="normal"),
                    )
                    self.assertEqual(
                        P.power_crt(d, m, 0.0, k, df_rule="individual_t"),
                        P.power_two_sample(d, k * m, method="t"),
                    )

    def test_m1_icc0_reduces_to_the_individual_t_test(self):
        """At m = 1 the cluster t rule has df = 2k - 2, which is the individual df."""
        for d in (0.2, 0.5, 0.8):
            k = P.clusters_crt(d, 1, 0.0, power=0.8).clusters_per_arm
            self.assertEqual(k, math.ceil(P.n_two_sample(d, 0.8)))

    def test_clusters_are_minimal(self):
        """k must reach the target and k - 1 must not. Checked over a grid."""
        for d in (0.2, 0.4):
            for m in (5, 25, 60):
                for icc in (0.0, 0.02, 0.15):
                    for cv in (0.0, 0.7):
                        res = P.clusters_crt(d, m, icc, cv, power=0.8)
                        k = res.clusters_per_arm
                        self.assertGreaterEqual(res.achieved_power, 0.8)
                        if k > 2:
                            below = P.power_crt(d, m, icc, k - 1, cv)
                            self.assertLess(
                                below, 0.8,
                                f"k={k} not minimal at d={d} m={m} icc={icc} cv={cv}",
                            )

    def test_t_correction_never_reduces_the_requirement(self):
        for d in (0.2, 0.35):
            for m in (10, 50):
                for icc in (0.01, 0.05, 0.2):
                    with_t = P.clusters_crt(d, m, icc, power=0.8, df_rule="cluster_t")
                    normal = P.clusters_crt(d, m, icc, power=0.8, df_rule="normal")
                    self.assertGreaterEqual(with_t.clusters_per_arm, normal.clusters_per_arm)

    def test_t_correction_matters_most_with_few_clusters(self):
        """The gap between the normal and t answers shrinks as clusters accumulate."""
        few = P.power_crt(0.8, 20, 0.05, 4, df_rule="normal") - P.power_crt(0.8, 20, 0.05, 4)
        many = P.power_crt(0.15, 20, 0.05, 80, df_rule="normal") - P.power_crt(0.15, 20, 0.05, 80)
        self.assertGreater(few, many)
        self.assertGreater(few, 0.01)

    def test_cv_increases_the_requirement(self):
        equal = P.clusters_crt(0.3, 30, 0.05, 0.0, power=0.8).clusters_per_arm
        unequal = P.clusters_crt(0.3, 30, 0.05, 0.8, power=0.8).clusters_per_arm
        self.assertGreater(unequal, equal)

    def test_hayes_moulton_cross_derivation(self):
        """A second published route to the same number, with no design effect in it.

        Hayes and Moulton size from the variance components directly:
            k = (z + z)^2 * 2 * (sigma_w^2 / m + sigma_b^2) / delta^2
        Writing sigma^2 = 1 so that sigma_b^2 = icc and sigma_w^2 = 1 - icc, this must
        equal the design effect route exactly. Their leading +1 is a deliberately
        crude stand-in for the t correction and is excluded from the comparison.
        """
        z = dist.norm_ppf(0.975) + dist.norm_ppf(0.80)
        for d in (0.2, 0.35, 0.6):
            for m in (5, 25, 100):
                for icc in (0.0, 0.01, 0.05, 0.3):
                    sigma_b2, sigma_w2 = icc, 1.0 - icc
                    hm = z * z * 2.0 * (sigma_w2 / m + sigma_b2) / (d * d)
                    deff_route = P.n_two_sample(d, 0.8, method="normal") * P.design_effect(m, icc) / m
                    self.assertAlmostEqual(
                        hm, deff_route, delta=1e-9 * deff_route,
                        msg=f"routes disagree at d={d} m={m} icc={icc}",
                    )

    def test_negative_control_wrong_df_rule(self):
        right = P.clusters_crt(0.25, 25, 0.05, power=0.8, df_rule="cluster_t").clusters_per_arm
        wrong = P.clusters_crt(0.25, 25, 0.05, power=0.8, df_rule="individual_t").clusters_per_arm
        self.assertNotEqual(right, wrong)

    def test_negative_control_ignoring_clustering(self):
        clustered = P.clusters_crt(0.2, 30, 0.05, power=0.8)
        self.assertGreater(
            clustered.individuals_total, 2.4 * clustered.n_individually_randomised_total
        )

    def test_result_reports_both_clusters_and_individuals(self):
        r = P.clusters_crt(0.2, 30, 0.05, power=0.8)
        self.assertEqual(r.clusters_total, 2 * r.clusters_per_arm)
        self.assertEqual(r.individuals_per_arm, r.clusters_per_arm * 30)
        self.assertEqual(r.individuals_total, 2 * r.individuals_per_arm)
        self.assertEqual(r.design_effect, 2.45)
        self.assertGreaterEqual(r.achieved_power, 0.8)
        self.assertIn("k/ICC", " ".join(r.notes))

    def test_infeasible_design_raises_rather_than_returning_nonsense(self):
        with self.assertRaises(ValueError):
            P.clusters_crt(0.01, 5, 0.5, power=0.99, max_clusters_per_arm=50)

    def test_rejects_bad_input(self):
        with self.assertRaises(ValueError):
            P.power_crt(0.3, 20, 0.05, 0)
        with self.assertRaises(ValueError):
            P.power_crt(0.3, 20, 0.05, 10, df_rule="wishful")
        with self.assertRaises(ValueError):
            P.clusters_crt(0.3, 0.5, 0.05)


class TestCurves(unittest.TestCase):
    def test_power_curve_is_monotone(self):
        curve = P.power_curve_clusters(0.3, 20, 0.05, k_min=2, k_max=40)
        self.assertEqual(len(curve), 39)
        powers = [p["power"] for p in curve]
        self.assertEqual(powers, sorted(powers))
        self.assertEqual(curve[0]["k_per_arm"], 2)
        self.assertEqual(curve[-1]["individuals_total"], 2 * 40 * 20)

    def test_operating_characteristic_starts_at_alpha(self):
        oc = P.operating_characteristic(20, 25, 0.05, alpha=0.05, points=51)
        self.assertEqual(oc[0]["effect"], 0.0)
        self.assertAlmostEqual(oc[0]["power"], 0.05, delta=1e-12)
        self.assertAlmostEqual(oc[0]["accept_null"], 0.95, delta=1e-12)
        self.assertEqual([p["power"] for p in oc], sorted(p["power"] for p in oc))
        self.assertTrue(all(abs(p["power"] + p["accept_null"] - 1.0) < 1e-15 for p in oc))

    def test_optimism_costs_power(self):
        """The README's central caveat, as a test.

        A design powered at 0.80 for d = 0.3 delivers far less if the true effect is
        0.2. The number quoted in the README comes from here.
        """
        design = P.clusters_crt(0.3, 25, 0.05, power=0.8)
        truth = P.power_crt(0.2, 25, 0.05, design.clusters_per_arm)
        self.assertLess(truth, 0.50)
        self.assertGreater(truth, 0.35)


if __name__ == "__main__":
    unittest.main(verbosity=2)
