"""Partially overlapping samples t-test for the NBA analysis.

Implements the unequal-variance T_new2 equations described in:
Derrick, B., White, P., & Toher, D. (2019).
Parametric and Non-Parametric Tests for the Comparison of Two Samples
Which Both Include Paired and Unpaired Observations.
https://doi.org/10.22237/jmasm/1556669520

This implementation tests new > old and reports a two-sided 95%
confidence interval and a one-sided 95% lower confidence bound.
"""
import numpy as np
from scipy import stats

def partially_overlapping_t(new_only, old_only, paired_new, paired_old):
    """Calculate the unequal-variance T_new2 test for new > old.

    Args:
        new_only: One-dimensional values for new-only players.
        old_only: One-dimensional values for old-only players.
        paired_new: New-period values for matched players.
        paired_old: Old-period values for the same matched players,
            in exactly the same order as paired_new.

    Returns:
        A dictionary containing sample sizes, paired correlation,
        mean difference (new minus old), standard error, t statistic,
        degrees of freedom, upper-tail p-value, two-sided 95%
        confidence interval, and one-sided 95% lower confidence bound.

    Raises:
        ValueError: If inputs are not finite one-dimensional arrays,
            paired lengths differ, fewer than two pairs are supplied,
            paired correlation is undefined, or the estimated sampling
            variance is not positive.

    Notes:
        Each player must contribute at most one value per group.
        Pair alignment must be checked by the caller using player IDs;
        this function receives values and cannot verify identities.
        This implementation does not support fewer than two pairs.
        A numerical result does not establish the statistical assumptions
        required for inference.
    """
    arrays = [
        np.asarray(values, dtype=float)
        for values in [new_only, old_only, paired_new, paired_old]
    ]

    if any(values.ndim != 1 for values in arrays):
        raise ValueError("Inputs must be one-dimensional.")

    if any(not np.isfinite(values).all() for values in arrays):
        raise ValueError("Inputs must contain only finite values.")

    new_only, old_only, paired_new, paired_old = arrays

    if len(paired_new) != len(paired_old):
        raise ValueError("Paired inputs must have equal lengths.")

    n_a = len(new_only)
    n_b = len(old_only)
    n_c = len(paired_new)

    if n_c < 2:
        raise ValueError("This implementation requires at least two pairs.")

    if (
        paired_new.std(ddof=1) == 0
        or paired_old.std(ddof=1) == 0
    ):
        raise ValueError("Paired correlation is undefined for constant inputs.")

    # Reconstruct each complete group.
    new_values = np.concatenate([new_only, paired_new])
    old_values = np.concatenate([old_only, paired_old])

    n_1 = len(new_values)
    n_2 = len(old_values)

    mean_difference = new_values.mean() - old_values.mean()

    s_1 = new_values.std(ddof=1)
    s_2 = old_values.std(ddof=1)

    r = stats.pearsonr(paired_new, paired_old).statistic

    # Estimated variance of the mean difference.
    v_1 = s_1**2 / n_1
    v_2 = s_2**2 / n_2
    covariance_adjustment = (
        2 * r * s_1 * s_2 * n_c / (n_1 * n_2)
    )

    se_squared = v_1 + v_2 - covariance_adjustment

    if not np.isfinite(se_squared) or se_squared <= 0:
        raise ValueError("Estimated sampling variance must be positive.")

    standard_error = np.sqrt(se_squared)
    t_statistic = mean_difference / standard_error

    # Degrees of freedom specified for T_new2.
    gamma = (v_1 + v_2)**2 / (
        v_1**2 / (n_1 - 1)
        + v_2**2 / (n_2 - 1)
    )

    degrees_of_freedom = (
        (n_c - 1)
        + (gamma - n_c + 1)
        * (n_a + n_b)
        / (n_a + n_b + 2 * n_c)
    )

    p_value = stats.t.sf(t_statistic, df=degrees_of_freedom)

    critical_two_sided = stats.t.ppf(
        0.975, df=degrees_of_freedom
    )
    critical_one_sided = stats.t.ppf(
        0.95, df=degrees_of_freedom
    )

    return {
        "n_new": n_1,
        "n_old": n_2,
        "n_pairs": n_c,
        "paired_r": r,
        "mean_difference": mean_difference,
        "standard_error": standard_error,
        "t_statistic": t_statistic,
        "df": degrees_of_freedom,
        "p_value_one_sided": p_value,
        "ci95_lower": (
            mean_difference - critical_two_sided * standard_error
        ),
        "ci95_upper": (
            mean_difference + critical_two_sided * standard_error
        ),
        "lower95_one_sided": (
            mean_difference - critical_one_sided * standard_error
        ),
    }