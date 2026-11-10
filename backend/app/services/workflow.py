import pandas as pd
from ..config import MIN_DEFAULTS_FOR_BAYESIAN
from .backtesting import analyze_overrides, analyze_stability, decision, run_backtest
from .recalibration import apply_mapping, propose


def _choose_final_grade(data: pd.DataFrame) -> str:
    """Prefer the granular GRC grade when it is almost fully populated."""
    return "GRC Name" if "GRC Name" in data and data["GRC Name"].notna().mean() >= .95 else "Final Rating Class"


def _by_dimension(data: pd.DataFrame, dimension: str, grade: str, correlation: float, minimum=20):
    if dimension not in data:
        return []
    result = []
    for label, group in data.groupby(dimension, dropna=False):
        if len(group) >= minimum:
            backtest = run_backtest(group, grade, "Final Pd Class", "defaut_observe", correlation, include_uncertainty=False)
            result.append({"segment": str(label), "population": len(group), "defaults": backtest["defaults"],
                           "gini": backtest["gini"], "brier_score": backtest["brier_score"], "warnings": backtest["warnings"]})
    return result


def _cohort_trend(data: pd.DataFrame, grade: str, correlation: float):
    if "date_notation" not in data:
        return []
    frame = data.dropna(subset=["date_notation"]).copy()
    frame["cohort"] = frame["date_notation"].dt.to_period("M").astype(str)
    output = []
    for cohort, group in frame.groupby("cohort"):
        result = run_backtest(group, grade, "Final Pd Class", "defaut_observe", correlation, include_uncertainty=False)
        output.append({"cohort": cohort, "population": len(group), **{key: result[key] for key in ["defaults", "default_rate", "mean_pd", "gini", "ks", "brier_score", "warnings"]}})
    return output


def _out_of_time_split(data: pd.DataFrame, fraction: float):
    """Hold out the latest rating dates; it is never used to estimate the mapping."""
    if "date_notation" not in data:
        return None
    frame = data.dropna(subset=["date_notation"]).sort_values("date_notation")
    dates = frame["date_notation"].dt.normalize().drop_duplicates().tolist()
    if len(dates) < 2:
        return None
    cutoff = dates[max(1, int(len(dates) * (1-fraction))) - 1]
    train, validation = frame[frame["date_notation"] <= cutoff], frame[frame["date_notation"] > cutoff]
    return (train, validation, str(cutoff.date())) if len(train) and len(validation) else None


def _parse_date(value: str | None, label: str) -> pd.Timestamp | None:
    if value is None:
        return None
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        raise ValueError(f"Date invalide pour {label}: {value}")
    return parsed


def _apply_horizon_gates(population: pd.DataFrame, horizon: dict | None, thresholds: dict) -> tuple[pd.DataFrame, dict]:
    if not horizon:
        return population, {"configured": False, "note": "Horizon non fourni; contrôle d'indépendance non exécutable."}

    development_start = _parse_date(horizon.get("development_start"), "development_start")
    development_end = _parse_date(horizon.get("development_end"), "development_end")
    backtest_start = _parse_date(horizon.get("backtest_start"), "backtest_start")
    backtest_end = _parse_date(horizon.get("backtest_end"), "backtest_end")

    if not all([development_start, development_end, backtest_start, backtest_end]):
        raise ValueError("Horizon incomplet: development_start, development_end, backtest_start et backtest_end sont obligatoires.")
    if development_start > development_end:
        raise ValueError("Période de développement invalide: development_start > development_end.")
    if backtest_start > backtest_end:
        raise ValueError("Période de backtesting invalide: backtest_start > backtest_end.")

    overlap = max(development_start, backtest_start) <= min(development_end, backtest_end)
    if overlap:
        raise ValueError("Horizon non conforme: la période de backtesting recouvre la période de développement/entraînement.")

    if "date_notation" not in population:
        raise ValueError("Colonne date_notation absente: horizon backtesting non vérifiable.")

    scoped = population[
        (population["date_notation"].notna())
        & (population["date_notation"] >= backtest_start)
        & (population["date_notation"] <= backtest_end)
    ].copy()

    observed_ratings = int(scoped["note_reelle_num"].notna().sum()) if "note_reelle_num" in scoped else 0
    unique_credits = int(scoped["Number"].nunique()) if "Number" in scoped else 0
    defaults = int(scoped["defaut_observe"].fillna(0).sum()) if "defaut_observe" in scoped else 0
    min_rows = int(thresholds.get("minimum_exploitable_rows", 120))
    min_observed = int(thresholds.get("minimum_observed_ratings", 120))
    min_credits = int(thresholds.get("minimum_unique_credits", 100))

    gate = {
        "configured": True,
        "development_window": {"start": str(development_start.date()), "end": str(development_end.date())},
        "backtest_window": {"start": str(backtest_start.date()), "end": str(backtest_end.date())},
        "rows_in_backtest_window": len(scoped),
        "observed_ratings_in_window": observed_ratings,
        "unique_credits_in_window": unique_credits,
        "defaults_in_window": defaults,
        "minimum_requirements": {
            "rows": min_rows,
            "observed_ratings": min_observed,
            "unique_credits": min_credits,
        },
    }

    if len(scoped) < min_rows or observed_ratings < min_observed or unique_credits < min_credits:
        raise ValueError(
            "Horizon non exploitable: volume insuffisant sur la période de backtesting "
            f"(rows={len(scoped)}, notes_observees={observed_ratings}, credits_uniques={unique_credits})."
        )

    return scoped, gate


