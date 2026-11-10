import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))
import pandas as pd
import pytest
from app.services.preparation import prepare
from app.services.backtesting import run_backtest
from app.services.metrics import hosmer_lemeshow_by_grade
from app.services.governance import default_policy
from app.services.workflow import execute_backtesting_workflow, recommend_horizon

def test_prepare_and_backtest():
    raw = pd.DataFrame({
        "Number": ["1", "2", "3", "4"], "Counterparty": [1,2,3,4],
        "Created Date": ["2026-01-01"]*4, "Last Modified Date": ["2026-01-02"]*4,
        "Model Scoring Name": ["PRO"]*4, "Process": ["Approved"]*4,
        "Final Rating Class": [1,2,3,4], "Final Pd Class": [1.,5.,10.,30.],
        "Rating_réel 072026": ["1", "2", "11", "12"],
    })
    prepared, report = prepare(raw, "2026-07-31")
    assert report["eligible"] == 4
    assert int(prepared.defaut_observe.sum()) == 2
    result = run_backtest(prepared, "Final Rating Class", "Final Pd Class", "defaut_observe", .12)
    assert result["population"] == 4 and result["auc"] is not None


def test_preparation_detects_new_actual_rating_column_and_optional_process():
    raw = pd.DataFrame({
        "Number": ["1", "2"], "Counterparty": [1, 2], "Created Date": ["2026-01-01"] * 2,
        "Model Scoring Name": ["PRO"] * 2, "Final Rating Class": [1, 2], "Final Pd Class": [.01, .10],
        "Rating_réel 082026": ["2", "12"],
    })
    prepared, report = prepare(raw, actual_rating_column="Rating_réel 082026", default_thresholds={"Professionnel": 12})
    assert report["actual_rating_column"] == "Rating_réel 082026"
    assert int(prepared["defaut_observe"].sum()) == 1
    result = run_backtest(prepared, "Final Rating Class", "Final Pd Class", "defaut_observe", .12)
    assert result["pd_scale"] == "decimal_auto"


def test_hosmer_lemeshow_uses_heterogeneous_bernoulli_variance():
    data = pd.DataFrame({"grade": [1, 1], "pd": [.01, .50], "default": [0, 1]})
    result = hosmer_lemeshow_by_grade(data, "grade", "pd", "default")
    expected_variance = .01 * .99 + .50 * .50
    assert result["statistic"] == pytest.approx((1 - .51) ** 2 / expected_variance)


def test_horizon_overlap_is_blocked():
    raw = pd.DataFrame({
        "Number": [str(i) for i in range(1, 141)],
        "Counterparty": [i for i in range(1, 141)],
        "Created Date": ["2025-04-01"] * 140,
        "Last Modified Date": ["2025-04-02"] * 140,
        "Model Scoring Name": ["PRO"] * 140,
        "Process": ["Approved"] * 140,
        "Final Rating Class": [1 + (i % 7) for i in range(140)],
        "Final Pd Class": [1.0 + (i % 10) for i in range(140)],
        "Rating_réel 072026": ["12" if i % 3 == 0 else "2" for i in range(140)],
    })
    prepared, _ = prepare(raw, "2026-07-31")
    policy = default_policy()
    with pytest.raises(ValueError):
        execute_backtesting_workflow(
            prepared,
            "Professionnel",
            0.12,
            None,
            policy,
            {
                "development_start": "2025-01-01",
                "development_end": "2025-12-31",
                "backtest_start": "2025-07-01",
                "backtest_end": "2026-06-30",
            },
        )


def test_horizon_exploitability_gate():
    raw = pd.DataFrame({
        "Number": [str(i) for i in range(1, 41)],
        "Counterparty": [i for i in range(1, 41)],
        "Created Date": ["2026-01-01"] * 40,
        "Last Modified Date": ["2026-01-02"] * 40,
        "Model Scoring Name": ["PRO"] * 40,
        "Process": ["Approved"] * 40,
        "Final Rating Class": [1 + (i % 5) for i in range(40)],
        "Final Pd Class": [1.0 + (i % 8) for i in range(40)],
        "Rating_réel 072026": ["12" if i % 4 == 0 else "2" for i in range(40)],
    })
    prepared, _ = prepare(raw, "2026-07-31")
    with pytest.raises(ValueError):
        execute_backtesting_workflow(
            prepared,
            "Professionnel",
            0.12,
            None,
            default_policy(),
            {
                "development_start": "2024-01-01",
                "development_end": "2024-12-31",
                "backtest_start": "2026-01-01",
                "backtest_end": "2026-06-30",
            },
        )


def test_recommended_horizon_uses_recent_exploitable_window():
    rows = 220
    raw = pd.DataFrame({
        "Number": [str(i) for i in range(1, rows + 1)],
        "Counterparty": [i for i in range(1, rows + 1)],
        "Created Date": pd.date_range("2026-01-01", periods=rows, freq="D").astype(str),
        "Last Modified Date": pd.date_range("2026-01-02", periods=rows, freq="D").astype(str),
        "Model Scoring Name": ["PRO"] * rows,
        "Process": ["Approved"] * rows,
        "Final Rating Class": [1 + (i % 8) for i in range(rows)],
        "Final Pd Class": [1.0 + (i % 12) for i in range(rows)],
        "Rating_réel 072026": ["12" if i % 5 == 0 else "2" for i in range(rows)],
    })
    prepared, _ = prepare(raw, "2026-12-31")
    population = prepared[(prepared["modele_cible"] == "Professionnel") & (prepared["eligible_backtesting"] == 1)]
    rec = recommend_horizon(population, "2024-01-01", "2024-12-31", default_policy()["thresholds"], preferred_months=12)
    assert rec["status"] == "recommended"
    assert rec["rows"] >= default_policy()["thresholds"]["minimum_exploitable_rows"]
