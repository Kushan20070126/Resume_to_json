import re
from difflib import get_close_matches
from typing import Any

from app.models.schemas import ParsedResume, ScoreBreakdown
from app.services.nlp_service import NLPService


class AnalyzerService:
    ACTION_KEYWORDS = {
        "built",
        "developed",
        "led",
        "implemented",
        "automated",
        "designed",
        "optimized",
        "delivered",
    }
    ROLE_ALIASES = {
        "devops": "devops engineer",
        "backend": "backend engineer",
        "frontend": "frontend engineer",
        "data science": "data scientist",
        "datascience": "data scientist",
        "full stack": "full stack engineer",
        "fullstack": "full stack engineer",
    }

    def __init__(self, nlp_service: NLPService) -> None:
        self.nlp = nlp_service

    def parse_resume(self, text: str, skills_catalog: list[str]) -> ParsedResume:
        return ParsedResume(
            name=self.nlp.extract_name(text),
            email=self.nlp.extract_email(text),
            skills=self.nlp.extract_skills(text, skills_catalog),
            experience=self.nlp.extract_experience(text),
            education=self.nlp.extract_education(text),
        )

    def calculate_skill_gap(
        self,
        resume_skills: list[str],
        job_role: str,
        role_templates: dict[str, list[str]],
    ) -> tuple[list[str], list[str], float]:
        role_key = self.resolve_job_role(job_role, role_templates)
        required = role_templates.get(role_key, [])
        if not required:
            return [], [], 0.0

        skill_set = {skill.lower() for skill in resume_skills}
        matched = sorted([skill for skill in required if skill in skill_set])
        missing = sorted([skill for skill in required if skill not in skill_set])

        match_score = round((len(matched) / len(required)) * 100, 2) if required else 0.0
        return matched, missing, match_score

    def calculate_resume_score(
        self,
        parsed: ParsedResume,
        raw_text: str,
        job_role: str,
        role_templates: dict[str, list[str]],
    ) -> tuple[float, float, ScoreBreakdown]:
        role_key = self.resolve_job_role(job_role, role_templates)
        required = role_templates.get(role_key, [])
        required_set = set(required)

        if required_set:
            skills_score = round((len(required_set.intersection(set(parsed.skills))) / len(required_set)) * 100, 2)
        else:
            skills_score = round(min(len(parsed.skills) * 10, 100), 2)

        years = self.nlp.estimate_years_experience(raw_text, parsed.experience)
        experience_score = min(years * 12, 70)
        if parsed.experience:
            experience_score += 25
        if re.search(r"\d", "\n".join(parsed.experience)):
            experience_score += 5
        experience_score = round(min(experience_score, 100), 2)

        section_hits = sum(
            1
            for key in ("experience", "education", "skills", "projects")
            if re.search(rf"\b{key}\b", raw_text, re.IGNORECASE)
        )
        format_score = 35.0
        if parsed.email:
            format_score += 20
        if parsed.name:
            format_score += 15
        if len(raw_text) >= 1200:
            format_score += 20
        elif len(raw_text) >= 600:
            format_score += 10
        format_score += min(section_hits * 7.5, 30)
        format_score = round(min(format_score, 100), 2)

        if required_set:
            keyword_score = round((len(required_set.intersection(set(parsed.skills))) / len(required_set)) * 100, 2)
        else:
            lower_text = raw_text.lower()
            action_hits = sum(1 for word in self.ACTION_KEYWORDS if word in lower_text)
            keyword_score = round(min(action_hits * 14, 100), 2)

        breakdown = ScoreBreakdown(
            skills=skills_score,
            experience=experience_score,
            format=format_score,
            keywords=keyword_score,
        )

        resume_score = round(
            (breakdown.skills * 0.3)
            + (breakdown.experience * 0.3)
            + (breakdown.format * 0.2)
            + (breakdown.keywords * 0.2),
            2,
        )

        ats_score = round((format_score * 0.4) + (keyword_score * 0.4) + (skills_score * 0.2), 2)
        return resume_score, ats_score, breakdown

    def recommended_roles(
        self,
        resume_skills: list[str],
        role_templates: dict[str, list[str]],
    ) -> list[str]:
        skill_set = set(skill.lower() for skill in resume_skills)
        ranked: list[tuple[str, float]] = []

        for role, required in role_templates.items():
            if not required:
                continue
            overlap = len(skill_set.intersection(required))
            if overlap == 0:
                continue
            score = overlap / len(required)
            ranked.append((role, score))

        ranked.sort(key=lambda item: item[1], reverse=True)
        return [role for role, _ in ranked[:3]] or ["general software engineer"]

    def improvement_suggestions(
        self,
        raw_text: str,
        missing_skills: list[str],
        match_score: float,
        recommended_roles: list[str],
        parsed: ParsedResume,
    ) -> list[str]:
        suggestions: list[str] = []

        if not re.search(r"\d", raw_text):
            suggestions.append("Add measurable achievements.")

        if missing_skills:
            suggestions.append(
                "Add these missing skills where you have real experience: " + ", ".join(missing_skills) + "."
            )

        if match_score < 45 and recommended_roles:
            suggestions.append(
                "Weak role match. Consider tailoring for: " + ", ".join(recommended_roles[:3]) + "."
            )

        if not parsed.experience:
            suggestions.append("Add a dedicated experience section with role impact.")

        if not parsed.education:
            suggestions.append("Include education details in a separate section.")

        return suggestions

    def build_strict_ai_fallback(
        self,
        job_role: str,
        parsed: ParsedResume,
        missing_skills: list[str],
        match_score: float,
        resume_score: float,
        ats_score: float,
    ) -> dict[str, Any]:
        role_label = (job_role or "").strip() or "target role"
        summary = (
            f"Resume score {round(resume_score)}/100. ATS score {round(ats_score)}/100.\n"
            f"Role match {round(match_score)}/100 for {role_label}."
        )

        strengths: list[str] = []
        weaknesses: list[str] = []

        if parsed.email:
            strengths.append("Contact email is present.")
        else:
            weaknesses.append("Contact email is missing.")

        if len(parsed.skills) >= 4:
            strengths.append("Skill coverage is decent.")
        elif len(parsed.skills) >= 2:
            strengths.append("Some core skills are listed.")
        else:
            weaknesses.append("Skill section is weak.")

        if parsed.experience:
            strengths.append("Experience entries are present.")
        else:
            weaknesses.append("Experience section is missing.")

        if parsed.education:
            strengths.append("Education section is present.")
        else:
            weaknesses.append("Education section is missing.")

        if missing_skills:
            weaknesses.append("Role-critical skills are missing: " + ", ".join(missing_skills[:5]) + ".")

        if match_score < 45:
            weaknesses.append("Role alignment is low.")
        if resume_score < 55:
            weaknesses.append("Overall resume quality is below baseline.")

        final_verdict = self._strict_verdict(match_score=match_score, resume_score=resume_score, ats_score=ats_score)

        return {
            "summary": summary,
            "strengths": strengths[:5],
            "weaknesses": weaknesses[:5],
            "final_verdict": final_verdict,
        }

    @classmethod
    def resolve_job_role(cls, job_role: str, role_templates: dict[str, list[str]]) -> str:
        raw = cls._normalize_role_name(job_role)
        if not raw:
            return ""

        normalized_map = {cls._normalize_role_name(role): role for role in role_templates.keys()}

        alias_target = cls.ROLE_ALIASES.get(raw)
        if alias_target and alias_target in role_templates:
            return alias_target

        if raw in normalized_map:
            return normalized_map[raw]

        for normalized_role, original_role in normalized_map.items():
            if raw in normalized_role or normalized_role in raw:
                return original_role

        close = get_close_matches(raw, list(normalized_map.keys()), n=1, cutoff=0.72)
        if close:
            return normalized_map[close[0]]

        return ""

    @staticmethod
    def _normalize_role_name(value: str) -> str:
        lowered = (value or "").strip().lower()
        lowered = re.sub(r"[^a-z0-9\s]", " ", lowered)
        lowered = re.sub(r"\s+", " ", lowered).strip()
        return lowered

    @staticmethod
    def _strict_verdict(match_score: float, resume_score: float, ats_score: float) -> str:
        if resume_score >= 75 and ats_score >= 75 and match_score >= 70:
            return "Good"
        if resume_score >= 50 and ats_score >= 50 and match_score >= 40:
            return "Average"
        return "Poor"
