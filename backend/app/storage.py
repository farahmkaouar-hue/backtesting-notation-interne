import hashlib
import json
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .config import DATABASE_PATH, MODEL_DATABASE_DIR, UPLOAD_DIR
from .config import MODEL_MAPPING


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect() -> sqlite3.Connection:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DATABASE_PATH)
    db.row_factory = sqlite3.Row
    return db


def _normalize_for_sql(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    for column in out.columns:
        if str(out[column].dtype).startswith("datetime64"):
            out[column] = out[column].dt.strftime("%Y-%m-%d")
    return out


def _safe_model_slug(model: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in model).strip("_")


def _partition_db_path(dataset_id: str, model: str) -> Path:
    MODEL_DATABASE_DIR.mkdir(parents=True, exist_ok=True)
    return MODEL_DATABASE_DIR / f"{dataset_id}_{_safe_model_slug(model)}.db"


def load_all_model_partitions(dataset_id: str) -> pd.DataFrame:
    """Reconstitue la population préparée depuis les partitions, source de vérité après import."""
    records = list_model_partitions(dataset_id)
    frames = [load_model_partition(dataset_id, record["model"]) for record in records]
    frames = [frame for frame in frames if not frame.empty]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def init_db() -> None:
    with connect() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
              username TEXT PRIMARY KEY, password_hash TEXT NOT NULL, role TEXT NOT NULL, created_at TEXT NOT NULL,
              full_name TEXT, email TEXT, status TEXT NOT NULL DEFAULT 'active', approved_by TEXT, approved_at TEXT
            );
            CREATE TABLE IF NOT EXISTS datasets (
              id TEXT PRIMARY KEY, filename TEXT NOT NULL, path TEXT NOT NULL, created_by TEXT NOT NULL,
              created_at TEXT NOT NULL, metadata TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS runs (
              id TEXT PRIMARY KEY, dataset_id TEXT NOT NULL, run_type TEXT NOT NULL, model TEXT,
              parameters TEXT NOT NULL, result TEXT NOT NULL, created_by TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS audit_log (
              id INTEGER PRIMARY KEY AUTOINCREMENT, actor TEXT NOT NULL, action TEXT NOT NULL,
              entity_type TEXT NOT NULL, entity_id TEXT NOT NULL, detail TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS chat_messages (
              id INTEGER PRIMARY KEY AUTOINCREMENT, actor TEXT NOT NULL, run_id TEXT,
              question TEXT NOT NULL, answer TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS governance_policies (
              id TEXT PRIMARY KEY, version TEXT NOT NULL UNIQUE, content TEXT NOT NULL,
              is_active INTEGER NOT NULL, created_by TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS model_partitions (
              id TEXT PRIMARY KEY,
              dataset_id TEXT NOT NULL,
              model TEXT NOT NULL,
              db_path TEXT NOT NULL,
              row_count INTEGER NOT NULL,
              eligible_count INTEGER NOT NULL,
              observed_rating_count INTEGER NOT NULL,
              default_count INTEGER NOT NULL,
              created_by TEXT NOT NULL,
              created_at TEXT NOT NULL,
              UNIQUE(dataset_id, model)
            );
            """
        )
        columns = {row["name"] for row in db.execute("PRAGMA table_info(users)").fetchall()}
        for name, definition in {
            "full_name": "TEXT", "email": "TEXT", "status": "TEXT NOT NULL DEFAULT 'active'",
            "approved_by": "TEXT", "approved_at": "TEXT",
        }.items():
            if name not in columns:
                db.execute(f"ALTER TABLE users ADD COLUMN {name} {definition}")

        policy = db.execute("SELECT 1 FROM governance_policies WHERE is_active=1").fetchone()
        if not policy:
            from .services.governance import default_policy

            content = default_policy()
            db.execute(
                "INSERT INTO governance_policies VALUES (?,?,?,?,?,?)",
                (secrets.token_urlsafe(12), content["version"], json.dumps(content), 1, "system", now()),
            )


def password_hash(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 200_000).hex()
    return f"{salt}${digest}"


def verify_password(password: str, encoded: str) -> bool:
    salt, digest = encoded.split("$", 1)
    return secrets.compare_digest(password_hash(password, salt).split("$", 1)[1], digest)


def validate_password_strength(password: str) -> None:
    if len(password) < 12 or not any(char.islower() for char in password) or not any(char.isupper() for char in password) or not any(char.isdigit() for char in password) or not any(not char.isalnum() for char in password):
        raise ValueError("Le mot de passe doit contenir au moins 12 caractères, une majuscule, une minuscule, un chiffre et un symbole.")


def get_user(username: str):
    with connect() as db:
        return db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()


def create_registration(username: str, full_name: str, email: str, password: str) -> None:
    validate_password_strength(password)
    with connect() as db:
        exists = db.execute("SELECT 1 FROM users WHERE username=? OR email=?", (username, email)).fetchone()
        if exists:
            raise ValueError("Identifiant ou adresse e-mail déjà utilisé.")
        db.execute(
            "INSERT INTO users(username,password_hash,role,created_at,full_name,email,status) VALUES (?,?,?,?,?,?,?)",
            (username, password_hash(password), "analyst", now(), full_name, email, "pending"),
        )
    audit(username, "REGISTER_ACCOUNT", "user", username, {"email": email, "status": "pending"})


def approve_account(username: str, role: str, approver: str) -> bool:
    with connect() as db:
        cursor = db.execute(
            "UPDATE users SET role=?, status='active', approved_by=?, approved_at=? WHERE username=? AND status='pending'",
            (role, approver, now(), username),
        )
        rowcount = cursor.rowcount
    if rowcount:
        audit(approver, "APPROVE_ACCOUNT", "user", username, {"role": role})
        return True
    return False


def pending_accounts() -> list[dict]:
    with connect() as db:
        rows = db.execute("SELECT username, full_name, email, created_at FROM users WHERE status='pending' ORDER BY created_at").fetchall()
    return [dict(row) for row in rows]


def audit(actor: str, action: str, entity_type: str, entity_id: str, detail: dict) -> None:
    with connect() as db:
        db.execute(
            "INSERT INTO audit_log(actor,action,entity_type,entity_id,detail,created_at) VALUES (?,?,?,?,?,?)",
            (actor, action, entity_type, entity_id, json.dumps(detail, ensure_ascii=False), now()),
        )


def save_dataset(filename: str, content: bytes, actor: str, metadata: dict) -> str:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    dataset_id = secrets.token_urlsafe(12)
    path = UPLOAD_DIR / f"{dataset_id}_{Path(filename).name}"
    path.write_bytes(content)
    with connect() as db:
        db.execute(
            "INSERT INTO datasets VALUES (?,?,?,?,?,?)",
            (dataset_id, filename, str(path), actor, now(), json.dumps(metadata)),
        )
    audit(actor, "UPLOAD", "dataset", dataset_id, metadata)
    return dataset_id


def dataset(dataset_id: str):
    with connect() as db:
        return db.execute("SELECT * FROM datasets WHERE id=?", (dataset_id,)).fetchone()


def save_model_partitions(dataset_id: str, prepared: pd.DataFrame, actor: str) -> list[dict]:
    partitions = []
    canonical_models = sorted(set(MODEL_MAPPING.values()))
    with connect() as db:
        for model_name in canonical_models:
            frame = prepared[prepared["modele_cible"] == model_name].copy()
            db_path = _partition_db_path(dataset_id, model_name)
            normalized = _normalize_for_sql(frame)
            with sqlite3.connect(db_path) as model_db:
                normalized.to_sql("observations", model_db, if_exists="replace", index=False)
                model_db.execute("CREATE INDEX IF NOT EXISTS idx_observations_date ON observations(date_notation)")
                model_db.execute("CREATE INDEX IF NOT EXISTS idx_observations_number ON observations(Number)")

            row_count = int(len(frame))
            eligible_count = int(frame["eligible_backtesting"].fillna(0).sum()) if "eligible_backtesting" in frame else 0
            observed_count = int(frame["note_reelle_num"].notna().sum()) if "note_reelle_num" in frame else 0
            default_count = int(frame["defaut_observe"].fillna(0).sum()) if "defaut_observe" in frame else 0

            db.execute(
                """
                INSERT INTO model_partitions(id, dataset_id, model, db_path, row_count, eligible_count,
                                             observed_rating_count, default_count, created_by, created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(dataset_id, model) DO UPDATE SET
                  db_path=excluded.db_path,
                  row_count=excluded.row_count,
                  eligible_count=excluded.eligible_count,
                  observed_rating_count=excluded.observed_rating_count,
                  default_count=excluded.default_count,
                  created_by=excluded.created_by,
                  created_at=excluded.created_at
                """,
                (
                    secrets.token_urlsafe(12),
                    dataset_id,
                    model_name,
                    str(db_path),
                    row_count,
                    eligible_count,
                    observed_count,
                    default_count,
                    actor,
                    now(),
                ),
            )
            partitions.append(
                {
                    "model": model_name,
                    "db_path": str(db_path),
                    "rows": row_count,
                    "eligible": eligible_count,
                    "observed_ratings": observed_count,
                    "defaults": default_count,
                }
            )

    audit(actor, "PARTITION_MODELS", "dataset", dataset_id, {"partitions": partitions})
    return partitions


def load_model_partition(dataset_id: str, model: str) -> pd.DataFrame:
    with connect() as db:
        row = db.execute(
            "SELECT db_path FROM model_partitions WHERE dataset_id=? AND model=?",
            (dataset_id, model),
        ).fetchone()
    if not row:
        return pd.DataFrame()
    db_path = Path(row["db_path"])
    if not db_path.exists():
        return pd.DataFrame()
    with sqlite3.connect(db_path) as model_db:
        frame = pd.read_sql_query("SELECT * FROM observations", model_db)
    for column in ["date_notation", "date_modification"]:
        if column in frame:
            frame[column] = pd.to_datetime(frame[column], errors="coerce")
    return frame


def list_model_partitions(dataset_id: str) -> list[dict]:
    with connect() as db:
        rows = db.execute(
            """
            SELECT dataset_id, model, db_path, row_count, eligible_count, observed_rating_count, default_count, created_at
            FROM model_partitions
            WHERE dataset_id=?
            ORDER BY model
            """,
            (dataset_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def save_run(dataset_id: str, run_type: str, model: str, parameters: dict, result: dict, actor: str) -> str:
    run_id = secrets.token_urlsafe(12)
    with connect() as db:
        db.execute(
            "INSERT INTO runs VALUES (?,?,?,?,?,?,?,?)",
            (run_id, dataset_id, run_type, model, json.dumps(parameters), json.dumps(result), actor, now()),
        )
    audit(actor, run_type.upper(), "run", run_id, {"dataset_id": dataset_id, "model": model})
    return run_id


def get_run(run_id: str):
    with connect() as db:
        return db.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()


def save_chat(actor: str, run_id: str | None, question: str, answer: str) -> None:
    with connect() as db:
        db.execute(
            "INSERT INTO chat_messages(actor,run_id,question,answer,created_at) VALUES (?,?,?,?,?)",
            (actor, run_id, question, answer, now()),
        )
    audit(actor, "CHAT", "run", run_id or "none", {"question": question[:300]})


def get_active_policy() -> dict | None:
    with connect() as db:
        row = db.execute(
            "SELECT content FROM governance_policies WHERE is_active=1 ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
    if not row:
        return None
    return json.loads(row["content"])
