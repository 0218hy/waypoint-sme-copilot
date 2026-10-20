"""Small numeric helpers for the Monte Carlo (no scipy): normal CDF and inverse, triangular draws, copula."""

from __future__ import annotations

import math

import numpy as np
from numpy.typing import NDArray

from tools.params import Tri

F64 = NDArray[np.float64]

# Abramowitz & Stegun 7.1.26 (|error| < 1.5e-7)
_A = (0.254829592, -0.284496736, 1.421413741, -1.453152027, 1.061405429)
_P = 0.3275911


def erf(x: F64) -> F64:
    s = np.sign(x)
    a = np.abs(x)
    t = 1.0 / (1.0 + _P * a)
    poly = ((((_A[4] * t + _A[3]) * t + _A[2]) * t + _A[1]) * t + _A[0]) * t
    out: F64 = s * (1.0 - poly * np.exp(-a * a))
    return out


def norm_cdf(z: F64) -> F64:
    out: F64 = 0.5 * (1.0 + erf(z / math.sqrt(2.0)))
    return out


# Acklam's rational approximation of the inverse normal CDF (relative error < 1.2e-9)
_a = (
    -3.969683028665376e01,
    2.209460984245205e02,
    -2.759285104469687e02,
    1.383577518672690e02,
    -3.066479806614716e01,
    2.506628277459239e00,
)
_b = (
    -5.447609879822406e01,
    1.615858368580409e02,
    -1.556989798598866e02,
    6.680131188771972e01,
    -1.328068155288572e01,
)
_c = (
    -7.784894002430293e-03,
    -3.223964580411365e-01,
    -2.400758277161838e00,
    -2.549732539343734e00,
    4.374664141464968e00,
    2.938163982698783e00,
)
_d = (7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e00, 3.754408661907416e00)


def norm_ppf(p: float) -> float:
    if not 0.0 < p < 1.0:
        raise ValueError("p must be in (0, 1)")
    lo = 0.02425
    if p < lo:
        q = math.sqrt(-2 * math.log(p))
        return (((((_c[0] * q + _c[1]) * q + _c[2]) * q + _c[3]) * q + _c[4]) * q + _c[5]) / (
            (((_d[0] * q + _d[1]) * q + _d[2]) * q + _d[3]) * q + 1
        )
    if p > 1 - lo:
        return -norm_ppf(1 - p)
    q = p - 0.5
    r = q * q
    return (
        (((((_a[0] * r + _a[1]) * r + _a[2]) * r + _a[3]) * r + _a[4]) * r + _a[5])
        * q
        / (((((_b[0] * r + _b[1]) * r + _b[2]) * r + _b[3]) * r + _b[4]) * r + 1)
    )


def tri_ppf(t: Tri, u: F64) -> F64:
    """Inverse CDF of a triangular distribution."""
    a, c, b = t.low, t.likely, t.high
    if b <= a:
        return np.full_like(u, a)
    fc = (c - a) / (b - a)
    left = a + np.sqrt(u * (b - a) * (c - a))
    right = b - np.sqrt((1.0 - u) * (b - a) * (b - c))
    out: F64 = np.where(u < fc, left, right)
    return out


def copula_uniforms(rng: np.random.Generator, n: int, k: int, rho: float) -> F64:
    """n x k uniforms with equicorrelation rho between columns (Gaussian copula)."""
    common = rng.standard_normal((n, 1))
    idio = rng.standard_normal((n, k))
    z = math.sqrt(max(rho, 0.0)) * common + math.sqrt(max(1.0 - rho, 0.0)) * idio
    return norm_cdf(z)


def wilson_upper(k: int, n: int, z: float = 1.959964) -> float:
    """Upper end of the Wilson score interval for k events in n runs (95% by default)."""
    if n <= 0:
        return 1.0
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return min(1.0, centre + half)
