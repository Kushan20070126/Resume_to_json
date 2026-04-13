from typing import Any, Literal

from pydantic import BaseModel, Field


class ParsedResume(BaseModel):
    name: str = ""
    email: str = ""
    skills: list[str] = Field(default_factory=list)
    experience: list[str] = Field(default_factory=list)
    education: list[str] = Field(default_factory=list)


class ScoreBreakdown(BaseModel):
    skills: float
    experience: float
    format: float
    keywords: float


class ScoreResponse(BaseModel):
    resume_score: float
    breakdown: ScoreBreakdown


class SkillGapRequest(BaseModel):
    resume_text: str = Field(min_length=1)
    job_role: str = Field(min_length=1)


class SkillGapResponse(BaseModel):
    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    match_score: float


class AnalyzeResponse(BaseModel):
    name: str
    email: str
    skills: list[str] = Field(default_factory=list)
    experience: list[str] = Field(default_factory=list)
    education: list[str] = Field(default_factory=list)
    resume_score: float
    ats_score: float
    missing_skills: list[str] = Field(default_factory=list)
    recommended_roles: list[str] = Field(default_factory=list)
    improvements: list[str] = Field(default_factory=list)


class AIEvaluateResponse(BaseModel):
    summary: str = ""
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    match_score: float = 0
    resume_score: float = 0
    ats_score: float = 0
    recommended_roles: list[str] = Field(default_factory=list)
    improvements: list[str] = Field(default_factory=list)
    final_verdict: Literal["Good", "Average", "Poor"] = "Average"


class ErrorResponse(BaseModel):
    detail: str


class SupabasePersistResult(BaseModel):
    resume_id: Any = None
    file_path: str | None = None
