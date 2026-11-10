from io import BytesIO
import json
import pandas as pd
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from . import storage
from .auth import _secret, current_user, login, require
from .schemas import AccountApprovalRequest, BacktestRequest, ChatRequest, HorizonRecommendationRequest, LoginRequest, RecalibrationRequest, RegistrationRequest, RevalidationRequest, Role
from .services.preparation import prepare
from .services.backtesting import decision, run_backtest
from .services.recalibration import propose
from .services.simulation import simulate_from_population
from .services.governance import methodology_catalog, resolve_policy
from .services.workflow import execute_backtesting_workflow, recalibration_workflow, recommend_horizon, revalidate
from .services.assistant import answer_question

app = FastAPI(title="Backtesting des modèles internes", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8443", "http://127.0.0.1:8443"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

@app.on_event("startup")
def startup():
    _secret()
    storage.init_db()


def active_policy() -> dict:
    return resolve_policy(storage.get_active_policy())

def load_prepared(dataset_id: str):
    record = storage.dataset(dataset_id)
    if not record: raise HTTPException(404, "Jeu de données introuvable")
    metadata = json.loads(record["metadata"])
    partitioned = storage.load_all_model_partitions(dataset_id)
    if not partitioned.empty:
        return partitioned, metadata
    try:
        raw = pd.read_excel(record["path"], sheet_name=0, dtype=object)
        return prepare(
            raw, metadata.get("performance_date"), metadata.get("actual_rating_column"),
            metadata.get("default_thresholds"),
        )
    except Exception as error:
        raise HTTPException(422, f"Import/préparation impossible : {error}")


def load_model_population(dataset_id: str, model: str, eligible_only=True) -> pd.DataFrame:
    frame = storage.load_model_partition(dataset_id, model)
    if frame.empty:
        prepared, _ = load_prepared(dataset_id)
        storage.save_model_partitions(dataset_id, prepared, "system")
        frame = storage.load_model_partition(dataset_id, model)
    if frame.empty:
        raise HTTPException(422, "Aucune population disponible pour ce modèle.")
    if eligible_only and "eligible_backtesting" in frame:
        frame = frame[frame["eligible_backtesting"] == 1]
    return frame

def ensure_real_dataset(dataset_id: str):
    record = storage.dataset(dataset_id)
    if record and json.loads(record["metadata"]).get("synthetic_only"):
        raise HTTPException(422, "Les données synthétiques sont réservées aux tests techniques et ne peuvent pas alimenter un backtesting ou un recalibrage.")

@app.get("/health")
def health(): return {"status": "ok"}

@app.get("/", include_in_schema=False)
def api_root():
    """The React application is deployed separately from the governed API."""
    return {"service": "API de backtesting des modèles internes", "documentation": "/docs", "health": "/health"}

@app.post("/auth/login")
def authenticate(request: LoginRequest):
    return {"access_token": login(request.username, request.password), "token_type": "bearer"}

@app.post("/auth/register", status_code=201)
def register(request: RegistrationRequest):
    try:
        storage.create_registration(request.username.lower(), request.full_name.strip(), request.email.lower().strip(), request.password)
    except ValueError as error:
        raise HTTPException(409, str(error))
    return {"message": "Demande de compte enregistrée. Un administrateur doit la valider avant la première connexion."}

@app.get("/admin/accounts/pending")
def pending_accounts(user=Depends(require(Role.admin))):
    return storage.pending_accounts()

@app.post("/admin/accounts/approve")
def approve_account(request: AccountApprovalRequest, user=Depends(require(Role.admin))):
    if not storage.approve_account(request.username, request.role.value, user["sub"]):
        raise HTTPException(404, "Compte en attente introuvable.")
    return {"message": "Compte validé."}

@app.post("/assistant/chat")
def assistant_chat(request: ChatRequest, user=Depends(current_user)):
    """Governed assistant: explains documented results but cannot take actions."""
    run_result = None
    if request.run_id:
        run = storage.get_run(request.run_id)
        if not run:
            raise HTTPException(404, "Exécution introuvable")
        run_result = json.loads(run["result"])
    response = answer_question(
        request.question,
        run_result,
        {
            "policy_version": active_policy().get("version"),
            "run_id": request.run_id,
            "model": request.model,
        },
    )
    storage.save_chat(user["sub"], request.run_id, request.question, response["answer"])
    return response

@app.post("/datasets")
async def upload_dataset(
    file: UploadFile = File(...),
    performance_date: str | None = Form(None),
    actual_rating_column: str | None = Form(None),
    user=Depends(require(Role.analyst, Role.supervisor, Role.admin)),
):
    if not file.filename.lower().endswith((".xlsx", ".xls")): raise HTTPException(415, "Fichier Excel attendu")
    content = await file.read()
    try:
        raw = pd.read_excel(BytesIO(content), sheet_name=0, dtype=object)
        default_thresholds = active_policy().get("thresholds", {}).get("default_rating_thresholds", {})
        prepared, report = prepare(raw, performance_date, actual_rating_column, default_thresholds)
    except Exception as error:
        raise HTTPException(422, f"Structure invalide : {error}")
    dataset_id = storage.save_dataset(file.filename, content, user["sub"], {**report, "performance_date": performance_date})
    partitions = storage.save_model_partitions(dataset_id, prepared, user["sub"])
    return {"dataset_id": dataset_id, "preparation_report": report, "model_partitions": partitions}

@app.get("/datasets")
def datasets(user=Depends(current_user)):
    """Dataset catalogue for the UI; file contents are never sent to the browser."""
    with storage.connect() as db:
        records = db.execute(
            "SELECT id, filename, created_by, created_at, metadata FROM datasets ORDER BY created_at DESC"
        ).fetchall()
    return [dict(record) for record in records]

@app.get("/datasets/{dataset_id}/preparation")
def preparation_report(dataset_id: str, user=Depends(current_user)):
    _, report = load_prepared(dataset_id)
    return report

@app.get("/datasets/{dataset_id}/models")
def models(dataset_id: str, user=Depends(current_user)):
    partitions = storage.list_model_partitions(dataset_id)
    if not partitions:
        prepared, _ = load_prepared(dataset_id)
        storage.save_model_partitions(dataset_id, prepared, user["sub"])
        partitions = storage.list_model_partitions(dataset_id)
    models_payload = [
        {
            "modele_cible": row["model"],
            "rows": row["row_count"],
            "eligible": row["eligible_count"],
            "observed_ratings": row["observed_rating_count"],
            "defaults": row["default_count"],
            "sql_partition": row["db_path"],
        }
        for row in partitions
    ]
    return {"models": models_payload}


@app.get("/datasets/{dataset_id}/partitions")
def dataset_partitions(dataset_id: str, user=Depends(current_user)):
    partitions = storage.list_model_partitions(dataset_id)
    if not partitions:
        prepared, _ = load_prepared(dataset_id)
        storage.save_model_partitions(dataset_id, prepared, user["sub"])
        partitions = storage.list_model_partitions(dataset_id)
    return {"dataset_id": dataset_id, "partitions": partitions}

@app.post("/backtests")
def backtest(request: BacktestRequest, user=Depends(require(Role.analyst, Role.supervisor, Role.admin))):
    ensure_real_dataset(request.dataset_id)
    population = load_model_population(request.dataset_id, request.model, eligible_only=True)
    if population.empty: raise HTTPException(422, "Aucune ligne éligible pour ce modèle")
    result = run_backtest(population, request.rating_column, request.pd_column, request.default_column, request.asset_correlation)
    result["decision"] = decision(result, active_policy().get("thresholds", {}))
    result["policy_version"] = active_policy().get("version")
    run_id = storage.save_run(request.dataset_id, "backtest", request.model, request.model_dump(), result, user["sub"])
    return {"run_id": run_id, **result}

@app.post("/workflows/backtesting")
def backtesting_workflow(request: BacktestRequest, user=Depends(require(Role.analyst, Role.supervisor, Role.admin))):
    """Parcours complet et expliqué : Final/Fundamental, calibration, stabilité et overrides."""
    ensure_real_dataset(request.dataset_id)
    prepared = load_model_population(request.dataset_id, request.model, eligible_only=True)
    reference = None
    if request.reference_dataset_id:
        ensure_real_dataset(request.reference_dataset_id)
        reference = load_model_population(request.reference_dataset_id, request.model, eligible_only=True)
    policy = active_policy()
    correlation = float(policy.get("thresholds", {}).get("asset_correlation", request.asset_correlation))
    horizon = {
        "development_start": request.development_start,
        "development_end": request.development_end,
        "backtest_start": request.backtest_start,
        "backtest_end": request.backtest_end,
    }
    try:
        result = execute_backtesting_workflow(prepared, request.model, correlation, reference, policy, horizon)
    except ValueError as error:
        raise HTTPException(422, str(error))
    run_id = storage.save_run(request.dataset_id, "backtesting_workflow", request.model, request.model_dump(), result, user["sub"])
    return {"run_id": run_id, **result}

@app.post("/recalibrations")
def recalibration(request: RecalibrationRequest, user=Depends(require(Role.analyst, Role.supervisor, Role.admin))):
    ensure_real_dataset(request.dataset_id)
    population = load_model_population(request.dataset_id, request.model, eligible_only=True)
    if population.empty: raise HTTPException(422, "Aucune ligne éligible pour ce modèle")
    horizon = {
        "development_start": request.development_start,
        "development_end": request.development_end,
        "backtest_start": request.backtest_start,
        "backtest_end": request.backtest_end,
    }
    policy = active_policy()
    correlation = float(policy.get("thresholds", {}).get("asset_correlation", request.asset_correlation))
    try: result = recalibration_workflow(population, request.model, request.method, correlation, request.validation_fraction, policy, horizon)
    except ValueError as error: raise HTTPException(422, str(error))
    run_id = storage.save_run(request.dataset_id, "recalibration_proposal", request.model, request.model_dump(), result, user["sub"])
    return {"run_id": run_id, **result}

@app.post("/recalibrations/revalidate")
def revalidation(request: RevalidationRequest, user=Depends(require(Role.supervisor, Role.admin))):
    ensure_real_dataset(request.validation_dataset_id)
    proposal = storage.get_run(request.proposal_run_id)
    if not proposal or proposal["run_type"] != "recalibration_proposal": raise HTTPException(404, "Proposition de recalibrage introuvable")
    proposal_result = json.loads(proposal["result"])
    if not proposal_result.get("proposal"):
        raise HTTPException(422, "Cette exécution ne contient pas de proposition de recalibrage à valider.")
    validation = load_model_population(request.validation_dataset_id, request.model, eligible_only=True)
    policy = active_policy()
    correlation = float(policy.get("thresholds", {}).get("asset_correlation", request.asset_correlation))
    try:
        result = revalidate(
            validation, proposal_result["proposal"]["mapping"], request.model, correlation,
            proposal_result["proposal"].get("grade_column", "Final Rating Class"), policy,
        )
    except ValueError as error:
        raise HTTPException(422, str(error))
    run_id = storage.save_run(request.validation_dataset_id, "post_recalibration_validation", request.model, request.model_dump(), result, user["sub"])
    return {"run_id": run_id, **result}

@app.post("/admin/simulations")
def simulation(dataset_id: str, model: str, rows: int = 10000, seed: int = 42, user=Depends(require(Role.admin))):
    if rows < 1 or rows > 1_000_000: raise HTTPException(422, "Le volume doit être compris entre 1 et 1 000 000")
    population = load_model_population(dataset_id, model, eligible_only=False)
    if population.empty: raise HTTPException(422, "Population de référence vide")
    synthetic = simulate_from_population(population, rows, seed)
    buffer = BytesIO()
    synthetic.to_excel(buffer, index=False)
    synthetic_id = storage.save_dataset(
        f"synthetic_{model}_{rows}.xlsx", buffer.getvalue(), user["sub"],
        {"synthetic_only": True, "source_dataset_id": dataset_id, "model": model, "rows": rows, "seed": seed},
    )
    # Les données synthétiques sont marquées et isolées de toute décision de validation réelle.
    result = {"rows": len(synthetic), "model": model, "synthetic_only": True,
              "synthetic_dataset_id": synthetic_id, "columns": synthetic.columns.tolist()}
    run_id = storage.save_run(dataset_id, "simulation", model, {"rows": rows, "seed": seed}, result, user["sub"])
    return {"run_id": run_id, **result}

@app.post("/admin/simulations/demo-workflow")
def simulation_demo_workflow(dataset_id: str, model: str, rows: int = 10000, seed: int = 42, user=Depends(require(Role.admin))):
    """Test end-to-end de charge/UI : résultats explicitement non réglementaires."""
    source = load_model_population(dataset_id, model, eligible_only=True)
    if source.empty: raise HTTPException(422, "Population de référence vide")
    synthetic = simulate_from_population(source, rows, seed)
    policy = active_policy()
    correlation = float(policy.get("thresholds", {}).get("asset_correlation", .12))
    workflow = execute_backtesting_workflow(synthetic, model, correlation, policy=policy)
    proposal = recalibration_workflow(synthetic, model, "auto", correlation, policy=policy)
    result = {"synthetic_only": True, "not_for_model_validation": True, "backtesting": workflow, "recalibration": proposal}
    run_id = storage.save_run(dataset_id, "synthetic_demo_workflow", model, {"rows": rows, "seed": seed}, result, user["sub"])
    return {"run_id": run_id, **result}

@app.get("/runs")
def runs(user=Depends(require(Role.supervisor, Role.admin))):
    with storage.connect() as db:
        return [dict(row) for row in db.execute("SELECT * FROM runs ORDER BY created_at DESC").fetchall()]

@app.get("/runs/{run_id}")
def run_detail(run_id: str, user=Depends(current_user)):
    run = storage.get_run(run_id)
    if not run:
        raise HTTPException(404, "Exécution introuvable")
    return dict(run)


@app.get("/governance/policy")
def governance_policy(user=Depends(require(Role.supervisor, Role.admin))):
    return active_policy()


@app.get("/governance/methodology")
def governance_methodology(user=Depends(current_user)):
    return methodology_catalog()


@app.post("/workflows/horizon/recommend")
def recommend_backtesting_horizon(request: HorizonRecommendationRequest, user=Depends(require(Role.analyst, Role.supervisor, Role.admin))):
    ensure_real_dataset(request.dataset_id)
    population = load_model_population(request.dataset_id, request.model, eligible_only=True)
    try:
        recommendation = recommend_horizon(
            population,
            request.development_start,
            request.development_end,
            active_policy().get("thresholds", {}),
            request.preferred_months,
        )
    except ValueError as error:
        raise HTTPException(422, str(error))
    return {
        "dataset_id": request.dataset_id,
        "model": request.model,
        "policy_version": active_policy().get("version"),
        "recommendation": recommendation,
    }
