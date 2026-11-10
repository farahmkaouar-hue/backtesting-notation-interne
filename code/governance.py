"""Politique de backtesting : unique source des seuils et paramètres de décision.

Aucun seuil n'est écrit ailleurs dans le code : le moteur, les rapports et
l'interface lisent la politique active. L'administrateur la modifie depuis
l'écran « Politique et seuils » ; chaque modification crée une nouvelle version,
justifiée et tracée, et chaque analyse archive la version appliquée.
"""
from copy import deepcopy

import pandas as pd
from datetime import datetime, timezone

POLICY_VERSION = "BANK_POLICY_2026_10"

# Catalogue des paramètres réglables : libellé, groupe, bornes et explication.
PARAMETERS = [
    # --- Définition du défaut ---------------------------------------------
    {"key": "default_pd_threshold_percent", "group": "Définition du défaut", "label": "PD à partir de laquelle une note vaut défaut (%)",
     "default": 100.0, "min": 1, "max": 100, "step": 0.01,
     "help": "La note de défaut est la première note de l'échelle dont la PD atteint ce seuil (100 % par défaut). "
             "Ignoré si une note de défaut explicite est fixée ci-dessous."},
    # --- Horizon du backtesting --------------------------------------------
    {"key": "default_horizon_months", "group": "Horizon du backtesting", "label": "Horizon proposé par défaut (mois)",
     "default": 12, "min": 1, "max": 60, "step": 1, "integer": True,
     "help": "Durée d'observation du défaut proposée à l'analyste (modifiable à chaque backtesting : 6, 12, 24 mois…). "
             "La PD annuelle est convertie à l'horizon choisi : PD(H) = 1 − (1 − PD)^(H/12)."},
    {"key": "horizon_tolerance_months", "group": "Horizon du backtesting", "label": "Tolérance sur l'horizon (mois)",
     "default": 3, "min": 0, "max": 24, "step": 1, "integer": True,
     "help": "Sans date de défaut, seules les notes observées pendant l'horizon ± cette tolérance sont retenues, "
             "chacune comparée à sa PD convertie à sa durée réelle d'observation."},
    # --- Volumes minimaux -------------------------------------------------
    {"key": "minimum_defaults_for_decision", "group": "Volumes minimaux", "label": "Défauts minimum pour conclure",
     "default": 20, "min": 1, "max": 10000, "step": 1, "integer": True,
     "help": "En deçà, la décision est « non concluant » : les indicateurs sont trop instables."},
    {"key": "minimum_exploitable_rows", "group": "Volumes minimaux", "label": "Clients minimum sur la période testée",
     "default": 120, "min": 1, "max": 10_000_000, "step": 1, "integer": True, "help": "Volume minimal pour lancer un backtesting."},
    {"key": "minimum_unique_clients", "group": "Volumes minimaux", "label": "Clients distincts minimum",
     "default": 100, "min": 1, "max": 10_000_000, "step": 1, "integer": True, "help": "Évite une conclusion fondée sur quelques clients."},
    {"key": "minimum_exposures_per_grade", "group": "Volumes minimaux", "label": "Clients minimum par note pour un feu",
     "default": 20, "min": 1, "max": 100000, "step": 1, "integer": True,
     "help": "Une note moins peuplée est « non concluante » : pas de feu vert, orange ou rouge."},
    # --- Discrimination ---------------------------------------------------
    {"key": "gini_minimum", "group": "Discrimination", "label": "Gini minimal", "default": 0.40, "min": 0, "max": 1, "step": 0.01,
     "help": "En dessous : alerte (surveillance renforcée). Une refonte n'est proposée que si les conditions du groupe "
             "« Refonte du modèle » sont toutes réunies. Un seuil propre à chaque modèle peut être fixé dans le référentiel."},
    {"key": "ks_minimum", "group": "Discrimination", "label": "KS minimal", "default": 0.20, "min": 0, "max": 1, "step": 0.01,
     "help": "En dessous : alerte sur la séparation entre clients sains et en défaut."},
    # --- Refonte du modèle : conditions cumulatives -------------------------
    {"key": "minimum_defaults_for_redevelopment", "group": "Refonte du modèle", "label": "Défauts minimum pour proposer une refonte",
     "default": 50, "min": 1, "max": 100000, "step": 1, "integer": True,
     "help": "Une refonte n'est proposée que si le Gini est mesuré sur au moins ce nombre de défauts."},
    {"key": "gini_max_relative_drop", "group": "Refonte du modèle", "label": "Baisse maximale du Gini depuis le développement",
     "default": 0.20, "min": 0, "max": 1, "step": 0.01,
     "help": "Ex. 0,20 : alerte si le Gini a perdu plus de 20 % par rapport au Gini de développement (référentiel des modèles)."},
    {"key": "redevelopment_confirmations", "group": "Refonte du modèle", "label": "Exercices consécutifs confirmant l'insuffisance",
     "default": 2, "min": 1, "max": 5, "step": 1, "integer": True,
     "help": "La refonte n'est proposée que si le Gini est significativement insuffisant sur ce nombre d'exercices "
             "consécutifs (l'exercice analysé compris). Sinon : surveillance, refonte à confirmer."},
    # --- Structure de l'échelle (circulaire BCT n°2016-06, art. 4 et 5) ------
    {"key": "minimum_non_default_grades", "group": "Structure de l'échelle", "label": "Nombre minimal de notes saines",
     "default": 7, "min": 1, "max": 30, "step": 1, "integer": True,
     "help": "L'échelle doit compter au moins ce nombre de notes pour les contreparties saines, plus une note de défaut."},
    {"key": "max_grade_concentration", "group": "Structure de l'échelle", "label": "Part maximale des clients sur une note",
     "default": 0.30, "min": 0.05, "max": 1, "step": 0.01,
     "help": "Au-delà, la concentration sur une note est signalée : elle doit être justifiée par des preuves empiriques."},
    {"key": "review_frequency_months", "group": "Structure de l'échelle", "label": "Délai maximal entre deux backtestings (mois)",
     "default": 12, "min": 1, "max": 36, "step": 1, "integer": True,
     "help": "Un modèle dont le dernier backtesting est plus ancien est signalé « revue en retard » au tableau de bord."},
    # --- Qualité des données ------------------------------------------------
    {"key": "max_exclusion_rate", "group": "Qualité des données", "label": "Taux maximal de lignes écartées à l'import",
     "default": 0.30, "min": 0, "max": 1, "step": 0.01,
     "help": "Au-delà, la décision signale une alerte sur la qualité des données."},
    # --- Calibration ------------------------------------------------------
    {"key": "traffic_light_orange_pvalue", "group": "Calibration (feux)", "label": "Seuil orange — test binomial (p-valeur)",
     "default": 0.05, "min": 0.0001, "max": 0.5, "step": 0.001,
     "help": "Orange si la probabilité d'observer autant de défauts avec la PD annoncée est inférieure à ce seuil."},
    {"key": "traffic_light_red_pvalue", "group": "Calibration (feux)", "label": "Seuil rouge — test corrélé (p-valeur)",
     "default": 0.01, "min": 0.00001, "max": 0.5, "step": 0.0001,
     "help": "Rouge si, même en admettant une année défavorable, la probabilité est inférieure à ce seuil."},
    {"key": "asset_correlation", "group": "Calibration (feux)", "label": "Corrélation des défauts (ρ)",
     "default": 0.12, "min": 0, "max": 0.5, "step": 0.01,
     "help": "Effet d'une année défavorable sur tous les clients (modèle de Vasicek). 0 = test rouge sans corrélation (plus strict)."},
    # --- Stabilité et jugement expert --------------------------------------
    {"key": "psi_warning", "group": "Stabilité et dérogations", "label": "PSI — seuil d'alerte", "default": 0.10, "min": 0, "max": 2, "step": 0.01,
     "help": "Évolution modérée de la population."},
    {"key": "psi_critical", "group": "Stabilité et dérogations", "label": "PSI — seuil critique", "default": 0.25, "min": 0, "max": 2, "step": 0.01,
     "help": "Forte dérive de la population : revue du périmètre."},
    {"key": "override_rate_critical", "group": "Stabilité et dérogations", "label": "Taux de dérogation maximal", "default": 0.20, "min": 0, "max": 1, "step": 0.01,
     "help": "Au-delà : alerte sur le jugement expert."},
    # --- Recalibrage ------------------------------------------------------
    {"key": "minimum_defaults_for_bayesian", "group": "Recalibrage", "label": "Défauts minimum pour proposer un recalibrage",
     "default": 5, "min": 1, "max": 10000, "step": 1, "integer": True, "help": "En deçà, la proposition est bloquée."},
    {"key": "minimum_defaults_for_logistic", "group": "Recalibrage", "label": "Défauts minimum pour le recalibrage logistique",
     "default": 20, "min": 1, "max": 10000, "step": 1, "integer": True, "help": "En deçà, le choix automatique retient la méthode bayésienne."},
    {"key": "bayesian_prior_strength", "group": "Recalibrage", "label": "Poids de la PD actuelle (méthode bayésienne)",
     "default": 20, "min": 0, "max": 100000, "step": 1, "help": "Nombre de « clients fictifs » représentant la PD actuelle."},
    {"key": "pd_floor_percent", "group": "Recalibrage", "label": "Plancher de PD (%)", "default": 0.03, "min": 0, "max": 5, "step": 0.01,
     "help": "Aucune PD proposée ne peut être inférieure à ce plancher."},
    {"key": "moc_confidence", "group": "Recalibrage", "label": "Niveau de la marge de prudence", "default": 0.90, "min": 0.5, "max": 0.999, "step": 0.01,
     "help": "Le niveau de défaut cible est la borne haute de son intervalle de confiance à ce niveau."},
    {"key": "bootstrap_iterations", "group": "Recalibrage", "label": "Tirages bootstrap (intervalle du Gini)",
     "default": 1000, "min": 200, "max": 10000, "step": 100, "integer": True, "help": "Plus de tirages = intervalle plus précis mais calcul plus long."},
]
# Fondement de chaque paramètre : réglementaire, scientifique ou choix métier.
BASIS = {
    "default_pd_threshold_percent": "Réglementaire — BCT 2016-06 art. 4 b (une note dédiée aux contreparties en défaut, PD = 100 %).",
    "default_horizon_months": "Réglementaire — BCT 2016-06 art. 7 : la PD est estimée sur un horizon d'un an.",
    "horizon_tolerance_months": "Métier — fenêtre d'observation admise autour de l'horizon ; chaque note reste comparée à sa PD convertie à sa durée réelle.",
    "minimum_defaults_for_decision": "Scientifique — en deçà de 20 défauts, les tests ont une puissance très faible (BCBS WP14, portefeuilles à faible défaut).",
    "minimum_exploitable_rows": "Métier — volume minimal d'une campagne exploitable.",
    "minimum_unique_clients": "Métier — évite une conclusion fondée sur quelques clients.",
    "minimum_exposures_per_grade": "Scientifique — règle usuelle de validité des approximations (N·PD et effectifs suffisants par classe).",
    "gini_minimum": "Métier — usage de place (aucun seuil réglementaire) ; à valider par le comité, éventuellement par modèle.",
    "ks_minimum": "Métier — usage de place ; indicateur complémentaire du Gini.",
    "minimum_defaults_for_redevelopment": "Métier et scientifique — une décision lourde exige un Gini mesuré avec précision.",
    "gini_max_relative_drop": "Métier — matérialité de la dégradation par rapport au développement.",
    "redevelopment_confirmations": "Métier — confirmation sur plusieurs exercices avant une décision irréversible.",
    "minimum_non_default_grades": "Réglementaire — BCT 2016-06 art. 4 b : au moins sept notes saines et une note de défaut.",
    "max_grade_concentration": "Réglementaire — BCT 2016-06 art. 4 d et e : concentration excessive à éviter ou à justifier ; seuil métier.",
    "review_frequency_months": "Réglementaire — BCT 2016-06 art. 5 d et 14 : revue au moins annuelle de la capacité de prévision.",
    "max_exclusion_rate": "Réglementaire — BCT 2016-06 art. 8 b (fiabilité et exhaustivité des données) ; seuil métier.",
    "traffic_light_orange_pvalue": "Scientifique — niveau de test usuel de 5 % (approche par feux de Tasche, BCBS WP14).",
    "traffic_light_red_pvalue": "Scientifique — niveau de 1 % sous corrélation : écart non explicable par la conjoncture.",
    "asset_correlation": "Scientifique — borne basse de la corrélation bâloise des entreprises (12 % à 24 %), la plus prudente pour le feu rouge.",
    "psi_warning": "Métier — convention de place (Siddiqi, 2006).",
    "psi_critical": "Métier — convention de place (Siddiqi, 2006).",
    "override_rate_critical": "Réglementaire — BCT 2016-06 art. 8 e et f (articulation modèle / jugement expert) ; seuil métier.",
    "minimum_defaults_for_bayesian": "Métier — en deçà, aucune estimation n'est fiable.",
    "minimum_defaults_for_logistic": "Scientifique — environ 10 événements par paramètre estimé (Peduzzi et al., 1996) : 2 paramètres, 20 défauts.",
    "bayesian_prior_strength": "Scientifique — poids de l'a priori dans le modèle bêta-binomial ; valeur métier.",
    "pd_floor_percent": "Réglementaire — plancher bâlois de PD de 0,03 % (Bâle II ; 0,05 % sous Bâle III finalisé).",
    "moc_confidence": "Réglementaire — marge de prudence EBA/GL/2017/16, catégorie C (erreur d'estimation) ; niveau métier.",
    "bootstrap_iterations": "Scientifique — au moins 1 000 tirages pour un intervalle par percentiles (Efron et Tibshirani, 1993).",
}
for _parameter in PARAMETERS:
    _parameter["basis"] = BASIS[_parameter["key"]]
