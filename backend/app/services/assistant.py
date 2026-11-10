"""Assistant explicatif gouverné.

Il explique les KPI et reformule les recommandations du moteur déterministe.
Il ne modifie ni données, ni seuils, ni mapping PD, ni décision de validation.
"""

KPI = {
    "gini": "Le Gini mesure le pouvoir de classement du modèle : plus il est élevé, mieux les défauts sont classés parmi les risques élevés. Il ne prouve pas que les PD sont bien calibrées.",
    "auc": "L'AUC est la probabilité qu'un défaut reçoive un risque supérieur à un non-défaut. Le Gini est égal à 2 × AUC − 1.",
    "ks": "Le KS est l'écart maximal entre les distributions cumulées des défauts et non-défauts. Il complète le Gini en identifiant une séparation opérationnelle.",
    "psi": "Le PSI mesure le changement de structure entre une population de référence et la population actuelle. Au-delà de 0,25, une revue du périmètre est requise.",
    "brier": "Le Brier score mesure l'écart quadratique moyen entre PD et défaut observé. Plus il est faible, meilleure est la calibration probabiliste.",
    "override": "Les overrides comparent la note fondamentale à la note finale. Une fréquence élevée ou orientée dans un seul sens peut signaler un facteur de risque absent du score.",
    "traffic": "Le traffic-light compare le taux de défaut observé à la PD par grade en tenant compte de la corrélation des défauts. Vert : conforme ; orange : revue ; rouge : action prioritaire.",
}

KPI_REFERENCES = {
    "gini": "Catalogue méthodologique interne — discrimination : AUC/Gini/KS.",
    "auc": "Catalogue méthodologique interne — discrimination : AUC/Gini/KS.",
    "ks": "Catalogue méthodologique interne — discrimination : AUC/Gini/KS.",
    "psi": "Catalogue méthodologique interne — stabilité : PSI et migrations.",
    "brier": "Catalogue méthodologique interne — calibration : Brier score et traffic-light Vasicek.",
    "override": "Catalogue méthodologique interne — comparaison Fundamental versus Final.",
    "traffic": "Catalogue méthodologique interne — calibration par grade : traffic-light Vasicek.",
}

def _kpi_answer(question: str):
    q = question.lower()
    for key, answer in KPI.items():
        if key in q or (key == "traffic" and ("feu" in q or "orange" in q or "rouge" in q)):
            return answer
    return None

def _recommendation(result: dict) -> str:
    action = result.get("decision", {}).get("action")
    actions = {
        "extend_history": "La priorité est d'agréger des cohortes historiques complètes. Le recalibrage est bloqué car l'échantillon de défauts ne permet pas une estimation fiable.",
        "pd_recalibration": "Le classement semble exploitable mais la calibration appelle une proposition de mapping PD, suivie d'une validation out-of-time indépendante.",
        "model_redevelopment": "Le problème concerne le pouvoir discriminant. Il faut analyser les variables, la segmentation et les coefficients avant tout recalibrage de PD.",
        "scope_review": "La population a dérivé. Vérifier la représentativité, la politique d'octroi et la nécessité d'une segmentation avant de recalibrer.",
        "override_review": "Examiner les motifs d'override et les facteurs récurrents ; ils peuvent indiquer une faiblesse structurelle du score fondamental.",
        "no_action": "Aucune action automatique n'est proposée. Le résultat reste soumis à la revue et à l'approbation du superviseur.",
    }
    return actions.get(action, "Aucun résultat de décision exploitable n'est attaché à cette question.")

def answer_question(question: str, run_result: dict | None = None, context: dict | None = None) -> dict:
    """Return an auditable answer based on KPI semantics and a selected run."""
    explanation = _kpi_answer(question)
    q = question.lower()
    if any(word in q for word in ["recalibr", "solution", "recommand", "problème", "probleme"]):
        answer, topic = _recommendation(run_result or {}), "recommendation"
    elif explanation:
        answer, topic = explanation, "kpi_explanation"
    elif run_result:
        answer, topic = "Le résultat associé doit être lu par étapes : discrimination, calibration, stabilité puis overrides. " + _recommendation(run_result), "run_summary"
    else:
        answer, topic = "Je peux expliquer les KPI, les alertes et le processus de recalibrage. Sélectionnez une exécution pour une explication contextualisée.", "general_guidance"
    context = context or {}
    references = [
        {"type": "kpi_catalog", "value": "Référentiel KPI interne RiskLens v1"},
        {"type": "methodology", "value": "Séparation discrimination/calibration/stabilité/overrides"},
    ]
    for key, reference in KPI_REFERENCES.items():
        if key in q or (key == "traffic" and ("feu" in q or "orange" in q or "rouge" in q)):
            references.append({"type": "kpi_reference", "value": reference})
    if context.get("policy_version"):
        references.append({"type": "policy_version", "value": context["policy_version"]})
    if context.get("run_id"):
        references.append({"type": "run_id", "value": context["run_id"]})
    if context.get("model"):
        references.append({"type": "model", "value": context["model"]})

    return {"topic": topic, "answer": answer,
            "guardrail": "Assistant explicatif uniquement : il ne modifie pas les données, les seuils, les PD ou la décision finale.",
            "method_basis": "Référentiel méthodologique : séparation discrimination, calibration, stabilité et overrides.",
            "references": references}
