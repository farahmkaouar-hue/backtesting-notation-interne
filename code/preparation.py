"""Préparation des données : contrôles, définition du défaut, population de backtesting.

Rien n'est supprimé : chaque ligne écartée porte un motif lisible. Les colonnes
du fichier sont d'abord renommées selon la correspondance validée par
l'utilisateur (voir app/fields.py) ; tout le reste du calcul est générique.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import (
    BCT_DEFAULT_CLASSES,
    BCT_REFERENCE,
    MODEL_ALIASES,
)
from ..fields import FIELD_BY_KEY, normalize
from .ingestion import clean_text, parse_dates, parse_numeric

# Motifs d'exclusion, dans l'ordre où ils sont appliqués.
EXCLUSION_REASONS = {
    "champ_manquant": "Champ obligatoire vide (client, date, note, PD ou modèle)",
    "pd_invalide": "PD illisible, négative ou supérieure à 100 %",
    "notation_posterieure": "Note attribuée après la date de performance",
    "deja_en_defaut": "Client déjà en défaut à la date de notation",
    "approbation": "Note non approuvée dans la période, ou approuvée avant d'être attribuée",
    "defaut_inconnu": "Défaut non observable (note observée, indicateur et classe BCT absents)",
}
# L'horizon d'observation (6, 12, 24 mois…) est choisi au moment du backtesting : la préparation
# calcule seulement, pour chaque note, la durée écoulée jusqu'à la date de performance.
DAYS_PER_MONTH = 30.4375

TRUTHY = {"1", "oui", "o", "yes", "y", "true", "vrai", "d", "defaut", "default", "x"}
FALSY = {"0", "non", "n", "no", "false", "faux", "sain", ""}


# ------------------------------------------------------------------------------
# PD
# ------------------------------------------------------------------------------

def check_pd_scale(values: pd.Series, declared: str = "percent") -> tuple[pd.Series, list[str]]:
    """Ramène les PD en pourcentage. L'échelle est déclarée par l'utilisateur, jamais devinée.

    La détection automatique ne sert qu'à bloquer une déclaration manifestement fausse.
    """
    warnings: list[str] = []
    numeric = parse_numeric(values)
    present = numeric.dropna()
    if present.empty:
        raise ValueError("Aucune PD exploitable dans la colonne fournie.")
    maximum = float(present.max())
    declared = (declared or "percent").strip().lower()
    if declared == "decimal":
        if maximum > 1.0:
            raise ValueError(
                "PD déclarées en décimal (0,005 = 0,5 %) mais certaines valeurs dépassent 1 "
                f"(maximum {maximum:g}). Choisissez « pourcentage » ou corrigez le fichier."
            )
        warnings.append("PD lues en décimal et converties en pourcentage.")
        return numeric * 100, warnings
    if maximum <= 1.0:
        warnings.append(
            "PD déclarées en pourcentage alors que toutes les valeurs sont ≤ 1 : "
            "vérifiez qu'il ne s'agit pas de probabilités décimales (0,005 = 0,5 %)."
        )
    positive = present[present > 0]
    if not positive.empty and maximum > 1.0:
        share_tiny = float((positive < 0.01).mean())
        if share_tiny > 0.05:
            raise ValueError(
                "La colonne PD mélange des probabilités décimales et des pourcentages "
                f"({share_tiny:.1%} des PD < 0,01 alors que le maximum vaut {maximum:g}). "
                "Harmonisez la colonne avant import."
            )
    if maximum > 100:
        raise ValueError(f"PD supérieure à 100 % (maximum {maximum:g}) : vérifiez l'unité de la colonne.")
    return numeric, warnings


# ------------------------------------------------------------------------------
# Échelle de notation
# ------------------------------------------------------------------------------

def _grade_number(values: pd.Series) -> pd.Series:
    return pd.to_numeric(values.astype("string").str.extract(r"(\d+(?:[.,]\d+)?)")[0].str.replace(",", "."), errors="coerce")


def build_scale(grades: pd.Series, pds: pd.Series) -> dict:
    """Ordre des notes, du meilleur au pire.

    Notes numériques (1 à 12, « 7+ », « 8- ») : l'ordre est celui du chiffre, les
    crans +/- sont ignorés. Notes littérales (AAA, BB…) : l'ordre est celui de la
    PD moyenne de chaque note.
    """
    frame = pd.DataFrame({"grade": clean_text(grades), "pd": pds}).dropna(subset=["grade"])
    numbers = _grade_number(frame["grade"])
    numeric = bool(len(frame)) and numbers.notna().mean() >= 0.95
    stats = frame.groupby("grade", observed=True).agg(pd=("pd", "mean"), count=("pd", "size")).reset_index()
    if numeric:
        stats["rank"] = _grade_number(stats["grade"]).astype(float)
    else:
        stats = stats.sort_values("pd", kind="mergesort")
        stats["rank"] = np.arange(1, len(stats) + 1, dtype=float)
    stats = stats.sort_values(["rank", "grade"])
    return {
        "numeric": numeric,
        "ranks": {str(g): float(r) for g, r in zip(stats["grade"], stats["rank"])},
        "grades": [
            {"grade": str(r.grade), "rank": float(r.rank), "pd_mean": float(r.pd) if pd.notna(r.pd) else None,
             "count": int(r.count)}
            for r in stats.itertuples()
        ],
    }


def grade_rank(values: pd.Series, scale: dict) -> pd.Series:
    text = clean_text(values)
    if scale["numeric"]:
        return _grade_number(text).astype(float)
    return text.map(scale["ranks"]).astype(float)


def suggest_default_grade(scale: dict, pd_threshold: float = 100.0) -> str | None:
    """Première note (la meilleure) dont la PD moyenne atteint le seuil de défaut de la politique."""
    for grade in scale["grades"]:
        if grade["pd_mean"] is not None and grade["pd_mean"] >= pd_threshold - 0.005:
            return grade["grade"]
    return None


# ------------------------------------------------------------------------------
# Défaut observé
# ------------------------------------------------------------------------------

def _flag_to_default(values: pd.Series) -> pd.Series:
    text = clean_text(values).str.lower()
    numeric = parse_numeric(values)
    result = pd.Series(np.nan, index=values.index, dtype="float64")
    is_number = numeric.notna().to_numpy(dtype=bool)
    result[is_number] = (numeric[is_number] >= 1).astype(float).to_numpy()
    rest = ~is_number & text.notna().to_numpy(dtype=bool)
    result[rest & text.isin(list(TRUTHY)).to_numpy(dtype=bool)] = 1.0
    result[rest & text.isin(list(FALSY)).to_numpy(dtype=bool)] = 0.0
    return result


def _bct_to_default(values: pd.Series) -> pd.Series:
    classes = _grade_number(values)
    return classes.where(classes.isna(), classes.isin(BCT_DEFAULT_CLASSES).astype(float))


def _model_names(values: pd.Series, overrides: dict | None) -> pd.Series:
    overrides = {str(k).strip(): str(v).strip() for k, v in (overrides or {}).items() if str(v).strip()}
    aliases = {normalize(k): v for k, v in MODEL_ALIASES.items()}
    text = clean_text(values)
    distinct = text.dropna().unique()
    lookup = {v: overrides.get(v) or aliases.get(normalize(v)) or v for v in distinct}
    return text.map(lookup)


# ------------------------------------------------------------------------------
# Préparation
# ------------------------------------------------------------------------------

def prepare(raw: pd.DataFrame, mapping: dict, options: dict) -> tuple[pd.DataFrame, dict]:
    """Construit la population de backtesting.

    options : performance_date (obligatoire), pd_scale, default_grade, default_pd_threshold_percent,
    approval_start, approval_end, model_names, single_model_name.
    La note de défaut et son seuil de PD viennent de la politique fixée par l'administrateur.
    """
    pd_threshold = float(options.get("default_pd_threshold_percent") or 100.0)
    performance = pd.to_datetime(options.get("performance_date"), errors="coerce")
    if pd.isna(performance):
        raise ValueError("La date de performance est obligatoire et doit être une date valide.")

    df = pd.DataFrame({key: raw[column] for key, column in mapping.items() if column}, index=raw.index)
    df = df.reset_index(drop=True)
    warnings: list[str] = []

    # --- Identifiants, modèle, notes --------------------------------------
    for key in ("id_contrepartie", "id_credit", "note_finale", "note_observee", "note_fondamentale",
                "override", "secteur", "segment_commercial", "type_contrepartie", "region"):
        if key in df:
            df[key] = clean_text(df[key])
    if "modele" in df:
        df["modele"] = _model_names(df["modele"], options.get("model_names"))
    else:
        df["modele"] = (options.get("single_model_name") or "Modèle unique").strip()

    # --- Dates -------------------------------------------------------------
    for key in ("date_notation", "date_approbation", "date_defaut"):
        if key in df:
            df[key] = parse_dates(df[key])

    # --- PD ----------------------------------------------------------------
    df["pd_finale"], pd_warnings = check_pd_scale(df["pd_finale"], options.get("pd_scale", "percent"))
    warnings += pd_warnings
    if "pd_fondamentale" in df:
        try:
            df["pd_fondamentale"], _ = check_pd_scale(df["pd_fondamentale"], options.get("pd_scale", "percent"))
        except ValueError as error:
            warnings.append(f"Analyse des dérogations désactivée : PD avant dérogation illisible ({error})")
            df = df.drop(columns=[c for c in ("pd_fondamentale", "note_fondamentale") if c in df])

    # --- Échelle de notation et note de défaut ------------------------------
    scale = build_scale(df["note_finale"], df["pd_finale"])
    df["rang_note"] = grade_rank(df["note_finale"], scale)
    if "note_fondamentale" in df:
        df["rang_fondamental"] = grade_rank(df["note_fondamentale"], scale)
    default_grade = (options.get("default_grade") or "").strip() or suggest_default_grade(scale, pd_threshold)
    default_rank = None
    if default_grade:
        default_rank = float(grade_rank(pd.Series([default_grade]), scale).iloc[0])
        if np.isnan(default_rank):
            raise ValueError(f"La note de défaut « {default_grade} » n'appartient pas à l'échelle de notation.")
    if "note_observee" in df and not ({"flag_defaut", "classe_bct"} & set(df.columns)) and default_rank is None:
        raise ValueError(
            f"Note de défaut introuvable : aucune note de l'échelle n'atteint une PD de {pd_threshold:g} %. "
            "L'administrateur doit fixer la note de défaut dans « Politique et seuils »."
        )

    # --- Défaut observé : indicateur > classe BCT > note observée ------------
    sources = []
    default = pd.Series(np.nan, index=df.index, dtype="float64")
    if "flag_defaut" in df:
        default = default.combine_first(_flag_to_default(df["flag_defaut"]))
        sources.append("indicateur")
    if "classe_bct" in df:
        default = default.combine_first(_bct_to_default(df["classe_bct"]))
        sources.append("classe_bct")
    if "note_observee" in df and default_rank is not None:
        df["rang_observe"] = grade_rank(df["note_observee"], scale)
        proxy = df["rang_observe"].where(df["rang_observe"].isna(), (df["rang_observe"] >= default_rank).astype(float))
        default = default.combine_first(proxy)
        sources.append("note_observee")
        if df["note_observee"].astype("string").str.contains(r"\d\s*[+-]", regex=True, na=False).any():
            warnings.append("La note observée contient des crans (+/−) : seul le chiffre de la note est comparé.")
    # Statut constaté à la date de performance ; la date de défaut, si fournie, permet ensuite
    # de ne compter que les défauts survenus dans l'horizon choisi au backtesting.
    df["defaut_observe"] = default
    df["mois_observes"] = (performance - df["date_notation"]).dt.days / DAYS_PER_MONTH

    # --- Exclusions (première raison applicable) ---------------------------
    required = ["id_contrepartie", "date_notation", "note_finale", "pd_finale", "modele"]
    missing = df[required].isna().any(axis=1)
    pd_invalid = df["pd_finale"].isna() | (df["pd_finale"] < 0) | (df["pd_finale"] > 100)
    after_performance = df["date_notation"] > performance
    already_default = df["pd_finale"] >= pd_threshold - 0.005
    if default_rank is not None:
        already_default |= df["rang_note"] >= default_rank
    if "date_defaut" in df:
        already_default |= df["date_defaut"].notna() & (df["date_defaut"] <= df["date_notation"])
    approval = pd.Series(False, index=df.index)
    if "date_approbation" in df:
        approval |= df["date_approbation"].notna() & (df["date_approbation"] < df["date_notation"])
        start, end = options.get("approval_start"), options.get("approval_end")
        if bool(start) != bool(end):
            raise ValueError("Renseignez les deux bornes de la période d'approbation, ou aucune.")
        if start:
            start, end = pd.to_datetime(start, errors="coerce"), pd.to_datetime(end, errors="coerce")
            if pd.isna(start) or pd.isna(end) or start > end:
                raise ValueError("Période d'approbation invalide.")
            approval |= df["date_approbation"].isna() | (df["date_approbation"] < start) | (df["date_approbation"] > end)
    elif options.get("approval_start"):
        raise ValueError("Une période d'approbation exige la colonne « Date d'approbation de la note ».")
    no_outcome = df["defaut_observe"].isna()

    conditions = [missing, pd_invalid, after_performance, already_default, approval, no_outcome]
    codes = list(EXCLUSION_REASONS)[:len(conditions)]
    masks = [np.asarray(c.fillna(False), dtype=bool) for c in conditions]
    df["motif_exclusion"] = np.select(masks, codes, default="")

    # Un client noté plusieurs fois garde toutes ses notes valides ici : le backtesting retient
    # celle dont la durée d'observation correspond le mieux à l'horizon choisi.
    df["eligible"] = (df["motif_exclusion"] == "").astype(int)

    # --- Cohérence de l'échelle avec la note de défaut ----------------------
    if default_rank is not None:
        for g in scale["grades"]:
            if g["rank"] >= default_rank and g["pd_mean"] is not None and g["pd_mean"] < pd_threshold - 0.005:
                warnings.append(
                    f"La note « {g['grade']} » est traitée comme un défaut mais sa PD vaut {g['pd_mean']:.2f} % "
                    "dans le fichier : vérifiez la note de défaut choisie."
                )
            if g["rank"] < default_rank and g["pd_mean"] is not None and g["pd_mean"] >= pd_threshold - 0.005:
                warnings.append(
                    f"La note « {g['grade']} » a une PD de {g['pd_mean']:.2f} % (seuil de défaut {pd_threshold:g} %) "
                    "mais n'est pas traitée comme un défaut."
                )

    report = _report(df, scale, default_grade, sources, warnings, options, mapping)
    return df, report


def _report(df, scale, default_grade, sources, warnings, options, mapping) -> dict:
    eligible = df[df["eligible"] == 1]
    exclusions = df["motif_exclusion"].value_counts()
    reasons = [
        {"code": code, "label": label, "count": int(exclusions.get(code, 0))}
        for code, label in EXCLUSION_REASONS.items() if exclusions.get(code, 0)
    ]
    models = []
    for model, group in df.groupby("modele", dropna=True, observed=True):
        kept = group[group["eligible"] == 1]
        models.append({"model": str(model), "rows": int(len(group)), "eligible": int(len(kept)),
                       "defaults": int(kept["defaut_observe"].fillna(0).sum())})

    source_labels = {"indicateur": "indicateur de défaut", "classe_bct": "classe BCT (2 à 4 = défaut)",
                     "note_observee": f"note observée ≥ « {default_grade} »"}
    blockers = []
    if sources == ["note_observee"]:
        blockers.append(
            "Le défaut est déduit de la note observée (approximation) et non d'un indicateur de défaut certifié."
        )

    return {
        "rows": int(len(df)),
        "eligible": int(len(eligible)),
        "defaults": int(eligible["defaut_observe"].fillna(0).sum()),
        "default_rate": float(eligible["defaut_observe"].mean()) if len(eligible) else None,
        "exclusions": reasons,
        "clients": int(eligible.groupby("modele")["id_contrepartie"].nunique().sum()) if len(eligible) else 0,
        "observation_months": {
            "min": float(eligible["mois_observes"].min()) if len(eligible) else None,
            "median": float(eligible["mois_observes"].median()) if len(eligible) else None,
            "max": float(eligible["mois_observes"].max()) if len(eligible) else None,
        },
        "dated_defaults": "date_defaut" in df,
        "models": models,
        "rating_scale": scale["grades"],
        "rating_scale_numeric": scale["numeric"],
        "default_definition": {
            "sources": [source_labels[s] for s in sources],
            "default_grade": default_grade,
            "bct_reference": BCT_REFERENCE,
            "summary": "Défaut retenu : " + " ; à défaut ".join(source_labels[s] for s in sources)
                       + (" ; la date de défaut limite le décompte à l'horizon choisi." if "date_defaut" in df
                          else ", constaté à la date de performance."),
        },
        "regulatory_ready": not blockers,
        "regulatory_blockers": blockers,
        "warnings": warnings,
        "configuration": {
            "mapping": {k: v for k, v in mapping.items() if v},
            "mapping_labels": {FIELD_BY_KEY[k].label: v for k, v in mapping.items() if v and k in FIELD_BY_KEY},
            "performance_date": str(pd.to_datetime(options.get("performance_date")).date()),
            "pd_scale": options.get("pd_scale", "percent"),
            "default_grade": default_grade,
            "default_pd_threshold_percent": options.get("default_pd_threshold_percent") or 100.0,
            "approval_start": options.get("approval_start"),
            "approval_end": options.get("approval_end"),
            "model_names": options.get("model_names") or {},
            "single_model_name": options.get("single_model_name"),
        },
    }