PARAMETER_BY_KEY = {p["key"]: p for p in PARAMETERS}


def default_policy() -> dict:
    return {
        "version": POLICY_VERSION,
        "name": "Politique interne de backtesting et de recalibrage",
        "status": "active",
        "thresholds": {p["key"]: p["default"] for p in PARAMETERS},
        # Note de défaut explicite (ex. « 12 », « D ») ; vide = déduite du seuil de PD ci-dessus.
        "default_grade": "",
        # Corrélation propre à un modèle, si la gouvernance la fixe (sinon valeur générale).
        "asset_correlation_by_model": {},
        # Référentiel des modèles : période de développement et Gini mesuré au développement.
        # Repris automatiquement au backtesting (l'analyste ne les ressaisit pas).
        "models": {},
        "comment": "Politique initiale.",
    }


def resolve_policy(record: dict | None) -> dict:
    """Complète une politique stockée avec les paramètres ajoutés depuis sa création."""
    base = default_policy()
    if not record:
        return base
    policy = deepcopy(record)
    thresholds = policy.setdefault("thresholds", {})
    for key, value in base["thresholds"].items():
        thresholds.setdefault(key, value)
    policy.setdefault("default_grade", "")
    policy.setdefault("asset_correlation_by_model", {})
    policy.setdefault("models", {})
    return policy


