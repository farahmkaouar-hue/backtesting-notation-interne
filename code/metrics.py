"""Indicateurs statistiques du backtesting.

Toutes les mesures de discrimination sont calculées à partir des effectifs par
valeur de score distincte : elles traitent correctement les ex æquo (les PD
sont attribuées par classe) et restent rapides sur des millions de lignes.
"""
from __future__ import annotations

import math
from statistics import NormalDist

import numpy as np
import pandas as pd

NORM = NormalDist()
_SQRT2 = math.sqrt(2.0)

# Quadrature de Gauss-Hermite pour intégrer sur le facteur systémique Z ~ N(0,1).
_NODES, _WEIGHTS = np.polynomial.hermite_e.hermegauss(80)
_WEIGHTS = _WEIGHTS / _WEIGHTS.sum()
_EXACT_TAIL_LIMIT = 5000


def _norm_cdf(x: np.ndarray) -> np.ndarray:
    return 0.5 * np.vectorize(math.erfc)(-np.asarray(x, float) / _SQRT2)


# ------------------------------------------------------------------------------
# Discrimination
# ------------------------------------------------------------------------------

def _counts_by_score(y, risk) -> tuple[np.ndarray, np.ndarray]:
    """Défauts et non-défauts par valeur de score, scores croissants."""
    y = np.asarray(y, dtype=float)
    risk = np.asarray(risk, dtype=float)
    _, inverse = np.unique(risk, return_inverse=True)
    bad = np.bincount(inverse, weights=y)
    total = np.bincount(inverse).astype(float)
    return bad, total - bad


def _auc_from_counts(bad: np.ndarray, good: np.ndarray) -> float | None:
    """AUC = P(score défaut > score sain) + ½ P(égalité)."""
    n_bad, n_good = bad.sum(), good.sum()
    if n_bad == 0 or n_good == 0:
        return None
    good_below = np.cumsum(good) - good
    return float((bad * (good_below + 0.5 * good)).sum() / (n_bad * n_good))


def auc_gini(y, risk) -> tuple[float | None, float | None]:
    auc = _auc_from_counts(*_counts_by_score(y, risk))
    return (None, None) if auc is None else (auc, 2 * auc - 1)


def ks_statistic(y, risk) -> float | None:
    """Écart maximal entre répartitions cumulées, évalué seulement entre deux valeurs de score distinctes."""
    bad, good = _counts_by_score(y, risk)
    if bad.sum() == 0 or good.sum() == 0:
        return None
    return float(np.max(np.abs(np.cumsum(bad) / bad.sum() - np.cumsum(good) / good.sum())))


def bootstrap_gini_ci(y, risk, iterations: int = 300, seed: int = 17) -> dict | None:
    """IC 95 % du Gini par bootstrap non paramétrique.

    Un rééchantillonnage des lignes équivaut à un tirage multinomial des
    effectifs (score, défaut) : on tire directement les effectifs.
    """
    bad, good = _counts_by_score(y, risk)
    n = int(bad.sum() + good.sum())
    if bad.sum() == 0 or good.sum() == 0:
        return None
    k = len(bad)
    rng = np.random.default_rng(seed)
    draws = rng.multinomial(n, np.concatenate([bad, good]) / n, size=int(iterations))
    values = [2 * a - 1 for a in (_auc_from_counts(d[:k].astype(float), d[k:].astype(float)) for d in draws) if a is not None]
    if not values:
        return None
    return {"lower_95": float(np.quantile(values, 0.025)), "upper_95": float(np.quantile(values, 0.975)),
            "iterations": len(values)}


# ------------------------------------------------------------------------------
# Calibration : test binomial corrélé (Vasicek) — « traffic-light »
# ------------------------------------------------------------------------------

def conditional_pd(pd_value: float, correlation: float, z: np.ndarray) -> np.ndarray:
    """PD conditionnelle au facteur systémique Z (modèle à un facteur de Vasicek / Bâle)."""
    p = min(max(float(pd_value), 1e-10), 1 - 1e-10)
    if correlation <= 0:
        return np.full_like(np.asarray(z, float), p)
    return _norm_cdf((NORM.inv_cdf(p) + math.sqrt(correlation) * np.asarray(z, float)) / math.sqrt(1 - correlation))


