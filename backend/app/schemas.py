from enum import Enum
from pydantic import BaseModel, Field


class Role(str, Enum):
    analyst = "analyst"
    supervisor = "supervisor"
    admin = "admin"


class LoginRequest(BaseModel):
    username: str
    password: str


class RegistrationRequest(BaseModel):
    username: str = Field(min_length=3, max_length=80, pattern=r"^[a-zA-Z0-9._-]+$")
    full_name: str = Field(min_length=3, max_length=160)
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=12, max_length=256)


class AccountApprovalRequest(BaseModel):
    username: str
    role: Role = Role.analyst


class BacktestRequest(BaseModel):
    dataset_id: str
    model: str
    rating_column: str = "Final Rating Class"
    pd_column: str = "Final Pd Class"
    default_column: str = "defaut_observe"
    asset_correlation: float = Field(default=0.12, ge=0, lt=1)
    reference_dataset_id: str | None = None
    development_start: str | None = None
    development_end: str | None = None
    backtest_start: str | None = None
    backtest_end: str | None = None


class RecalibrationRequest(BacktestRequest):
    method: str = "auto"  # auto | central_tendency | logistic | bayesian
    validation_fraction: float = Field(default=0.30, gt=0, lt=0.5)

class RevalidationRequest(BaseModel):
    proposal_run_id: str
    validation_dataset_id: str
    model: str
    asset_correlation: float = Field(default=0.12, ge=0, lt=1)

class ChatRequest(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
    run_id: str | None = None
    model: str | None = None


class HorizonRecommendationRequest(BaseModel):
    dataset_id: str
    model: str
    development_start: str
    development_end: str
    preferred_months: int = Field(default=12, ge=3, le=36)
