"""Recalibrage des PD annuelles par note : une proposition chiffrée, jamais une activation.

Étapes, toujours dans cet ordre :
1. estimation sur l'horizon réellement observé (6, 12, 24 mois…), puis conversion en PD
   annuelle par l'hypothèse d'un taux de défaut constant : PD = 1 − (1 − PD_H)^(12/H) ;
2. couverture de toute l'échelle : une note absente de l'échantillon reçoit le même
   ajustement relatif que ses voisines (interpolation) ;
3. marge de prudence : le niveau de défaut cible est la borne haute de son intervalle
   de confiance (et non le seul taux observé) ;
4. plancher de PD ;
5. ordre respecté : la PD ne peut pas baisser quand la note se dégrade.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .metrics import wilson_interval

METHODS = {
    "central_tendency": (
        "Ajustement au taux de défaut moyen (tendance centrale)",
        "Toutes les PD sont multipliées par un même facteur pour que les défauts attendus égalent les défauts "
        "observés. L'ordre et les écarts relatifs entre notes sont conservés.",
    ),
    "bayesian": (
        "Ajustement bayésien par note",
        "Chaque PD est rapprochée du taux de défaut observé dans sa note, d'autant plus fortement que la note "
        "compte de clients. Adapté aux portefeuilles avec peu de défauts.",
    ),
    "logistic": (
        "Recalibrage logistique",
        "Une relation à deux paramètres entre la PD actuelle et le défaut observé est réestimée sur tout le "
        "portefeuille, puis appliquée à chaque note. Exige un nombre suffisant de défauts.",
    ),
}


def to_horizon(annual: np.ndarray, years: np.ndarray) -> np.ndarray:
    """PD annuelle -> probabilité de défaut sur `years` années (taux de défaut constant)."""
    return 1 - (1 - np.clip(annual, 0, 1 - 1e-12)) ** years


def to_annual(horizon_pd: np.ndarray, years: np.ndarray) -> np.ndarray:
    """Probabilité de défaut sur `years` années -> PD annuelle."""
    return 1 - (1 - np.clip(horizon_pd, 0, 1 - 1e-12)) ** (1 / np.maximum(years, 1e-6))


def choose_method(defaults: int, thresholds: dict) -> str:
    return "logistic" if defaults >= thresholds["minimum_defaults_for_logistic"] else "bayesian"


def _logit(p):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def _fit_logistic(pd_values: np.ndarray, y: np.ndarray) -> np.ndarray | None:
    """Ajustement a + b·logit(PD). Renvoie None si l'ajustement n'est pas exploitable."""
    x = np.column_stack([np.ones(len(pd_values)), _logit(pd_values)])
    beta = np.array([0.0, 1.0])
    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        for _ in range(100):
            p = 1 / (1 + np.exp(-np.clip(x @ beta, -35, 35)))
            w = np.clip(p * (1 - p), 1e-9, None)
            try:
                step = np.linalg.solve(x.T @ (x * w[:, None]), x.T @ (y - p))
            except np.linalg.LinAlgError:
                return None
            beta += step
            if not np.all(np.isfinite(beta)) or np.abs(beta).max() > 50:
                return None
            if np.max(np.abs(step)) < 1e-9:
                return beta
    return None


def propose(frame: pd.DataFrame, method: str, thresholds: dict, scale: pd.DataFrame | None = None) -> dict:
    """Propose une PD annuelle par note.

    `frame` : population d'estimation avec pd_finale (annuelle, en %), horizon_mois et defaut_observe.
    `scale` : notes à couvrir (note_finale, rang_note, pd_finale) ; par défaut celles de `frame`.
    """
    data = frame.dropna(subset=["note_finale", "pd_finale", "defaut_observe"]).copy()
    data["_pd"] = data["pd_finale"] / 100
    data["_years"] = (data["horizon_mois"] if "horizon_mois" in data else 12.0) / 12
    data["_pd_h"] = to_horizon(data["_pd"].to_numpy(float), data["_years"].to_numpy(float))
    data["_y"] = data["defaut_observe"].astype(int)
    n, defaults = len(data), int(data["_y"].sum())
    if method not in METHODS:
        raise ValueError("Méthode de recalibrage inconnue.")
    notes = []
    if method == "logistic" and defaults < thresholds["minimum_defaults_for_logistic"]:
        raise ValueError(
            f"Recalibrage logistique impossible : {defaults} défaut(s), il en faut au moins "
            f"{thresholds['minimum_defaults_for_logistic']}. Choisissez l'ajustement bayésien."
        )

    grades = data.groupby("note_finale", observed=True).agg(
        rank=("rang_note", "mean"), exposures=("_y", "size"), defaults=("_y", "sum"), current_pd=("_pd", "mean"),
        prior_h=("_pd_h", "mean"), years=("_years", "mean"),
    ).reset_index()
    grades["observed_dr"] = grades["defaults"] / grades["exposures"]

    if method == "logistic":
        beta = _fit_logistic(data["_pd_h"].to_numpy(float), data["_y"].to_numpy(float))
        if beta is None or beta[1] <= 0:
            reason = ("l'ajustement ne converge pas" if beta is None else
                      "la relation entre PD et défaut est inversée (les notes risquées font moins défaut)")
            notes.append(f"Recalibrage logistique écarté : {reason}. Méthode bayésienne appliquée à la place.")
            method = "bayesian"
        else:
            q = 1 / (1 + np.exp(-(beta[0] + beta[1] * _logit(grades["prior_h"].to_numpy(float)))))
            grades["estimated_pd"] = to_annual(q, grades["years"].to_numpy(float))
    if method == "central_tendency":
        # Facteur f tel que les défauts attendus sur l'horizon observé égalent les défauts observés.
        low, high = 1e-3, 1e3
        pd_values, years = data["_pd"].to_numpy(float), data["_years"].to_numpy(float)
        for _ in range(100):
            mid = (low * high) ** 0.5
            if to_horizon(np.clip(pd_values * mid, 0, 1), years).sum() < defaults:
                low = mid
            else:
                high = mid
        grades["estimated_pd"] = np.clip(grades["current_pd"] * (low * high) ** 0.5, 0, 1)
    elif method == "bayesian":
        k = float(thresholds["bayesian_prior_strength"])
        posterior = (grades["prior_h"] * k + grades["defaults"]) / (k + grades["exposures"])
        grades["estimated_pd"] = to_annual(posterior.to_numpy(float), grades["years"].to_numpy(float))

    # Couverture de toute l'échelle : les notes absentes de l'estimation reçoivent l'ajustement
    # relatif (PD estimée / PD actuelle) interpolé entre leurs voisines.
    uncovered = []
    if scale is not None and len(scale):
        full = scale.groupby("note_finale", observed=True).agg(rank=("rang_note", "mean"),
                                                               current_pd=("pd_finale", "mean")).reset_index()
        full["current_pd"] = full["current_pd"] / 100
        missing = full[~full["note_finale"].isin(grades["note_finale"])]
        if len(missing):
            ratio = (grades["estimated_pd"] / grades["current_pd"].clip(lower=1e-9)).to_numpy(float)
            order = np.argsort(grades["rank"].to_numpy(float))
            interpolated = np.interp(missing["rank"].to_numpy(float), grades["rank"].to_numpy(float)[order], ratio[order])
            extra = missing.assign(exposures=0, defaults=0, observed_dr=np.nan,
                                   estimated_pd=np.clip(missing["current_pd"].to_numpy(float) * interpolated, 0, 1))
            uncovered = [str(g) for g in missing["note_finale"]]
            grades = pd.concat([grades, extra], ignore_index=True)
    grades = grades.sort_values(["rank", "note_finale"]).reset_index(drop=True)

    # Marge de prudence : borne haute unilatérale du taux de défaut global (sur l'horizon observé).
    confidence = float(thresholds["moc_confidence"])
    upper = wilson_interval(defaults, n, confidence=2 * confidence - 1)["upper"] if n else 0.0
    moc_factor = upper / (defaults / n) if defaults else 1.0
    floor = float(thresholds["pd_floor_percent"]) / 100
    proposed = np.clip(grades["estimated_pd"].to_numpy(float) * moc_factor, floor, 1.0)
    ordered = np.maximum.accumulate(proposed)  # ordre de l'échelle respecté
    flattened = [str(g) for g, before, after in zip(grades["note_finale"], proposed, ordered) if after > before + 1e-12]
    if flattened:
        notes.append("PD relevées pour respecter l'ordre de l'échelle (même PD que la note précédente) : "
                     + ", ".join(flattened) + ".")
    if uncovered:
        notes.append("Notes absentes de l'échantillon, ajustées par interpolation entre leurs voisines : "
                     + ", ".join(uncovered) + ".")

    mapping = [
        {
            "grade": str(r.note_finale), "rank": float(r.rank), "exposures": int(r.exposures),
            "defaults": int(r.defaults), "observed_dr": None if pd.isna(r.observed_dr) else float(r.observed_dr),
            "old_pd": float(r.current_pd), "estimated_pd": float(r.estimated_pd), "new_pd": float(p),
            "change": float(p - r.current_pd), "interpolated": str(r.note_finale) in uncovered,
        }
        for r, p in zip(grades.itertuples(), ordered)
    ]
    label, explanation = METHODS[method]
    return {
        "method": method,
        "method_label": label,
        "method_explanation": explanation,
        "defaults": defaults,
        "population": n,
        "default_rate": defaults / n if n else None,
        "moc": {"confidence": confidence, "factor": float(moc_factor),
                "explanation": f"PD estimées multipliées par {moc_factor:.2f} : le niveau cible est la borne "
                               f"haute à {confidence:.0%} du taux de défaut observé."},
        "pd_floor": floor,
        "grade_column": "note_finale",
        "mapping": mapping,
        "notes": notes,
        "governance_note": "Proposition uniquement : elle doit être revalidée sur des données indépendantes puis "
                           "approuvée par un superviseur autre que son auteur avant toute mise en production.",
    }


def apply_mapping(data: pd.DataFrame, mapping: list[dict]) -> tuple[pd.DataFrame, list[str]]:
    """Applique les PD annuelles proposées (en %) sans modifier les PD d'origine.

    Renvoie aussi les notes présentes dans les données mais absentes de la proposition.
    """
    out = data.copy()
    lookup = {str(item["grade"]): item["new_pd"] * 100 for item in mapping}
    mapped = out["note_finale"].astype(str).map(lookup).astype(float)
    uncovered = sorted(set(out.loc[mapped.isna(), "note_finale"].astype(str)))
    out["pd_recalibree"] = mapped.fillna(pd.to_numeric(out["pd_finale"], errors="coerce"))
    return out, uncovered
