import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))
from app.services.assistant import answer_question

def test_explains_kpi_and_recommendation():
    first = answer_question("Que signifie le Gini ?", context={"policy_version": "BANK_POLICY_2026_08"})
    assert "Gini" in first["answer"]
    assert any(ref["type"] == "policy_version" for ref in first["references"])
    result = {"decision": {"action": "extend_history"}}
    second = answer_question("Quelle solution de recalibrage ?", result, context={"run_id": "run_1"})
    assert "historique" in second["answer"]
    assert any(ref["type"] == "run_id" for ref in second["references"])