def _binomial_tail(d: int, n: int, p: np.ndarray) -> np.ndarray:
    """P(X >= d) pour X ~ Binomiale(n, p), p vectoriel."""
    p = np.clip(np.asarray(p, float), 1e-15, 1 - 1e-15)
    if d <= 0:
        return np.ones_like(p)
    if d > n:
        return np.zeros_like(p)
    if d > _EXACT_TAIL_LIMIT:
        # Grands effectifs : approximation normale avec correction de continuité.
        z = (d - 0.5 - n * p) / np.sqrt(n * p * (1 - p))
        return 1 - _norm_cdf(z)
    k = np.arange(d)
    log_comb = np.concatenate([[0.0], np.cumsum(np.log(n - k[1:] + 1) - np.log(k[1:]))])
    log_pmf = log_comb[None, :] + np.outer(np.log(p), k) + np.outer(np.log1p(-p), n - k)
    return np.clip(1 - np.exp(log_pmf).sum(axis=1), 0.0, 1.0)


def defaults_tail_probability(defaults: int, exposures: int, pd_value: float, correlation: float) -> float:
    """P(D >= défauts observés) si la PD est juste, défauts corrélés (ρ).

    D | Z ~ Binomiale(n, p(Z)) et Z ~ N(0,1) : la probabilité est intégrée sur Z.
    Une valeur faible signifie que tant de défauts sont improbables : PD sous-estimée.
    """
    tails = _binomial_tail(int(defaults), int(exposures), conditional_pd(pd_value, correlation, _NODES))
    return float(np.clip((tails * _WEIGHTS).sum(), 0.0, 1.0))


def critical_defaults(exposures: int, pd_value: float, correlation: float, level: float) -> int:
    """Plus petit nombre de défauts d tel que P(D >= d) <= level."""
    low, high = 0, int(exposures) + 1
    while low < high:
        mid = (low + high) // 2
        if mid <= exposures and defaults_tail_probability(mid, exposures, pd_value, correlation) > level:
            low = mid + 1
        else:
            high = mid
    return low


def traffic_light(defaults: int, exposures: int, pd_value: float, correlation: float, rules: dict) -> dict:
    """Feu de calibration d'une classe : deux tests, trois couleurs, règles explicites.

    Test 1 — binomial exact (défauts indépendants) :
        p1 = P(D >= défauts observés | PD). Mesure si l'écart est statistiquement significatif.
    Test 2 — binomial corrélé (Vasicek, corrélation ρ de la politique) :
        p2 = même probabilité, en admettant qu'une année défavorable augmente tous les défauts.
        p2 >= p1 : ce test est plus tolérant.

    - NON CONCLUANT : moins d'expositions que le minimum de la politique ;
    - ROUGE  : p2 <= seuil rouge (1 %) — trop de défauts, même pour une année défavorable ;
    - ORANGE : p1 <= seuil orange (5 %) — écart significatif, que la conjoncture peut encore expliquer ;
    - VERT   : p1 > 5 % — aucun écart significatif.
    Les bornes sont aussi données en nombre de défauts, pour une lecture directe.
    """
    orange_level = float(rules["traffic_light_orange_pvalue"])
    red_level = float(rules["traffic_light_red_pvalue"])
    minimum = int(rules["minimum_exposures_per_grade"])
    result = {
        "p_value": None, "p_value_correlated": None, "orange_from_defaults": None, "red_from_defaults": None,
        "overestimated": False, "expected_defaults": exposures * pd_value,
    }
    if exposures < minimum:
        return {**result, "light": "nc",
                "rule": f"Moins de {minimum} clients dans la note : pas de conclusion statistique possible."}
    p_independent = defaults_tail_probability(defaults, exposures, pd_value, 0.0)
    p_correlated = defaults_tail_probability(defaults, exposures, pd_value, correlation)
    orange_from = critical_defaults(exposures, pd_value, 0.0, orange_level)
    red_from = max(orange_from, critical_defaults(exposures, pd_value, correlation, red_level))
    # PD manifestement trop prudente : trop peu de défauts (information, pas une alerte).
    lower_p = 1 - defaults_tail_probability(defaults + 1, exposures, pd_value, 0.0)
    if p_correlated <= red_level:
        light = "red"
    elif p_independent <= orange_level:
        light = "orange"
    else:
        light = "green"
    return {
        **result, "light": light, "p_value": p_independent, "p_value_correlated": p_correlated,
        "orange_from_defaults": orange_from, "red_from_defaults": red_from,
        "overestimated": bool(lower_p <= orange_level),
        "rule": f"Vert jusqu'à {orange_from - 1} défaut(s), orange à partir de {orange_from}, rouge à partir de {red_from}.",
    }


