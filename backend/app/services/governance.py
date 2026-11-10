from copy import deepcopy


def default_policy() -> dict:
    """Active policy used when no custom policy is stored yet."""
    return {
        "version": "BANK_POLICY_2026_08",
        "name": "Politique interne backtesting et recalibrage",
        "status": "active",
        "thresholds": {
            "gini_minimum": 0.40,
            "ks_minimum": 0.20,
            "psi_warning": 0.10,
            "psi_critical": 0.25,
            "override_rate_critical": 0.20,
            "minimum_defaults_for_decision": 20,
            "minimum_defaults_for_bayesian": 5,
            "minimum_defaults_for_logistic": 20,
            "minimum_exploitable_rows": 120,
            "minimum_observed_ratings": 120,
            "minimum_unique_credits": 100,
            "bayesian_prior_strength": 20,
            "preferred_backtest_months": 12,
            "minimum_backtest_months": 6,
            "maximum_backtest_months": 36,
            "asset_correlation": 0.12,
            "default_rating_thresholds": {
                "default": 11,
                "Professionnel": 11,
                "Corpo_TPME_EF": 11,
                "Corpo_TPME_SANS_EF": 11,
            },
        },
        "justifications": [
            {
                "key": "minimum_exploitable_rows",
                "type": "business",
                "reason": "Garantir une base statistique minimale pour une décision défendable en comité modèle.",
            },
            {
                "key": "minimum_observed_ratings",
                "type": "technical",
                "reason": "Éviter les métriques non représentatives quand la note observée est trop rare sur l'horizon.",
            },
            {
                "key": "minimum_unique_credits",
                "type": "business",
                "reason": "Limiter la concentration excessive sur un sous-ensemble de contreparties.",
            },
            {
                "key": "gini_minimum",
                "type": "business",
                "reason": "Seuil de discrimination accepté par la gouvernance risque interne pour ce périmètre.",
            },
            {
                "key": "psi_critical",
                "type": "technical",
                "reason": "Détecter une dérive populationnelle forte avant d'attribuer un écart au modèle.",
            },
            {"key": "psi_warning", "type": "technical", "reason": "Déclencher une revue précoce de dérive avant le seuil de matérialité critique."},
            {"key": "ks_minimum", "type": "business", "reason": "Seuil minimal de séparation opérationnelle adopté pour l’usage interne du modèle."},
            {"key": "minimum_defaults_for_decision", "type": "technical", "reason": "Éviter une décision fréquentiste instable lorsque le nombre de défauts est insuffisant."},
            {"key": "minimum_defaults_for_bayesian", "type": "technical", "reason": "Exiger un minimum d’information observée même pour une estimation bayésienne."},
            {"key": "minimum_defaults_for_logistic", "type": "technical", "reason": "Limiter le risque d’estimation instable d’une régression logistique de recalibrage."},
            {"key": "override_rate_critical", "type": "business", "reason": "Déclencher une revue du jugement expert lorsqu’il devient matériel dans la décision finale."},
            {"key": "preferred_backtest_months", "type": "business", "reason": "Cible annuelle cohérente avec le cycle de suivi, sous réserve d’exploitabilité."},
            {"key": "minimum_backtest_months", "type": "technical", "reason": "Éviter une fenêtre trop courte, même si les volumes y sont ponctuellement suffisants."},
            {"key": "maximum_backtest_months", "type": "business", "reason": "Éviter l’agrégation de cycles économiques trop éloignés sans revue spécifique."},
            {"key": "asset_correlation", "type": "technical", "reason": "Paramètre Vasicek documenté et versionné, à valider par portefeuille."},
            {"key": "bayesian_prior_strength", "type": "technical", "reason": "Force du prior versionnée afin que la régularisation low-default soit reproductible."},
            {"key": "default_rating_thresholds", "type": "business", "reason": "Définition du défaut par modèle, versionnée et à confirmer par la gouvernance risque avant chaque usage réel."},
        ],
        "process": [
            "quality_gate",
            "horizon_independence_gate",
            "horizon_exploitability_gate",
            "discrimination",
            "calibration",
            "stability",
            "overrides",
            "decision",
            "recalibration_if_needed",
            "independent_validation",
            "supervisor_approval",
        ],
    }


def methodology_catalog() -> dict:
    return {
        "kpi_references": {
            "auc": "Probabilité qu'un défaut soit classé plus risqué qu'un non-défaut.",
            "gini": "Gini = 2 x AUC - 1 ; mesure de discrimination.",
            "ks": "Distance maximale entre CDF défauts et non-défauts.",
            "brier_score": "Erreur quadratique moyenne entre défaut observé et PD.",
            "psi": "Population Stability Index entre référence et période courante.",
            "traffic_light": "Test de calibration par grade avec quantiles de Vasicek corrélés.",
            "wilson_interval": "Intervalle de confiance de proportion robuste pour petits échantillons.",
            "hosmer_lemeshow": "Lecture globale complémentaire de calibration par classes.",
        },
        "process_references": {
            "horizon_independence_gate": "La période de backtesting ne doit pas recouvrir la période de développement/entraînement.",
            "horizon_exploitability_gate": "L'horizon doit contenir assez de crédits et de notations observées exploitables.",
            "decision": "La décision est déterministe, pilotée par la politique active et traçable.",
            "recalibration": "Le recalibrage est une proposition versionnée, jamais une activation automatique.",
        },
    }


def resolve_policy(record: dict | None) -> dict:
    if not record:
        return default_policy()
    policy = deepcopy(record)
    thresholds = policy.setdefault("thresholds", {})
    defaults = default_policy()["thresholds"]
    for key, value in defaults.items():
        thresholds.setdefault(key, value)
    baseline = {item["key"]: item for item in default_policy()["justifications"]}
    existing = {item.get("key"): item for item in policy.setdefault("justifications", [])}
    existing.update({key: item for key, item in baseline.items() if key not in existing})
    policy["justifications"] = list(existing.values())
    return policy
