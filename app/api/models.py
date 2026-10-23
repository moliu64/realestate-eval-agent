"""Pydantic request/response models for the HTTP API."""

from typing import Any

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=200)


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=80, pattern=r"^[A-Za-z0-9_\u4e00-\u9fff-]+$")
    password: str = Field(min_length=8, max_length=200)
    confirm_password: str = Field(min_length=1, max_length=200)


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)


class RagRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)


class EvaluateRequest(BaseModel):
    """Structured valuation input shared by one-shot and session endpoints."""

    property_usage: str = ""
    area: float | None = None
    layout: str = ""
    building_age: float | None = None
    orientation: str = ""
    floor: str = ""
    decoration: str = ""
    location: str = ""
    valuation_purpose: str = ""
    valuation_date: str = ""
    comparable_price: float | None = None
    net_income: float | None = None
    cap_rate: float | None = None
    land_value: float | None = None
    replacement_cost: float | None = None
    depreciation: float | None = None
    preset_year: int | None = None
    preset_sources: list[str] = Field(default_factory=list)
    preset_basis: str = ""
    note: str = ""


class SessionMessageRequest(EvaluateRequest):
    message: str = Field(default="", max_length=5000)


class SessionPatchRequest(BaseModel):
    title: str | None = Field(default=None, max_length=120)
    fixed_fields: dict[str, Any] | None = None
    layout_description: str | None = None
    layout_filename: str | None = None


class SessionRagRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)


class AskResponse(BaseModel):
    answer: str
    steps: list[dict[str, Any]] = Field(default_factory=list)
    report_json: str = ""


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