def wilson_interval(defaults: int, exposures: int, confidence: float = 0.95) -> dict | None:
    if exposures == 0:
        return None
    z = NORM.inv_cdf(1 - (1 - confidence) / 2)
    p = defaults / exposures
    denominator = 1 + z * z / exposures
    centre = (p + z * z / (2 * exposures)) / denominator
    half = z * math.sqrt((p * (1 - p) + z * z / (4 * exposures)) / exposures) / denominator
    return {"lower": max(0.0, centre - half), "upper": min(1.0, centre + half), "confidence": confidence}


def brier_score(y, probabilities) -> float | None:
    y, probabilities = np.asarray(y, float), np.asarray(probabilities, float)
    return float(np.mean((y - probabilities) ** 2)) if len(y) else None


# ------------------------------------------------------------------------------
# Tests globaux et stabilité
# ------------------------------------------------------------------------------

def _gamma_q(a: float, x: float) -> float:
    """Fonction gamma incomplète régularisée supérieure Q(a, x)."""
    if x <= 0:
        return 1.0
    log_prefix = -x + a * math.log(x) - math.lgamma(a)
    if x < a + 1:
        term = total = 1.0 / a
        ap = a
        for _ in range(1000):
            ap += 1
            term *= x / ap
            total += term
            if abs(term) < abs(total) * 1e-15:
                break
        return max(0.0, 1.0 - total * math.exp(log_prefix))
    tiny = 1e-300
    b = x + 1 - a
    c, d = 1 / tiny, 1 / b
    h = d
    for i in range(1, 1000):
        an = -i * (i - a)
        b += 2
        d = an * d + b
        d = d if abs(d) > tiny else tiny
        c = b + an / c
        c = c if abs(c) > tiny else tiny
        d = 1 / d
        delta = d * c
        h *= delta
        if abs(delta - 1) < 1e-15:
            break
    return min(1.0, math.exp(log_prefix) * h)


def chi2_sf(statistic: float, dof: int) -> float:
    return _gamma_q(dof / 2, statistic / 2) if dof > 0 else float("nan")


def hosmer_lemeshow_by_grade(data: pd.DataFrame, grade_column: str, pd_column: str, default_column: str) -> dict:
    """Test global de calibration par classe (PD non estimées sur cet échantillon : ddl = nombre de classes)."""
    grouped = data.groupby(grade_column, observed=True).agg(
        observed=(default_column, "sum"), expected=(pd_column, "sum"),
        variance=(pd_column, lambda p: float(np.sum(p * (1 - p)))),
    )
    grouped = grouped[grouped["variance"] > 0]
    statistic = float(((grouped["observed"] - grouped["expected"]) ** 2 / grouped["variance"]).sum())
    groups = int(len(grouped))
    return {"statistic": statistic, "groups": groups, "dof": groups,
            "p_value": chi2_sf(statistic, groups) if groups else None}


def monotonicity(grades: list[dict]) -> dict:
    """La PD doit croître (au sens large) quand la note se dégrade."""
    ordered = sorted(grades, key=lambda g: g["rank"])
    values = [g["pd_predicted"] for g in ordered]
    violations = [
        f"{ordered[i]['grade']} → {ordered[i + 1]['grade']}"
        for i in range(len(values) - 1) if values[i + 1] < values[i] - 1e-12
    ]
    return {"is_monotonic": not violations, "violations": len(violations), "pairs": violations}


def psi(reference, current) -> float | None:
    reference = pd.Series(reference).dropna().astype(str)
    current = pd.Series(current).dropna().astype(str)
    if reference.empty or current.empty:
        return None
    categories = sorted(set(reference) | set(current))
    ref = reference.value_counts(normalize=True).reindex(categories, fill_value=0.0).clip(lower=1e-6)
    cur = current.value_counts(normalize=True).reindex(categories, fill_value=0.0).clip(lower=1e-6)
    return float(((cur - ref) * np.log(cur / ref)).sum())