def build_new_version(current: dict, changes: dict, actor: str) -> dict:
    """Valide une modification et renvoie la nouvelle version de la politique (erreurs en clair)."""
    comment = (changes.get("comment") or "").strip()
    if len(comment) < 5:
        raise ValueError("Indiquez le motif de la modification (exigence métier, décision du comité…).")
    policy = resolve_policy(current)
    errors = []
    for key, raw in (changes.get("thresholds") or {}).items():
        spec = PARAMETER_BY_KEY.get(key)
        if not spec:
            errors.append(f"Paramètre inconnu : {key}.")
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError):
            errors.append(f"« {spec['label']} » : valeur numérique attendue.")
            continue
        if not spec["min"] <= value <= spec["max"]:
            errors.append(f"« {spec['label']} » doit être compris entre {spec['min']} et {spec['max']}.")
            continue
        policy["thresholds"][key] = int(round(value)) if spec.get("integer") else value
    t = policy["thresholds"]
    if t["traffic_light_red_pvalue"] > t["traffic_light_orange_pvalue"]:
        errors.append("Le seuil rouge doit être inférieur ou égal au seuil orange (le rouge est plus sévère).")
    if t["psi_warning"] > t["psi_critical"]:
        errors.append("Le seuil d'alerte du PSI doit être inférieur au seuil critique.")
    if t["minimum_defaults_for_bayesian"] > t["minimum_defaults_for_logistic"]:
        errors.append("Le minimum de défauts pour le logistique doit être au moins celui du bayésien.")
    if "default_grade" in changes:
        policy["default_grade"] = str(changes.get("default_grade") or "").strip()
    if "asset_correlation_by_model" in changes:
        by_model = {}
        for model, raw in (changes.get("asset_correlation_by_model") or {}).items():
            try:
                value = float(raw)
            except (TypeError, ValueError):
                errors.append(f"Corrélation du modèle « {model} » : valeur numérique attendue.")
                continue
            if not 0 <= value <= 0.5:
                errors.append(f"Corrélation du modèle « {model} » : entre 0 et 0,5.")
            by_model[str(model).strip()] = value
        policy["asset_correlation_by_model"] = by_model
    if "models" in changes:
        registry = {}
        for name, entry in (changes.get("models") or {}).items():
            name = str(name).strip()
            if not name:
                continue
            entry = entry or {}
            start = pd.to_datetime(entry.get("development_start") or None, errors="coerce")
            end = pd.to_datetime(entry.get("development_end") or None, errors="coerce")
            if pd.isna(start) or pd.isna(end) or start > end:
                errors.append(f"Modèle « {name} » : période de développement invalide.")
                continue
            values = {}
            for key, label in (("development_gini", "Gini de développement"), ("gini_minimum", "Gini minimal")):
                raw = entry.get(key)
                if raw in (None, ""):
                    values[key] = None
                    continue
                try:
                    values[key] = float(raw)
                except (TypeError, ValueError):
                    values[key] = -1.0
                if not 0 < values[key] <= 1:
                    errors.append(f"Modèle « {name} » : {label} entre 0 et 1.")
            registry[name] = {"development_start": str(start.date()), "development_end": str(end.date()), **values}
        policy["models"] = registry
    if errors:
        raise ValueError(" ".join(errors))
    stamp = datetime.now(timezone.utc)
    policy["version"] = f"POLICY_{stamp:%Y%m%d_%H%M%S}_{stamp.microsecond // 1000:03d}"
    policy["comment"] = comment
    policy["previous_version"] = current.get("version") if current else None
    policy["updated_by"] = actor
    return policy


def policy_for_model(policy: dict, model: str) -> dict:
    """Politique appliquée à un modèle : seuils propres au modèle (référentiel) prioritaires."""
    entry = (policy.get("models") or {}).get(model) or {}
    resolved = deepcopy(policy)
    if entry.get("gini_minimum") is not None:
        resolved["thresholds"]["gini_minimum"] = float(entry["gini_minimum"])
    return resolved


def correlation_for(policy: dict, model: str) -> float:
    by_model = policy.get("asset_correlation_by_model") or {}
    return float(by_model.get(model, policy["thresholds"]["asset_correlation"]))


def preparation_options(policy: dict) -> dict:
    """Paramètres de la politique qui influent sur la préparation des données."""
    t = policy["thresholds"]
    return {"default_grade": policy.get("default_grade") or None,
            "default_pd_threshold_percent": float(t["default_pd_threshold_percent"])}


def preparation_signature(policy: dict, preparation_version: int) -> str:
    """Change dès que le code ou un paramètre de préparation change : les partitions sont alors reconstruites."""
    o = preparation_options(policy)
    return f"{preparation_version}|{o['default_grade'] or ''}|{o['default_pd_threshold_percent']}"
