"""Model performance / registry response schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ModelVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    model_name: str
    version: str
    is_active: bool
    metrics: dict
    trained_at: datetime


class ModelPerformanceOut(BaseModel):
    model_name: str
    active_version: ModelVersionOut | None
    recent_versions: list[ModelVersionOut]


class RetrainResponse(BaseModel):
    status: str
    model_name: str
    version: str | None
    metrics: dict
