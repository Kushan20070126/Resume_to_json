import asyncio
import logging

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.core.config import get_settings
from app.models.schemas import (
    AIEvaluateResponse,
    AnalyzeResponse,
    ParsedResume,
    ScoreResponse,
    SkillGapRequest,
    SkillGapResponse,
)
from app.services.analyzer_service import AnalyzerService
from app.services.ai_evaluator_service import AIEvaluatorService
from app.services.data_service import load_role_templates, load_skills
from app.services.nlp_service import NLPService
from app.services.pdf_service import PDFService
from app.services.supabase_service import SupabaseService

router = APIRouter(prefix="/resume", tags=["resume"])
logger = logging.getLogger(__name__)

pdf_service = PDFService()
nlp_service = NLPService()
analyzer = AnalyzerService(nlp_service)
ai_evaluator = AIEvaluatorService()
supabase_service = SupabaseService()
settings = get_settings()


@router.post("/parse", response_model=ParsedResume)
async def parse_resume(file: UploadFile = File(...)) -> ParsedResume:
    pdf_bytes = await pdf_service.read_pdf_bytes(file)
    raw_text, _ = pdf_service.extract_text_from_pdf_bytes(pdf_bytes)
    if not raw_text.strip():
        raise HTTPException(status_code=400, detail="No text could be extracted from this PDF.")

    skills_catalog = load_skills()
    return analyzer.parse_resume(raw_text, skills_catalog)


@router.post("/score", response_model=ScoreResponse)
async def score_resume(
    file: UploadFile = File(...),
    job_role: str = Form(default=""),
) -> ScoreResponse:
    pdf_bytes = await pdf_service.read_pdf_bytes(file)
    raw_text, _ = pdf_service.extract_text_from_pdf_bytes(pdf_bytes)
    if not raw_text.strip():
        raise HTTPException(status_code=400, detail="No text could be extracted from this PDF.")

    skills_catalog = load_skills()
    role_templates = load_role_templates()

    parsed = analyzer.parse_resume(raw_text, skills_catalog)
    resume_score, _, breakdown = analyzer.calculate_resume_score(parsed, raw_text, job_role, role_templates)

    return ScoreResponse(resume_score=resume_score, breakdown=breakdown)


@router.post("/skill-gap", response_model=SkillGapResponse)
async def skill_gap(payload: SkillGapRequest) -> SkillGapResponse:
    skills_catalog = load_skills()
    role_templates = load_role_templates()

    parsed = analyzer.parse_resume(payload.resume_text, skills_catalog)
    matched, missing, match_score = analyzer.calculate_skill_gap(parsed.skills, payload.job_role, role_templates)

    return SkillGapResponse(matched_skills=matched, missing_skills=missing, match_score=match_score)


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_resume(
    file: UploadFile = File(...),
    job_role: str = Form(default=""),
) -> AnalyzeResponse:
    pdf_bytes = await pdf_service.read_pdf_bytes(file)
    raw_text, _ = pdf_service.extract_text_from_pdf_bytes(pdf_bytes)

    if not raw_text.strip():
        raise HTTPException(status_code=400, detail="No text could be extracted from this PDF.")

    skills_catalog = load_skills()
    role_templates = load_role_templates()

    parsed = analyzer.parse_resume(raw_text, skills_catalog)
    matched, missing, match_score = analyzer.calculate_skill_gap(parsed.skills, job_role, role_templates)
    resume_score, ats_score, _ = analyzer.calculate_resume_score(parsed, raw_text, job_role, role_templates)
    recommended = analyzer.recommended_roles(parsed.skills, role_templates)
    improvements = analyzer.improvement_suggestions(raw_text, missing, match_score, recommended, parsed)

    if supabase_service.enabled:
        try:
            resume_id = await asyncio.to_thread(supabase_service.save_resume, raw_text)
            await asyncio.to_thread(supabase_service.upload_resume_file, pdf_bytes, file.filename or "resume.pdf")
            await asyncio.to_thread(
                supabase_service.save_analysis,
                resume_id,
                resume_score,
                parsed.skills,
                missing,
                improvements,
            )
        except Exception as exc:  # pragma: no cover
            if settings.supabase_strict:
                raise HTTPException(status_code=502, detail=f"Supabase operation failed: {exc}") from exc
            handled = supabase_service.handle_persistence_exception(exc)
            if handled:
                logger.warning("Supabase persistence skipped. Returning analysis only.")
            else:
                logger.warning("Supabase persistence failed. Returning analysis without persistence: %s", exc)

    return AnalyzeResponse(
        name=parsed.name,
        email=parsed.email,
        skills=parsed.skills,
        experience=parsed.experience,
        education=parsed.education,
        resume_score=resume_score,
        ats_score=ats_score,
        missing_skills=missing,
        recommended_roles=recommended,
        improvements=improvements,
    )


@router.post("/ai-evaluate", response_model=AIEvaluateResponse)
async def ai_evaluate_resume(
    file: UploadFile = File(...),
    job_role: str = Form(...),
) -> AIEvaluateResponse:
    pdf_bytes = await pdf_service.read_pdf_bytes(file)
    raw_text, _ = pdf_service.extract_text_from_pdf_bytes(pdf_bytes)
    if not raw_text.strip():
        raise HTTPException(status_code=400, detail="No text could be extracted from this PDF.")

    skills_catalog = load_skills()
    role_templates = load_role_templates()

    parsed = analyzer.parse_resume(raw_text, skills_catalog)
    resolved_role = analyzer.resolve_job_role(job_role, role_templates) or job_role
    _, missing, match_score = analyzer.calculate_skill_gap(parsed.skills, job_role, role_templates)
    resume_score, ats_score, _ = analyzer.calculate_resume_score(parsed, raw_text, job_role, role_templates)
    recommended = analyzer.recommended_roles(parsed.skills, role_templates)[:3]
    improvements = analyzer.improvement_suggestions(raw_text, missing, match_score, recommended, parsed)
    fallback = analyzer.build_strict_ai_fallback(
        job_role=resolved_role,
        parsed=parsed,
        missing_skills=missing,
        match_score=match_score,
        resume_score=resume_score,
        ats_score=ats_score,
    )
    try:
        ai_response = await ai_evaluator.evaluate_resume(job_role=job_role, resume_text=raw_text)
    except HTTPException as exc:
        if settings.gemini_fallback_enabled:
            if settings.debug:
                logger.warning("Gemini evaluation unavailable. Using deterministic fallback.")
            ai_response = fallback
        else:
            raise

    if not ai_response.get("summary"):
        ai_response["summary"] = fallback["summary"]
    if not ai_response.get("strengths"):
        ai_response["strengths"] = fallback["strengths"]
    if not ai_response.get("weaknesses"):
        ai_response["weaknesses"] = fallback["weaknesses"]
    if ai_response.get("final_verdict") not in {"Good", "Average", "Poor"}:
        ai_response["final_verdict"] = fallback["final_verdict"]

    return AIEvaluateResponse(
        summary=ai_response.get("summary", ""),
        strengths=ai_response.get("strengths", []),
        weaknesses=ai_response.get("weaknesses", []),
        skills=parsed.skills,
        missing_skills=missing,
        match_score=match_score,
        resume_score=resume_score,
        ats_score=ats_score,
        recommended_roles=recommended,
        improvements=improvements,
        final_verdict=ai_response.get("final_verdict", "Average"),
    )
