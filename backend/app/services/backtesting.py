import numpy as np
import pandas as pd
from .metrics import (auc_gini, binomial_upper_tail, bootstrap_gini_ci, brier_score,
                      hosmer_lemeshow_by_grade, ks_statistic, monotonicity, normalize_pd, psi,
                      traffic_light, wilson_interval)
from ..config import MIN_DEFAULTS_FOR_DECISION


def run_backtest(data: pd.DataFrame, rating_column: str, pd_column: str, default_column: str, correlation: float, include_uncertainty=True, pd_unit="auto") -> dict:
    required = [rating_column, pd_column, default_column]
    missing = [c for c in required if c not in data]
    if missing: raise ValueError(f"Colonnes absentes : {missing}")
    frame = data.loc[data[default_column].notna() & data[pd_column].notna() & data[rating_column].notna()].copy()
    frame[default_column] = frame[default_column].astype(int)
    frame["pd_decimal"], pd_scale = normalize_pd(frame[pd_column], pd_unit)
    frame = frame.dropna(subset=["pd_decimal"])
    defaults = int(frame[default_column].sum())
    auc, gini = auc_gini(frame[default_column], frame["pd_decimal"])
    grades = []
    for grade, group in frame.groupby(rating_column, dropna=False):
        n, d = len(group), int(group[default_column].sum())
        expected = float(group["pd_decimal"].mean())
        observed = d / n
        grades.append({"grade": str(grade), "exposures": n, "defaults": d, "pd_predicted": expected,
                       "default_rate_observed": observed, "gap": observed-expected,
                       "confidence_interval": wilson_interval(d, n),
                       "binomial_upper_tail": binomial_upper_tail(d, n, expected),
                       "traffic_light": traffic_light(observed, expected, correlation)})
    warnings = []
    if defaults < MIN_DEFAULTS_FOR_DECISION: warnings.append("Nombre de défauts insuffisant pour un recalibrage fréquentiste robuste.")
    if auc is None: warnings.append("Discrimination non calculable : une seule classe de défaut observée.")
    result = {
        "population": len(frame), "defaults": defaults, "default_rate": defaults / len(frame) if len(frame) else None,
        "mean_pd": float(frame.pd_decimal.mean()) if len(frame) else None, "pd_scale": pd_scale,
        "auc": auc, "gini": gini, "gini_confidence_interval": bootstrap_gini_ci(frame[default_column], frame.pd_decimal) if include_uncertainty else None,
        "ks": ks_statistic(frame[default_column], frame.pd_decimal), "brier_score": brier_score(frame[default_column], frame.pd_decimal),
        "grades": grades, "warnings": warnings,
    }
    result["hosmer_lemeshow"] = hosmer_lemeshow_by_grade(frame, rating_column, "pd_decimal", default_column)
    result["pd_monotonicity"] = monotonicity(pd.DataFrame(grades))
    return result

def analyze_overrides(data: pd.DataFrame, correlation: float) -> dict:
    """Compare modèle statistique pur et système de décision final, comme exigé par le référentiel."""
    available = {"Override", "Fundamental Rating Class", "Fundamental Pd Class", "Final Rating Class", "Final Pd Class", "defaut_observe"}
    if not available.issubset(data.columns):
        return {"available": False, "reason": "Colonnes Fundamental/Final/Override incomplètes."}
    has_override = data["Override"].notna()
    base = data[data["defaut_observe"].notna()]
    fundamental = base.dropna(subset=["Fundamental Rating Class", "Fundamental Pd Class"])
    result = {
        "available": True, "population": len(base), "override_count": int(has_override.sum()),
        "override_rate": float(has_override.mean()),
        "direction": data.loc[has_override, "Override"].value_counts().to_dict(),
    }
    if not fundamental.empty:
        result["fundamental_backtest"] = run_backtest(fundamental, "Fundamental Rating Class", "Fundamental Pd Class", "defaut_observe", correlation)
    return result

def analyze_stability(reference: pd.DataFrame | None, current: pd.DataFrame, rating_column: str, id_column="Counterparty", psi_warning=.10, psi_critical=.25) -> dict:
    if reference is None or reference.empty:
        return {"available": False, "reason": "Jeu de référence requis pour PSI et migrations."}
    psi_value = psi(reference[rating_column], current[rating_column])
    migration = reference[[id_column, rating_column]].merge(current[[id_column, rating_column]], on=id_column, suffixes=("_reference", "_current"))
    matrix = pd.crosstab(migration[f"{rating_column}_reference"], migration[f"{rating_column}_current"])
    return {"available": True, "psi": psi_value,
            "psi_status": "green" if psi_value < psi_warning else "orange" if psi_value <= psi_critical else "red",
            "migration_matrix": {str(k): {str(x): int(v) for x, v in row.items()} for k,row in matrix.to_dict(orient="index").items()}}


def decision(result: dict, thresholds: dict | None = None, psi_value: float | None = None, override_rate: float | None = None) -> dict:
    thresholds = thresholds or {}
    min_defaults = int(thresholds.get("minimum_defaults_for_decision", MIN_DEFAULTS_FOR_DECISION))
    gini_minimum = float(thresholds.get("gini_minimum", 0.40))
    ks_minimum = float(thresholds.get("ks_minimum", 0.20))
    psi_critical = float(thresholds.get("psi_critical", 0.25))
    override_rate_critical = float(thresholds.get("override_rate_critical", 0.20))

    if result["defaults"] < min_defaults:
        return {"status": "inconclusive", "action": "extend_history", "reason": "Nombre de défauts insuffisant : agréger des périodes supplémentaires avant toute décision de recalibrage."}
    reds = sum(x["traffic_light"] == "red" for x in result["grades"])
    oranges = sum(x["traffic_light"] == "orange" for x in result["grades"])
    gini = result.get("gini")
    if gini is not None and gini < gini_minimum:
        return {"status": "review", "action": "model_redevelopment", "reason": f"Pouvoir discriminant insuffisant (Gini < {gini_minimum:.2f})."}
    if result.get("ks") is not None and result["ks"] < ks_minimum:
        return {"status": "review", "action": "model_redevelopment", "reason": f"Pouvoir discriminant insuffisant (KS < {ks_minimum:.2f})."}
    if reds or oranges:
        return {"status": "review", "action": "pd_recalibration", "reason": f"{reds} classe(s) rouge(s), {oranges} orange(s) sur la calibration."}
    if psi_value is not None and psi_value > psi_critical:
        return {"status": "monitor", "action": "scope_review", "reason": "PSI > 0,25 : dérive significative de population."}
    if override_rate is not None and override_rate > override_rate_critical:
        return {"status": "monitor", "action": "override_review", "reason": "Fréquence d'override élevée : analyser le jugement expert."}
    return {"status": "pass", "action": "no_action", "reason": "Aucune alerte matérielle selon les règles configurées."}
