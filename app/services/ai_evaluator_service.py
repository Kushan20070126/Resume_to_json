import json
import re
from typing import Any

import httpx
from fastapi import HTTPException

from app.core.config import get_settings


class AIEvaluatorService:
    def __init__(self) -> None:
        self.settings = get_settings()

    @property
    def enabled(self) -> bool:
        return bool(self.settings.gemini_api_key)

    async def evaluate_resume(self, job_role: str, resume_text: str) -> dict[str, Any]:
        if not self.enabled:
            raise HTTPException(status_code=400, detail="Gemini API key is not configured.")

        prompt = self._build_prompt(job_role=job_role, resume_text=resume_text)
        response_text = await self._call_gemini(prompt)
        parsed = self._parse_model_json(response_text)
        return self._sanitize_response(parsed)

    async def _call_gemini(self, prompt: str) -> str:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.settings.gemini_model}:generateContent"
        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.1,
                "response_mime_type": "application/json",
            },
        }

        try:
            async with httpx.AsyncClient(timeout=self.settings.gemini_timeout_seconds) as client:
                response = await client.post(url, params={"key": self.settings.gemini_api_key}, json=payload)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise self._map_http_status_error(exc) from exc
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail="Gemini connection error.") from exc

        data = response.json()
        return self._extract_text_response(data)

    @staticmethod
    def _build_prompt(job_role: str, resume_text: str) -> str:
        trimmed_role = (job_role or "").strip()
        trimmed_text = (resume_text or "").strip()
        if len(trimmed_text) > 15000:
            trimmed_text = trimmed_text[:15000]

        return (
            "You are an ATS resume evaluator.\n"
            "Be strict. Be concise. No explanations.\n"
            "Use short sentences.\n"
            "Return ONLY valid JSON.\n"
            "If missing data, return empty values.\n\n"
            f"Job Role:\n{trimmed_role}\n\n"
            f"Resume:\n{trimmed_text}\n\n"
            "Output format:\n"
            "{\n"
            '  "summary": "2 line professional summary",\n'
            '  "strengths": ["max 5 items"],\n'
            '  "weaknesses": ["max 5 items"],\n'
            '  "final_verdict": "Good | Average | Poor"\n'
            "}"
        )

    @staticmethod
    def _extract_text_response(data: dict[str, Any]) -> str:
        candidates = data.get("candidates") or []
        if not candidates:
            return "{}"

        first = candidates[0]
        content = first.get("content") or {}
        parts = content.get("parts") or []
        texts = [str(part.get("text", "")) for part in parts if isinstance(part, dict)]
        return "\n".join(t for t in texts if t).strip() or "{}"

    @staticmethod
    def _parse_model_json(text: str) -> dict[str, Any]:
        if not text:
            return {}

        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            return {}

        try:
            parsed = json.loads(match.group(0))
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            return {}

        return {}

    @staticmethod
    def _sanitize_response(value: dict[str, Any]) -> dict[str, Any]:
        summary = str(value.get("summary", "")).strip()
        strengths = AIEvaluatorService._sanitize_list(value.get("strengths"), limit=5)
        weaknesses = AIEvaluatorService._sanitize_list(value.get("weaknesses"), limit=5)

        verdict_raw = str(value.get("final_verdict", "")).strip().lower()
        if verdict_raw == "good":
            final_verdict = "Good"
        elif verdict_raw == "poor":
            final_verdict = "Poor"
        else:
            final_verdict = "Average"

        return {
            "summary": summary,
            "strengths": strengths,
            "weaknesses": weaknesses,
            "final_verdict": final_verdict,
        }

    @staticmethod
    def _sanitize_list(items: Any, limit: int = 5) -> list[str]:
        if not isinstance(items, list):
            return []
        result: list[str] = []
        for item in items:
            text = str(item).strip()
            if not text:
                continue
            result.append(text)
            if len(result) >= limit:
                break
        return result

    @classmethod
    def _map_http_status_error(cls, exc: httpx.HTTPStatusError) -> HTTPException:
        status_code = exc.response.status_code
        api_status = ""
        api_message = ""

        try:
            payload = exc.response.json()
            error_obj = payload.get("error", {}) if isinstance(payload, dict) else {}
            api_status = str(error_obj.get("status", "")).strip().upper()
            api_message = str(error_obj.get("message", "")).strip()
        except Exception:
            api_message = ""

        if status_code == 429 or api_status == "RESOURCE_EXHAUSTED":
            retry_seconds = cls._extract_retry_seconds(api_message) or 30
            return HTTPException(
                status_code=429,
                detail=f"Gemini quota/rate limit exceeded. Retry after {retry_seconds}s.",
            )

        if status_code in {401, 403}:
            return HTTPException(status_code=502, detail="Gemini authentication/permission failed.")
        if status_code == 404:
            return HTTPException(status_code=502, detail="Gemini model not found. Check GEMINI_MODEL.")
        if status_code >= 500:
            return HTTPException(status_code=502, detail="Gemini service unavailable.")

        short = api_message[:200] if api_message else f"HTTP {status_code}"
        return HTTPException(status_code=502, detail=f"Gemini API request failed: {short}")

    @staticmethod
    def _extract_retry_seconds(message: str) -> int | None:
        if not message:
            return None
        match = re.search(r"retry in\s+([\d.]+)s", message, re.IGNORECASE)
        if not match:
            return None
        try:
            return max(1, int(float(match.group(1))))
        except ValueError:
            return None
