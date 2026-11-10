from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# Le répertoire des données peut être déplacé sans dépendre de la structure du projet.
DATA_DIR = Path(__import__("os").environ.get("BACKTESTING_DATA_DIR", ROOT / "data"))
UPLOAD_DIR = DATA_DIR / "uploads"
DATABASE_PATH = DATA_DIR / "backtesting.db"
MODEL_DATABASE_DIR = DATA_DIR / "model_partitions"

DEFAULT_ASSET_CORRELATION = 0.12
MIN_DEFAULTS_FOR_FREQUENTIST = 20
MIN_DEFAULTS_FOR_BAYESIAN = 5
MIN_DEFAULTS_FOR_DECISION = 20
GINI_MINIMUM = 0.40
KS_MINIMUM = 0.20
BOOTSTRAP_ITERATIONS = 300

MODEL_MAPPING = {
    "PRO": "Professionnel",
    "CORPO EF": "Corpo_TPME_EF",
    "TPME (MODELE CORPO EF)": "Corpo_TPME_EF",
    "CORPO SEF": "Corpo_TPME_SANS_EF",
    "TPME (MODELE CORPO SEF)": "Corpo_TPME_SANS_EF",
}

REQUIRED_COLUMNS = {
    "Number", "Counterparty", "Created Date", "Model Scoring Name",
    "Final Rating Class", "Final Pd Class",
}
