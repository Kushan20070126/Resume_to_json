import logging
from datetime import datetime, timezone
from typing import Any

from postgrest.exceptions import APIError
from supabase import Client, create_client

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class SupabaseService:
    NON_FATAL_ERROR_CODES = {"42501", "PGRST205"}

    def __init__(self) -> None:
        self.settings = get_settings()
        self.client: Client | None = None
        self._disabled_reason: str | None = None

        if self.settings.supabase_enabled:
            write_key = self.settings.supabase_write_key
            self.client = create_client(self.settings.supabase_url, write_key)
            if not self.settings.supabase_service_role_key:
                logger.warning(
                    "SUPABASE_SERVICE_ROLE_KEY is not set. If writes fail with 42501/RLS errors, "
                    "set SUPABASE_SERVICE_ROLE_KEY or run supabase/setup.sql."
                )

    @property
    def enabled(self) -> bool:
        return self.client is not None and self._disabled_reason is None

    @property
    def disabled_reason(self) -> str | None:
        return self._disabled_reason

    def upload_resume_file(self, file_bytes: bytes, filename: str) -> str | None:
        if not self.enabled:
            return None

        safe_name = filename.replace(" ", "_")
        object_path = f"resumes/{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}_{safe_name}"

        self.client.storage.from_(self.settings.supabase_bucket).upload(
            object_path,
            file_bytes,
            file_options={"content-type": "application/pdf"},
        )
        return object_path

    def save_resume(self, raw_text: str) -> Any:
        if not self.enabled:
            return None

        response = self.client.table("resumes").insert({"raw_text": raw_text}).execute()
        data = getattr(response, "data", None) or []
        if not data:
            return None
        return data[0].get("id")

    def save_analysis(
        self,
        resume_id: Any,
        score: float,
        skills: list[str],
        missing_skills: list[str],
        suggestions: list[str],
    ) -> Any:
        if not self.enabled or not resume_id:
            return None

        payload = {
            "resume_id": resume_id,
            "score": score,
            "skills": skills,
            "missing_skills": missing_skills,
            "suggestions": suggestions,
        }
        response = self.client.table("analysis").insert(payload).execute()
        data = getattr(response, "data", None) or []
        return data[0] if data else None

    def handle_persistence_exception(self, exc: Exception) -> bool:
        code = self._extract_error_code(exc)
        message = str(exc).lower()
        is_non_fatal = code in self.NON_FATAL_ERROR_CODES or "row-level security" in message or "schema cache" in message
        if is_non_fatal:
            self._disabled_reason = str(exc)
            logger.warning(
                "Disabling Supabase persistence for this process due to configuration/permission error: %s",
                exc,
            )
            return True
        return False

    @staticmethod
    def _extract_error_code(exc: Exception) -> str | None:
        if isinstance(exc, APIError):
            code = getattr(exc, "code", None)
            if code:
                return str(code)
            if exc.args and isinstance(exc.args[0], dict):
                arg_code = exc.args[0].get("code")
                if arg_code:
                    return str(arg_code)
        return None