def recommend_horizon(
    population: pd.DataFrame,
    development_start: str,
    development_end: str,
    thresholds: dict,
    preferred_months: int = 12,
) -> dict:
    development_start_ts = _parse_date(development_start, "development_start")
    development_end_ts = _parse_date(development_end, "development_end")
    if development_start_ts is None or development_end_ts is None:
        raise ValueError("La période de développement doit être renseignée.")
    if development_start_ts > development_end_ts:
        raise ValueError("Période de développement invalide: development_start > development_end.")
    if "date_notation" not in population:
        raise ValueError("Colonne date_notation absente: recommandation d'horizon impossible.")

    frame = population[population["date_notation"].notna()].copy()
    frame = frame[frame["date_notation"] > development_end_ts]
    if frame.empty:
        raise ValueError("Aucune observation disponible après la période de développement.")

    min_rows = int(thresholds.get("minimum_exploitable_rows", 120))
    min_observed = int(thresholds.get("minimum_observed_ratings", 120))
    min_credits = int(thresholds.get("minimum_unique_credits", 100))
    minimum_months = int(thresholds.get("minimum_backtest_months", 6))
    maximum_months = int(thresholds.get("maximum_backtest_months", 36))
    preferred_months = int(thresholds.get("preferred_backtest_months", preferred_months))
    if minimum_months > maximum_months:
        raise ValueError("Politique invalide: minimum_backtest_months > maximum_backtest_months.")
    preferred_months = min(max(preferred_months, minimum_months), maximum_months)
    latest_date = frame["date_notation"].max().normalize()

    def _stats(window: pd.DataFrame) -> tuple[int, int, int, int]:
        rows = int(len(window))
        observed = int(window["note_reelle_num"].notna().sum()) if "note_reelle_num" in window else 0
        credits = int(window["Number"].nunique()) if "Number" in window else 0
        defaults = int(window["defaut_observe"].fillna(0).sum()) if "defaut_observe" in window else 0
        return rows, observed, credits, defaults

    best = None
    # Priorité à la fenêtre la plus récente et la plus proche de la cible métier.
    # Si elle n'est pas exploitable, l'horizon s'allonge graduellement sans dépasser
    # la limite gouvernée, plutôt que de retenir une période arbitraire.
    candidates = list(range(preferred_months, maximum_months + 1)) + list(range(preferred_months - 1, minimum_months - 1, -1))
    for months in candidates:
        start = (latest_date - pd.DateOffset(months=months)) + pd.Timedelta(days=1)
        window = frame[(frame["date_notation"] >= start) & (frame["date_notation"] <= latest_date)]
        rows, observed, credits, defaults = _stats(window)
        score = (rows >= min_rows, observed >= min_observed, credits >= min_credits, observed, rows, credits)
        candidate = {
            "development_start": str(development_start_ts.date()),
            "development_end": str(development_end_ts.date()),
            "backtest_start": str(start.date()),
            "backtest_end": str(latest_date.date()),
            "months": months,
            "rows": rows,
            "observed_ratings": observed,
            "unique_credits": credits,
            "defaults": defaults,
        }
        if best is None or score > best[0]:
            best = (score, candidate)
        if rows >= min_rows and observed >= min_observed and credits >= min_credits:
            return {
                **candidate,
                "status": "recommended",
                "reason": "Fenêtre la plus récente compatible avec les exigences de volume et d'observation.",
                "minimum_requirements": {
                    "rows": min_rows,
                    "observed_ratings": min_observed,
                    "unique_credits": min_credits,
                },
                "selection_rule": "Fenêtre indépendante la plus récente, proche de la cible métier, satisfaisant les minima gouvernés.",
            }

    fallback = best[1] if best else None
    raise ValueError(
        "Aucun horizon ne satisfait les seuils de la politique active. "
        f"Meilleure fenêtre trouvée: {fallback}."
    )


