import re
import numpy as np
import pandas as pd
from ..config import MODEL_MAPPING, REQUIRED_COLUMNS


def _missing(value) -> bool:
    return pd.isna(value) or (isinstance(value, str) and not value.strip())


def _detect_actual_rating_column(columns, requested: str | None) -> str:
    if requested:
        if requested not in columns:
            raise ValueError(f"Colonne de notation réelle introuvable : {requested}")
        return requested
    candidates = [column for column in columns if re.match(r"^rating[ _]réel(?:[ _].+)?$", str(column), flags=re.IGNORECASE)]
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise ValueError("Aucune colonne de notation réelle détectée. Renseignez son nom à l’import.")
    raise ValueError(f"Plusieurs colonnes de notation réelle détectées : {candidates}. Renseignez celle de l’horizon retenu.")


def prepare(
    raw: pd.DataFrame,
    performance_date: str | None = None,
    actual_rating_column: str | None = None,
    default_thresholds: dict[str, int] | None = None,
) -> tuple[pd.DataFrame, dict]:
    """Prépare sans supprimer : les exclusions sont marquées et justifiées."""
    df = raw.copy()
    df.columns = df.columns.str.strip()
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"Colonnes obligatoires absentes : {sorted(missing)}")

    for col in df.select_dtypes(include=["object", "string"]).columns:
        values = df[col].dropna()
        if values.map(lambda x: isinstance(x, str)).all():
            df[col] = df[col].str.strip()
    if "Process" in df.columns:
        df["Process"] = df["Process"].astype("string").str.replace(r"\s+", " ", regex=True).str.strip()
    df["source_row"] = np.arange(2, len(df) + 2)
    df["modele_cible"] = df["Model Scoring Name"].map(MODEL_MAPPING)
    df["date_notation"] = pd.to_datetime(df["Created Date"], errors="coerce")
    df["date_modification"] = pd.to_datetime(df.get("Last Modified Date"), errors="coerce")
    rating_column = _detect_actual_rating_column(df.columns, actual_rating_column)
    df["note_reelle_num"] = pd.to_numeric(df[rating_column].astype("string").str.extract(r"(\d+)")[0], errors="coerce")
    thresholds = default_thresholds or {}
    fallback_threshold = int(thresholds.get("default", 11))
    df["default_threshold_used"] = df["modele_cible"].map(thresholds).fillna(fallback_threshold).astype(int)
    df["defaut_observe"] = np.nan
    has_observed_rating = df["note_reelle_num"].notna()
    df.loc[has_observed_rating, "defaut_observe"] = (
        df.loc[has_observed_rating, "note_reelle_num"] >= df.loc[has_observed_rating, "default_threshold_used"]
    ).astype(int)

    required = ["Number", "Counterparty", "date_notation", "modele_cible", "Final Rating Class", "Final Pd Class", "note_reelle_num"]
    def reason(row):
        absent = [col for col in required if _missing(row[col])]
        return "" if not absent else "Champ obligatoire absent/non exploitable : " + ", ".join(absent)
    df["motif_non_eligibilite"] = df.apply(reason, axis=1)
    df["anomalie_date"] = df["date_modification"].notna() & (df["date_modification"] < df["date_notation"])
    if performance_date:
        observed = pd.Timestamp(performance_date)
        df["anomalie_look_ahead"] = df["date_notation"].notna() & (df["date_notation"] >= observed)
    else:
        df["anomalie_look_ahead"] = False
    df["anomalie_pd"] = df["Final Pd Class"].isna() | (pd.to_numeric(df["Final Pd Class"], errors="coerce") < 0)
    df["anomalie_modele"] = df["modele_cible"].isna()
    df["anomalie_preparation"] = df[["anomalie_date", "anomalie_look_ahead", "anomalie_pd", "anomalie_modele"]].any(axis=1)
    df["eligible_backtesting"] = ((df["motif_non_eligibilite"] == "") & ~df["anomalie_preparation"]).astype(int)

    report = {
        "rows": len(df), "eligible": int(df["eligible_backtesting"].sum()),
        "defaults": int(pd.Series(df["defaut_observe"]).fillna(0).sum()),
        "duplicates_number": int(df["Number"].duplicated().sum()),
        "models": df["modele_cible"].value_counts(dropna=False).to_dict(),
        "issues": {c: int(df[c].sum()) for c in ["anomalie_date", "anomalie_look_ahead", "anomalie_pd", "anomalie_modele"]},
        "performance_date_configured": performance_date is not None,
        "actual_rating_column": rating_column,
        "default_thresholds": {str(key): int(value) for key, value in {"default": fallback_threshold, **thresholds}.items()},
        "warnings": ([] if performance_date else ["Date de performance non configurée : le contrôle strict d'antériorité notation/défaut est incomplet."]),
    }
    return df, report


def split_models(prepared: pd.DataFrame) -> dict[str, pd.DataFrame]:
    return {model: prepared[prepared["modele_cible"].eq(model)].copy() for model in MODEL_MAPPING.values() if model in prepared["modele_cible"].values}
