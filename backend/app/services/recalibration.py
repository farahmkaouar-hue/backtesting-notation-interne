import numpy as np
import pandas as pd
from .backtesting import run_backtest
from .metrics import normalize_pd


def _clip(values): return np.clip(values, 1e-6, 1-1e-6)

def _monotonic_mapping(mapping):
    """Ensure PDs do not decrease as the numeric grade deteriorates."""
    ordered = sorted(mapping, key=lambda row: (int("".join(filter(str.isdigit, str(row["grade"]))) or 0), str(row["grade"])))
    for row, value in zip(ordered, np.maximum.accumulate([row["new_pd"] for row in ordered])):
        row["new_pd"] = float(value)
    return ordered

def propose(data: pd.DataFrame, rating_column: str, pd_column: str, default_column: str, model: str, method="auto", min_logistic_defaults=20, prior_strength=20) -> dict:
    frame = data.dropna(subset=[rating_column, pd_column, default_column]).copy()
    frame["pd"], pd_scale = normalize_pd(frame[pd_column])
    frame = frame.dropna(subset=["pd"]); frame[default_column] = frame[default_column].astype(int)
    defaults = int(frame[default_column].sum())
    if method == "auto":
        method = "logistic" if model == "Professionnel" and defaults >= min_logistic_defaults else "bayesian"
    by_grade = frame.groupby(rating_column)
    if method == "central_tendency":
        factor = frame[default_column].mean() / frame.pd.mean() if frame.pd.mean() else 1
        mapping = [{"grade": str(g), "old_pd": float(x.pd.mean()), "new_pd": float(_clip(x.pd.mean()*factor))} for g,x in by_grade]
    elif method == "bayesian":
        # Beta prior centred on historical/model PD, strength intentionally explicit for governance.
        strength = prior_strength
        mapping = []
        for g, x in by_grade:
            prior = x.pd.mean(); posterior = (prior*strength + x[default_column].sum()) / (strength + len(x))
            mapping.append({"grade": str(g), "old_pd": float(prior), "new_pd": float(_clip(posterior)), "prior_strength": strength})
    elif method == "logistic":
        if defaults < min_logistic_defaults: raise ValueError(f"Régression logistique non autorisée : moins de {min_logistic_defaults} défauts observés.")
        x = np.column_stack([np.ones(len(frame)), np.log(_clip(frame.pd)/(1-_clip(frame.pd)))])
        y = frame[default_column].to_numpy(float); beta = np.zeros(2)
        for _ in range(50):
            p = 1/(1+np.exp(-x@beta)); w = np.clip(p*(1-p), 1e-7, None)
            # lstsq reste stable si la matrice est proche de la singularité.
            step = np.linalg.lstsq(x.T @ (x * w[:, None]), x.T @ (y - p), rcond=None)[0]
            if not np.isfinite(step).all():
                raise ValueError("Régression logistique instable : revoir le volume de défauts ou utiliser la méthode bayésienne.")
            beta += step
            if np.max(np.abs(step)) < 1e-8: break
        mapping = []
        for g, group in by_grade:
            old = group.pd.mean(); new = 1/(1+np.exp(-(beta[0]+beta[1]*np.log(_clip(old)/(1-_clip(old))))))
            mapping.append({"grade": str(g), "old_pd": float(old), "new_pd": float(_clip(new))})
    else: raise ValueError("Méthode inconnue")
    mapping = _monotonic_mapping(mapping)
    return {"method": method, "defaults": defaults, "grade_column": rating_column, "pd_scale_input": pd_scale, "mapping": mapping,
            "governance_note": "Proposition uniquement : validation indépendante et validation out-of-time obligatoires avant activation."}

def apply_mapping(data: pd.DataFrame, mapping: list[dict], rating_column="Final Rating Class", pd_column="Final Pd Class") -> pd.DataFrame:
    """Applique une proposition à une cohorte indépendante, sans modifier les PD sources."""
    out = data.copy()
    lookup = {str(item["grade"]): item["new_pd"] * 100 for item in mapping}
    out["pd_recalibree"] = out[rating_column].astype(str).map(lookup)
    source_pd, _ = normalize_pd(out[pd_column])
    out["pd_recalibree"] = out["pd_recalibree"].fillna(source_pd)
    return out