def execute_backtesting_workflow(
    data: pd.DataFrame,
    model: str,
    correlation: float,
    reference: pd.DataFrame | None = None,
    policy: dict | None = None,
    horizon: dict | None = None,
) -> dict:
    """Run independent discrimination, calibration, stability and override diagnostics."""
    population = data[(data["modele_cible"] == model) & (data["eligible_backtesting"] == 1)].copy()
    if population.empty:
        raise ValueError("Aucune observation éligible pour le modèle sélectionné.")
    final_grade = _choose_final_grade(population)
    thresholds = (policy or {}).get("thresholds", {})
    scoped_population, horizon_gate = _apply_horizon_gates(population, horizon, thresholds)
    final = run_backtest(scoped_population, final_grade, "Final Pd Class", "defaut_observe", correlation)
    final["grade_dimension"] = final_grade
    if final_grade != "Final Rating Class":
        final["rating_class_view"] = run_backtest(scoped_population, "Final Rating Class", "Final Pd Class", "defaut_observe", correlation)
    overrides = analyze_overrides(scoped_population, correlation)
    stability = analyze_stability(
        reference, scoped_population, final_grade,
        psi_warning=float(thresholds.get("psi_warning", .10)),
        psi_critical=float(thresholds.get("psi_critical", .25)),
    )
    return {
        "model": model,
        "policy_version": (policy or {}).get("version", "default"),
        "horizon_gate": horizon_gate,
        "steps": [
            {"name": "discrimination", "method": "AUC, Gini, KS et IC bootstrap", "why": "Mesurer le classement des risques et son incertitude, sans confondre classement et calibration."},
            {"name": "calibration", "method": "Traffic-light Vasicek, binomial exact, Wilson et Hosmer-Lemeshow", "why": "Comparer PD et défauts par grade en tenant compte de la corrélation, avec une vue globale complémentaire."},
            {"name": "stability", "method": "PSI puis migrations", "why": "Détecter un changement de population avant d'attribuer un écart au modèle."},
            {"name": "overrides", "method": "Fundamental versus Final", "why": "Séparer la performance du modèle statistique de l'effet du jugement expert."},
        ],
        "final_backtest": final,
        "overrides": overrides,
        "stability": stability,
        "cohort_trend": _cohort_trend(scoped_population, final_grade, correlation),
        "segment_analysis": {name: _by_dimension(scoped_population, name, final_grade, correlation) for name in ["Sector", "Business Segment", "Counterparty Type", "gouvernorat"]},
        "decision": decision(final, thresholds, stability.get("psi"), overrides.get("override_rate")),
    }


def recalibration_workflow(data: pd.DataFrame, model: str, method: str, correlation: float, validation_fraction=.30, policy: dict | None = None, horizon: dict | None = None) -> dict:
    grade = _choose_final_grade(data)
    thresholds = (policy or {}).get("thresholds", {})
    scoped_data, horizon_gate = _apply_horizon_gates(data, horizon, thresholds)
    split = _out_of_time_split(scoped_data, validation_fraction)
    training = split[0] if split else scoped_data
    defaults = int(training["defaut_observe"].fillna(0).sum())
    min_defaults = int(thresholds.get("minimum_defaults_for_bayesian", MIN_DEFAULTS_FOR_BAYESIAN))
    if defaults < min_defaults:
        return {"proposal": None, "validation_required": False, "status": "blocked_insufficient_defaults", "horizon_gate": horizon_gate,
                "reason": f"{defaults} défaut(s) observé(s) : historique insuffisant pour une proposition automatique. Agréger les périodes."}
    proposal = propose(training, grade, "Final Pd Class", "defaut_observe", model, method,
                       min_logistic_defaults=int(thresholds.get("minimum_defaults_for_logistic", 20)),
                       prior_strength=int(thresholds.get("bayesian_prior_strength", 20)))
    output = {"proposal": proposal, "validation_required": True, "status": "pending_independent_validation", "horizon_gate": horizon_gate,
              "validation_rule": "Le mapping est estimé sur la période de calibration et évalué sur une cohorte temporelle indépendante."}
    if split:
        validation = split[1]
        output["out_of_time_split"] = {"cutoff": split[2], "training_rows": len(training), "validation_rows": len(validation)}
        output["out_of_time_result"] = revalidate(validation, proposal["mapping"], model, correlation, grade, policy)
    else:
        output["out_of_time_warning"] = "Deux dates de notation distinctes au minimum sont requises pour la validation out-of-time automatique."
    return output


def revalidate(data: pd.DataFrame, mapping: list[dict], model: str, correlation: float, grade_column="Final Rating Class", policy: dict | None = None) -> dict:
    population = data.copy()
    if "modele_cible" in population:
        population = population[population["modele_cible"] == model]
    if "eligible_backtesting" in population:
        population = population[population["eligible_backtesting"] == 1]
    if population.empty:
        raise ValueError("Aucune observation éligible disponible pour la revalidation du modèle.")
    before = run_backtest(population, grade_column, "Final Pd Class", "defaut_observe", correlation)
    recalibrated = apply_mapping(population, mapping, grade_column)
    after = run_backtest(recalibrated, grade_column, "pd_recalibree", "defaut_observe", correlation, pd_unit="decimal")
    return {"before": before, "after": after, "decision": decision(after, (policy or {}).get("thresholds", {})),
            "note": "Résultat sur une cohorte indépendante ; la décision finale exige l'approbation du superviseur."}
