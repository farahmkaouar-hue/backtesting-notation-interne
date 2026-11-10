import math
from statistics import NormalDist
import numpy as np
import pandas as pd
from ..config import BOOTSTRAP_ITERATIONS

NORM = NormalDist()

def auc_gini(y, risk):
    y, risk = np.asarray(y, dtype=int), np.asarray(risk, dtype=float)
    pos, neg = y.sum(), len(y) - y.sum()
    if pos == 0 or neg == 0:
        return None, None
    order = np.argsort(risk, kind="mergesort")
    ranks = np.empty(len(risk), float); ranks[order] = np.arange(1, len(risk) + 1)
    for value in np.unique(risk):
        mask = risk == value
        ranks[mask] = ranks[mask].mean()
    auc = (ranks[y == 1].sum() - pos * (pos + 1) / 2) / (pos * neg)
    return float(auc), float(2 * auc - 1)

def bootstrap_gini_ci(y, risk, iterations=BOOTSTRAP_ITERATIONS, seed=17):
    """IC non paramétrique : retenu car aucune normalité des scores n'est supposée."""
    y, risk = np.asarray(y, dtype=int), np.asarray(risk, dtype=float)
    if y.sum() == 0 or y.sum() == len(y): return None
    rng = np.random.default_rng(seed); values = []
    for _ in range(iterations):
        sample = rng.integers(0, len(y), len(y))
        _, gini = auc_gini(y[sample], risk[sample])
        if gini is not None: values.append(gini)
    return {"lower_95": float(np.quantile(values, .025)), "upper_95": float(np.quantile(values, .975)), "iterations": len(values)} if values else None

def ks_statistic(y, risk):
    y, risk = np.asarray(y, dtype=int), np.asarray(risk, dtype=float)
    if y.sum() == 0 or y.sum() == len(y): return None
    frame = pd.DataFrame({"y": y, "risk": risk}).sort_values("risk")
    return float(np.max(np.abs(frame.y.cumsum() / y.sum() - (1-frame.y).cumsum() / (len(y)-y.sum()))))

def vasicek_quantile(pd_value: float, correlation: float, confidence: float) -> float:
    p = min(max(float(pd_value), 1e-8), 1 - 1e-8)
    return float(NORM.cdf((NORM.inv_cdf(p) + math.sqrt(correlation) * NORM.inv_cdf(confidence)) / math.sqrt(1 - correlation)))

def traffic_light(observed: float, predicted: float, correlation: float) -> str:
    # BCE-style proxy: green <= 95% Vasicek quantile, orange <= 99.9%, red above.
    if observed <= vasicek_quantile(predicted, correlation, .95): return "green"
    if observed <= vasicek_quantile(predicted, correlation, .999): return "orange"
    return "red"

def wilson_interval(defaults: int, exposures: int, confidence=.95):
    if exposures == 0: return None
    z = NORM.inv_cdf(1 - (1-confidence)/2); p = defaults/exposures
    denominator = 1 + z*z/exposures
    centre = (p + z*z/(2*exposures))/denominator
    half = z*math.sqrt((p*(1-p) + z*z/(4*exposures))/exposures)/denominator
    return {"lower": max(0., centre-half), "upper": min(1., centre+half), "confidence": confidence}

def binomial_upper_tail(defaults: int, exposures: int, probability: float):
    """Alerte exacte par classe. Décision : traffic-light corrélé, pas ce test indépendant."""
    if exposures == 0: return None
    p = min(max(probability, 1e-12), 1-1e-12)
    if exposures > 5000:
        # Continuity-corrected normal approximation prevents a costly O(n) exact tail on large portfolios.
        z = (defaults - .5 - exposures*p) / math.sqrt(exposures*p*(1-p))
        return float(1 - NORM.cdf(z))
    logs = [math.lgamma(exposures+1)-math.lgamma(k+1)-math.lgamma(exposures-k+1)+k*math.log(p)+(exposures-k)*math.log1p(-p) for k in range(defaults, exposures+1)]
    maximum = max(logs)
    return float(min(1., math.exp(maximum)*sum(math.exp(v-maximum) for v in logs)))

def brier_score(y, probabilities):
    y, probabilities = np.asarray(y, float), np.asarray(probabilities, float)
    return float(np.mean((y-probabilities)**2)) if len(y) else None

def normalize_pd(values, unit: str = "auto") -> tuple[pd.Series, str]:
    """Normalise des PD en décimales sans supposer silencieusement une unité unique."""
    numeric = pd.to_numeric(pd.Series(values), errors="coerce")
    observed = numeric.dropna()
    if observed.empty:
        return numeric, "unknown"
    if (observed < 0).any() or (observed > 100).any():
        raise ValueError("Les PD doivent être comprises entre 0 et 1 (décimal) ou 0 et 100 (pourcentage).")
    if unit not in {"auto", "decimal", "percent"}:
        raise ValueError("Unité de PD invalide : utiliser auto, decimal ou percent.")
    if unit == "decimal":
        if (observed > 1).any():
            raise ValueError("PD déclarées décimales mais une valeur est supérieure à 1.")
        return numeric, "decimal"
    if unit == "percent":
        return numeric / 100, "percent"
    # Auto-détection : une valeur > 1 impose une lecture en pourcentage ; les
    # valeurs 0-1 sont alors elles-mêmes des pourcentages valides (ex. 0,5 %).
    # Si toutes les valeurs sont <= 1, le résultat porte une étiquette explicite.
    return (numeric / 100, "percent") if (observed > 1).any() else (numeric, "decimal_auto")

def monotonicity(mapping: pd.DataFrame, grade_column="grade", pd_column="pd_predicted"):
    ordered = mapping.copy()
    ordered["_grade"] = pd.to_numeric(ordered[grade_column].astype(str).str.extract(r"(\d+)")[0], errors="coerce")
    ordered = ordered.sort_values(["_grade", grade_column])
    values = ordered[pd_column].to_numpy(float)
    violations = int(np.sum(np.diff(values) < -1e-12))
    return {"is_monotonic": violations == 0, "violations": violations,
            "note": "La PD doit être non décroissante lorsque le grade numérique se dégrade ; les grades +/- doivent être validés dans le référentiel de mapping."}

def psi(reference, current, bins=None):
    reference, current = pd.Series(reference).dropna(), pd.Series(current).dropna()
    if reference.empty or current.empty: return None
    categories = bins or sorted(set(reference) | set(current))
    ref = reference.value_counts(normalize=True).reindex(categories, fill_value=1e-6)
    cur = current.value_counts(normalize=True).reindex(categories, fill_value=1e-6)
    return float(((cur-ref) * np.log(cur/ref)).sum())

def hosmer_lemeshow_by_grade(data: pd.DataFrame, grade_column: str, pd_column: str, default_column: str):
    """Statistique globale complémentaire ; le traffic-light reste la décision par classe."""
    statistic = 0.0
    groups = 0
    for _, group in data.groupby(grade_column):
        n = len(group); observed = group[default_column].sum(); expected = group[pd_column].sum()
        # Variance exacte de la somme de Bernoulli avec PD hétérogènes dans un grade.
        variance = float((group[pd_column] * (1 - group[pd_column])).sum())
        if n and variance > 0:
            statistic += (observed - expected) ** 2 / variance
            groups += 1
    return {"statistic": float(statistic), "groups": groups,
            "note": "Statistique Hosmer-Lemeshow par classes ; interprétation avec effectifs et traffic-light."}
