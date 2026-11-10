"""Moteur de backtesting : discrimination, calibration, stabilité, dérogations et décision finale."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .metrics import (
    auc_gini,
    bootstrap_gini_ci,
    brier_score,
    critical_defaults,
    hosmer_lemeshow_by_grade,
    ks_statistic,
    monotonicity,
    psi,
    traffic_light,
    wilson_interval,
)


def run_backtest(
    data: pd.DataFrame,
    thresholds: dict,
    correlation: float,
    grade_column: str = "note_finale",
    pd_column: str = "pd_finale",
    rank_column: str = "rang_note",
    default_column: str = "defaut_observe",
    include_uncertainty: bool = True,
    score_column: str | None = None,
    annual_pd_column: str | None = None,
) -> dict:
    """Mesures de performance d'un système de notation sur une population donnée (PD en %).

    `pd_column` : PD attendue sur l'horizon observé (sert à la calibration).
    `score_column` : PD servant à classer les clients (discrimination) ; par défaut `pd_column`.
    `annual_pd_column` : PD annuelle affichée à titre d'information.
    """
    frame = data.dropna(subset=[grade_column, pd_column, default_column]).copy()
    frame["_y"] = frame[default_column].astype(int)
    frame["_pd"] = pd.to_numeric(frame[pd_column], errors="coerce") / 100
    frame["_score"] = pd.to_numeric(frame[score_column or pd_column], errors="coerce")
    frame["_annual"] = pd.to_numeric(frame[annual_pd_column or pd_column], errors="coerce") / 100
    frame = frame.dropna(subset=["_pd", "_score"])
    if rank_column not in frame:
        frame[rank_column] = frame["_pd"]
    n, defaults = len(frame), int(frame["_y"].sum())

    auc, gini = auc_gini(frame["_y"], frame["_score"])
    grades = []
    for grade, group in frame.groupby(grade_column, observed=True):
        exposures, grade_defaults = len(group), int(group["_y"].sum())
        pd_predicted = float(group["_pd"].mean())
        light = traffic_light(grade_defaults, exposures, pd_predicted, correlation, thresholds)
        grades.append({
            "grade": str(grade),
            "rank": float(group[rank_column].mean()),
            "exposures": exposures,
            "defaults": grade_defaults,
            "pd_predicted": pd_predicted,
            "pd_annual": float(group["_annual"].mean()),
            "default_rate_observed": grade_defaults / exposures,
            "gap": grade_defaults / exposures - pd_predicted,
            "expected_defaults": light["expected_defaults"],
            "confidence_interval": wilson_interval(grade_defaults, exposures),
            "traffic_light": light["light"],
            "p_value": light["p_value"],
            "p_value_correlated": light["p_value_correlated"],
            "orange_from_defaults": light["orange_from_defaults"],
            "red_from_defaults": light["red_from_defaults"],
            "pd_overestimated": light["overestimated"],
            "rule": light["rule"],
        })
    grades.sort(key=lambda g: (g["rank"], g["grade"]))

    mean_pd = float(frame["_pd"].mean()) if n else None
    portfolio = (
        traffic_light(defaults, n, mean_pd, correlation, {**thresholds, "minimum_exposures_per_grade": 1})
        if n else None
    )
    warnings = []
    not_conclusive = sum(g["traffic_light"] == "nc" for g in grades)
    if not_conclusive:
        warnings.append(
            f"{not_conclusive} classe(s) comptent moins de {thresholds['minimum_exposures_per_grade']} "
            "expositions : pas de feu de calibration pour ces classes."
        )
    if auc is None:
        warnings.append("Discrimination non calculable : aucune observation de défaut (ou aucun client sain).")

    return {
        "population": n,
        "defaults": defaults,
        "default_rate": defaults / n if n else None,
        "mean_pd": mean_pd,
        "auc": auc,
        "gini": gini,
        "gini_confidence_interval": (
            bootstrap_gini_ci(frame["_y"], frame["_score"], thresholds.get("bootstrap_iterations", 300))
            if include_uncertainty else None
        ),
        "ks": ks_statistic(frame["_y"], frame["_score"]),
        "brier_score": brier_score(frame["_y"], frame["_pd"]),
        "grades": grades,
        "portfolio_calibration": portfolio and {
            "light": portfolio["light"], "p_value": portfolio["p_value"],
            "p_value_correlated": portfolio["p_value_correlated"], "rule": portfolio["rule"],
            "expected_defaults": portfolio["expected_defaults"],
        },
        "hosmer_lemeshow": hosmer_lemeshow_by_grade(frame, grade_column, "_pd", "_y"),
        "pd_monotonicity": monotonicity(grades),
        "correlation": correlation,
        "warnings": warnings,
    }


def analyze_overrides(data: pd.DataFrame, thresholds: dict, correlation: float) -> dict:
    """Compare la note du modèle (avant dérogation) et la note finale retenue."""
    if "note_fondamentale" not in data and "override" not in data:
        return {"available": False, "reason": "Colonnes de note avant dérogation / override non fournies."}
    base = data[data["defaut_observe"].notna()]
    if "override" in base:
        overridden = base["override"].notna()
    else:
        overridden = base["note_fondamentale"].notna() & (base["note_fondamentale"] != base["note_finale"])
    result = {
        "available": True,
        "population": int(len(base)),
        "override_count": int(overridden.sum()),
        "override_rate": float(overridden.mean()) if len(base) else None,
    }
    if "rang_fondamental" in base:
        moved = base[overridden & base["rang_fondamental"].notna()]
        result["direction"] = {
            "Note dégradée par l'analyste": int((moved["rang_note"] > moved["rang_fondamental"]).sum()),
            "Note améliorée par l'analyste": int((moved["rang_note"] < moved["rang_fondamental"]).sum()),
        }
    elif "override" in base:
        result["direction"] = {str(k): int(v) for k, v in base.loc[overridden, "override"].value_counts().items()}
    if {"note_fondamentale", "pd_fondamentale"} <= set(base.columns):
        fundamental = base.dropna(subset=["note_fondamentale", "pd_fondamentale"])
        if not fundamental.empty:
            horizon_column = "pd_fond_horizon" if "pd_fond_horizon" in fundamental else "pd_fondamentale"
            result["fundamental_backtest"] = run_backtest(
                fundamental, thresholds, correlation, "note_fondamentale", horizon_column,
                "rang_fondamental", include_uncertainty=False, score_column="pd_fondamentale",
            )
        # Efficacité du jugement expert : les clients dégradés par l'analyste font-ils plus défaut ?
        if "rang_fondamental" in base:
            moved = base[overridden & base["rang_fondamental"].notna()]
            down = moved[moved["rang_note"] > moved["rang_fondamental"]]
            up = moved[moved["rang_note"] < moved["rang_fondamental"]]
            unchanged = base[~overridden]
            result["effectiveness"] = {
                label: {"clients": int(len(g)), "default_rate": float(g["defaut_observe"].mean()) if len(g) else None}
                for label, g in (("Note dégradée", down), ("Note améliorée", up), ("Sans dérogation", unchanged))
            }
    return result


def analyze_stability(reference: pd.DataFrame | None, current: pd.DataFrame, thresholds: dict) -> dict:
    """PSI sur la répartition des notes et matrice de migration des clients communs."""
    if reference is None or reference.empty:
        return {"available": False, "reason": "Aucun fichier de référence choisi : PSI et migrations non calculés."}
    value = psi(reference["note_finale"], current["note_finale"])
    if value is None:
        return {"available": False, "reason": "Répartition des notes vide dans l'un des deux fichiers."}
    status = "green" if value < thresholds["psi_warning"] else "orange" if value <= thresholds["psi_critical"] else "red"
    ref = reference.drop_duplicates("id_contrepartie")[["id_contrepartie", "note_finale", "rang_note"]]
    cur = current.drop_duplicates("id_contrepartie")[["id_contrepartie", "note_finale", "rang_note"]]
    joined = ref.merge(cur, on="id_contrepartie", suffixes=("_ref", "_cur"))
    order = {**dict(zip(ref["note_finale"], ref["rang_note"])), **dict(zip(cur["note_finale"], cur["rang_note"]))}
    matrix = pd.crosstab(joined["note_finale_ref"], joined["note_finale_cur"])
    rows = sorted(matrix.index, key=lambda g: (order.get(g, np.inf), str(g)))
    cols = sorted(matrix.columns, key=lambda g: (order.get(g, np.inf), str(g)))
    matrix = matrix.reindex(index=rows, columns=cols, fill_value=0)
    return {
        "available": True,
        "psi": value,
        "psi_status": status,
        "common_clients": int(len(joined)),
        "migration_matrix": {str(r): {str(c): int(matrix.at[r, c]) for c in cols} for r in rows},
    }


# ------------------------------------------------------------------------------
# Décision finale
# ------------------------------------------------------------------------------

VERDICTS = {
    "inconclusive": ("Non concluant", "extend_history", "Allonger l'historique (agréger des périodes) avant toute décision"),
    "redevelopment": ("Refonte du modèle", "model_redevelopment",
                      "Engager la refonte : l'insuffisance du pouvoir discriminant est significative, matérielle et confirmée"),
    "recalibration": ("Recalibrage des PD", "pd_recalibration", "Proposer un recalibrage des PD, puis le faire valider"),
    "redevelopment_watch": ("Surveillance renforcée — refonte à confirmer", "confirm_redevelopment",
                            "Le pouvoir discriminant se dégrade : confirmer au prochain exercice avant toute refonte"),
    "scope_review": ("Maintien sous surveillance — population instable", "scope_review",
                     "Analyser l'évolution de la population avant de modifier le modèle"),
    "monitor": ("Maintien sous surveillance renforcée", "monitor", "Suivre les points d'alerte au prochain exercice"),
    "pass": ("Modèle maintenu", "no_action", "Aucune action corrective ; poursuivre le backtesting périodique"),
}
STATUS_OF = {"inconclusive": "inconclusive", "redevelopment": "review", "recalibration": "review",
             "redevelopment_watch": "monitor", "scope_review": "monitor", "monitor": "monitor", "pass": "pass"}


def _sentence(text: str) -> str:
    """Majuscule initiale sans toucher au reste (« PD » reste « PD »)."""
    return (text[:1].upper() + text[1:] + ".") if text else ""


def _criterion(key, label, value, threshold, result, comment):
    return {"key": key, "label": label, "value": value, "threshold": threshold, "result": result, "comment": comment}


def _volume_criterion(result: dict, thresholds: dict) -> dict:
    enough = result["defaults"] >= thresholds["minimum_defaults_for_decision"]
    return _criterion(
        "volume", "Nombre de défauts observés", result["defaults"], f"≥ {thresholds['minimum_defaults_for_decision']}",
        "conforme" if enough else "critique",
        "Volume suffisant pour conclure." if enough else
        "Trop peu de défauts : les indicateurs ci-dessous sont indicatifs et ne fondent pas de décision.",
    )


def calibration_criteria(result: dict, thresholds: dict) -> list[dict]:
    """Feux par note, test du portefeuille et ordre des PD."""
    criteria = []
    grades = result.get("grades", [])
    reds = [g["grade"] for g in grades if g["traffic_light"] == "red"]
    oranges = [g["grade"] for g in grades if g["traffic_light"] == "orange"]
    over = [g["grade"] for g in grades if g.get("pd_overestimated")]
    # Chaque note est testée à 5 % : sur k notes, quelques oranges surviennent par hasard même
    # si toutes les PD sont justes. L'alerte n'est levée qu'au-delà de ce que le hasard explique.
    tested = sum(g["traffic_light"] != "nc" for g in grades)
    orange_alpha = float(thresholds["traffic_light_orange_pvalue"])
    orange_tolerance = max(1, critical_defaults(tested, orange_alpha, 0.0, 0.05)) if tested else 1
    calib = "critique" if reds else "alerte" if len(oranges) >= orange_tolerance else "conforme"
    portfolio = result.get("portfolio_calibration") or {}
    systematic = calib == "alerte" and portfolio.get("light") in ("orange", "red")
    if systematic:
        calib = "critique"  # plusieurs notes ET niveau global en écart : sous-estimation systématique
    comment = []
    if systematic:
        comment.append("sous-estimation systématique : trop de notes en orange et niveau global de défaut significativement "
                       "supérieur à la PD moyenne")
    if reds:
        comment.append("PD sous-estimée même pour une année défavorable (rouge) : note(s) " + ", ".join(reds))
    if oranges:
        comment.append("écart significatif, encore explicable par la conjoncture (orange) : note(s) " + ", ".join(oranges))
    if oranges and calib == "conforme":
        comment.append(f"{len(oranges)} orange(s) sur {tested} notes testées : compatible avec le hasard "
                       f"(alerte à partir de {orange_tolerance})")
    if not comment:
        comment.append("défauts observés compatibles avec la PD dans toutes les classes évaluables")
    if over:
        comment.append("PD prudente (trop peu de défauts) pour " + ", ".join(over))
    criteria.append(_criterion("calibration_grades", "Calibration par note (feux)",
                               f"{len(reds)} rouge(s), {len(oranges)} orange(s)",
                               f"aucun rouge, moins de {orange_tolerance} orange(s)", calib, _sentence("; ".join(comment))))
    if portfolio:
        level = {"red": "critique", "orange": "alerte", "green": "conforme"}.get(portfolio["light"], "non_evaluable")
        criteria.append(_criterion(
            "calibration_portfolio", "Calibration du portefeuille",
            f"{result['defaults']} défauts pour {portfolio['expected_defaults']:.1f} attendus", portfolio["rule"], level,
            {"conforme": "Niveau global de PD cohérent.",
             "alerte": "Plus de défauts qu'attendu au global ; l'écart reste explicable par une année défavorable.",
             "critique": "Le niveau global de PD est sous-estimé, même pour une année défavorable."}.get(level, ""),
        ))
    mono = result.get("pd_monotonicity") or {}
    criteria.append(_criterion(
        "monotonicity", "Ordre des PD le long de l'échelle", mono.get("violations", 0), "0 inversion",
        "conforme" if mono.get("is_monotonic", True) else "alerte",
        "La PD augmente quand la note se dégrade." if mono.get("is_monotonic", True)
        else "Inversions de PD : " + ", ".join(mono.get("pairs", [])) + ".",
    ))
    return criteria


def redevelopment_check(result: dict, thresholds: dict, context: dict) -> dict:
    """Conditions cumulatives exigées avant de proposer une refonte du modèle."""
    gini, ci = result.get("gini"), result.get("gini_confidence_interval") or {}
    minimum = float(thresholds["gini_minimum"])
    upper = ci.get("upper_95", gini)
    significant = gini is not None and upper is not None and upper < minimum
    development_gini = context.get("development_gini")
    drop = (development_gini - gini) / development_gini if development_gini and gini is not None else None
    required = int(thresholds["redevelopment_confirmations"])
    confirmed = (context.get("previous_deficient", 0) + 1) if significant else 0
    conditions = [
        {"condition": "Gini significativement inférieur au seuil",
         "met": significant,
         "detail": ("Gini non calculable." if gini is None else
                    f"Gini {gini:.3f}, borne haute de l'intervalle de confiance {upper:.3f}, seuil {minimum:.2f}.")},
        {"condition": "Nombre de défauts suffisant pour conclure sur le Gini",
         "met": result["defaults"] >= thresholds["minimum_defaults_for_redevelopment"],
         "detail": f"{result['defaults']} défauts, minimum {thresholds['minimum_defaults_for_redevelopment']}."},
        {"condition": "Dégradation matérielle depuis le développement",
         "met": None if drop is None else drop >= thresholds["gini_max_relative_drop"],
         "detail": ("Gini de développement non renseigné dans le référentiel des modèles : condition non évaluée."
                    if drop is None else
                    f"Gini de développement {development_gini:.3f}, baisse de {drop:.0%} "
                    f"(seuil {thresholds['gini_max_relative_drop']:.0%}).")},
        {"condition": "Insuffisance confirmée sur des exercices consécutifs",
         "met": confirmed >= required,
         "detail": f"{confirmed} exercice(s) consécutif(s) sur {required} exigé(s)."},
    ]
    return {"all_met": significant and all(c["met"] is not False for c in conditions),
            "discrimination_deficient": significant, "conditions": conditions}


def decision(result: dict, thresholds: dict, stability: dict | None = None, overrides: dict | None = None,
             context: dict | None = None) -> dict:
    """Verdict final avec la liste complète des critères examinés et leur justification."""
    stability, overrides, context = stability or {}, overrides or {}, context or {}
    criteria = [_volume_criterion(result, thresholds)]
    enough = criteria[0]["result"] == "conforme"

    gini, ci = result.get("gini"), result.get("gini_confidence_interval") or {}
    check = redevelopment_check(result, thresholds, context)
    minimum = thresholds["gini_minimum"]
    ci_text = f" (IC 95 % : {ci['lower_95']:.2f} à {ci['upper_95']:.2f})" if ci else ""
    if gini is None:
        criteria.append(_criterion("gini", "Pouvoir discriminant (Gini)", None, f"≥ {minimum:.2f}",
                                   "non_evaluable", "Non calculable sans défaut observé."))
    elif gini >= minimum:
        criteria.append(_criterion("gini", "Pouvoir discriminant (Gini)", gini, f"≥ {minimum:.2f}", "conforme",
                                   f"Le modèle classe correctement les clients risqués{ci_text}."))
    else:
        significant = check["discrimination_deficient"]
        criteria.append(_criterion(
            "gini", "Pouvoir discriminant (Gini)", gini, f"≥ {minimum:.2f}", "critique" if significant else "alerte",
            (f"Gini significativement inférieur au seuil{ci_text}." if significant else
             f"Gini sous le seuil, mais l'écart n'est pas significatif{ci_text}."),
        ))
    development_gini = context.get("development_gini")
    if development_gini and gini is not None:
        drop = (development_gini - gini) / development_gini
        ok = drop < thresholds["gini_max_relative_drop"]
        criteria.append(_criterion(
            "gini_drift", "Évolution du Gini depuis le développement", f"{development_gini:.3f} → {gini:.3f}",
            f"baisse < {thresholds['gini_max_relative_drop']:.0%}", "conforme" if ok else "alerte",
            f"Baisse de {drop:.0%} par rapport au développement." if drop > 0
            else "Pas de dégradation depuis le développement."))
    ks = result.get("ks")
    if ks is not None:
        ok = ks >= thresholds["ks_minimum"]
        criteria.append(_criterion("ks", "Séparation sains / défauts (KS)", ks, f"≥ {thresholds['ks_minimum']:.2f}",
                                   "conforme" if ok else "alerte",
                                   "Séparation suffisante." if ok else "Séparation faible entre clients sains et en défaut."))

    criteria += calibration_criteria(result, thresholds)

    hl = result.get("hosmer_lemeshow") or {}
    if hl.get("p_value") is not None:
        criteria.append(_criterion(
            "hosmer_lemeshow", "Test global de Hosmer-Lemeshow (p-valeur)", hl["p_value"], "information", "information",
            "Test global complémentaire (toutes notes ensemble, sans corrélation), donné à titre indicatif."))

    if stability.get("available"):
        value = stability["psi"]
        level = "critique" if value > thresholds["psi_critical"] else "alerte" if value >= thresholds["psi_warning"] else "conforme"
        criteria.append(_criterion("psi", "Stabilité de la population (PSI)", value,
                                   f"< {thresholds['psi_warning']:.2f} (critique > {thresholds['psi_critical']:.2f})", level,
                                   {"conforme": "Population stable.", "alerte": "Évolution modérée de la population.",
                                    "critique": "Forte dérive de la population par rapport à la référence."}[level]))
    else:
        criteria.append(_criterion("psi", "Stabilité de la population (PSI)", None, f"< {thresholds['psi_warning']:.2f}",
                                   "non_evaluable", stability.get("reason", "Non calculé.")))

    if overrides.get("available") and overrides.get("override_rate") is not None:
        rate = overrides["override_rate"]
        ok = rate <= thresholds["override_rate_critical"]
        criteria.append(_criterion("overrides", "Taux de dérogation (override)", rate,
                                   f"≤ {thresholds['override_rate_critical']:.0%}", "conforme" if ok else "alerte",
                                   "Jugement expert limité." if ok
                                   else "Dérogations fréquentes : le modèle omet peut-être un facteur de risque."))

    scale = context.get("scale") or {}
    if scale.get("non_default_grades") is not None:
        required = int(thresholds["minimum_non_default_grades"])
        count = scale["non_default_grades"]
        criteria.append(_criterion(
            "scale_structure", "Structure de l'échelle (notes saines)", count, f"≥ {required} + 1 note de défaut",
            "conforme" if count >= required else "alerte",
            "Échelle conforme à la circulaire BCT n°2016-06 (art. 4 b)." if count >= required else
            f"Seulement {count} note(s) saine(s) utilisée(s) : la circulaire BCT n°2016-06 (art. 4 b) en exige au moins "
            f"{required}, plus une note de défaut."))
    if scale.get("max_share") is not None:
        limit = float(thresholds["max_grade_concentration"])
        share = scale["max_share"]
        criteria.append(_criterion(
            "concentration", "Concentration sur une note", share, f"≤ {limit:.0%} des clients",
            "conforme" if share <= limit else "alerte",
            (f"Note la plus peuplée : {scale['max_share_grade']} ({share:.0%} des clients) ; "
             f"indice de Herfindahl {scale['herfindahl']:.3f}.") if share <= limit else
            (f"{share:.0%} des clients sur la note {scale['max_share_grade']} : concentration à justifier par des preuves "
             "empiriques (circulaire BCT n°2016-06, art. 4 d et e).")))

    quality = context.get("data_quality") or {}
    if quality:
        rate = quality.get("exclusion_rate") or 0.0
        if rate > thresholds["max_exclusion_rate"]:
            level = "alerte"
        else:
            level = "information" if quality.get("proxy") else "conforme"
        notes = [f"{rate:.0%} des lignes du fichier écartées à l'import"]
        if quality.get("proxy"):
            notes.append("défaut déduit de la note observée (approximation)")
        criteria.append(_criterion("data_quality", "Qualité des données et définition du défaut", rate,
                                   f"≤ {thresholds['max_exclusion_rate']:.0%} de lignes écartées", level,
                                   _sentence(" ; ".join(notes))))
    horizon = context.get("horizon") or {}
    if horizon:
        criteria.append(_criterion("horizon", "Horizon d'observation", f"{horizon['months']} mois", "information",
                                   "information", horizon.get("explanation", "")))

    def worst(key):
        return next((c["result"] for c in criteria if c["key"] == key), None)

    if not enough:
        case = "inconclusive"
    elif check["all_met"]:
        case = "redevelopment"
    elif check["discrimination_deficient"]:
        # Le modèle ne classe plus les clients : recalibrer ses PD ne corrigerait pas le classement.
        case = "redevelopment_watch"
    elif "critique" in (worst("calibration_grades"), worst("calibration_portfolio")):
        case = "recalibration"
    elif worst("psi") == "critique":
        case = "scope_review"
    elif any(c["result"] == "alerte" for c in criteria):
        case = "monitor"
    else:
        case = "pass"
    verdict, action, next_step = VERDICTS[case]
    findings = [c for c in criteria if c["result"] in ("critique", "alerte")]
    justification = [f"{c['label']} : {c['comment']}" for c in findings] or [
        "Tous les critères évaluables sont conformes aux seuils de la politique."]
    if check["discrimination_deficient"] and case != "redevelopment":
        unmet = [c["condition"] for c in check["conditions"] if c["met"] is False]
        justification.append("Refonte non proposée à ce stade : conditions non remplies — " + " ; ".join(unmet) + ".")
        if "critique" in (worst("calibration_grades"), worst("calibration_portfolio")):
            justification.append("Un recalibrage des PD n'est pas recommandé tant que le pouvoir discriminant est "
                                 "insuffisant : il ne corrigerait pas le classement des clients.")
    elif worst("gini") == "alerte":
        justification.append("Gini sous le seuil sans écart statistiquement significatif (l'intervalle de confiance "
                             "contient le seuil) : aucune refonte n'est envisagée, le Gini est suivi au prochain exercice.")
    return {
        "status": STATUS_OF[case],
        "case": case,
        "verdict": verdict,
        "action": action,
        "next_step": next_step,
        "reason": justification[0],
        "justification": justification,
        "criteria": criteria,
        "redevelopment_check": check,
        "recommended_method": "auto" if case == "recalibration" else None,
    }


CALIBRATION_VERDICTS = {
    "inconclusive": ("Non concluant", "Trop peu de défauts pour juger les PD proposées"),
    "review": ("PD proposées insuffisantes", "Revoir la proposition : des notes restent sous-estimées"),
    "monitor": ("PD proposées acceptables, à surveiller", "Approuver en suivant les points d'alerte"),
    "pass": ("PD proposées conformes", "Les PD proposées sont cohérentes avec les défauts observés"),
}


def calibration_decision(result: dict, thresholds: dict) -> dict:
    """Verdict d'une proposition de recalibrage : la calibration seule (le Gini ne change pas)."""
    criteria = [_volume_criterion(result, thresholds)] + calibration_criteria(result, thresholds)
    results = {c["key"]: c["result"] for c in criteria}
    if results["volume"] == "critique":
        status = "inconclusive"
    elif "critique" in (results.get("calibration_grades"), results.get("calibration_portfolio")):
        status = "review"
    elif "alerte" in results.values():
        status = "monitor"
    else:
        status = "pass"
    verdict, next_step = CALIBRATION_VERDICTS[status]
    findings = [c for c in criteria if c["result"] in ("critique", "alerte")]
    justification = [f"{c['label']} : {c['comment']}" for c in findings] or [
        "Avec les PD proposées, les défauts observés sont compatibles avec les PD dans toutes les notes évaluables."]
    return {"status": status, "case": status, "verdict": verdict, "next_step": next_step,
            "reason": justification[0], "justification": justification, "criteria": criteria,
            "favorable": status in ("pass", "monitor")}
