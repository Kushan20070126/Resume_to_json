import json
from functools import lru_cache
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"


@lru_cache
def load_skills() -> list[str]:
    skills_path = DATA_DIR / "skills.json"
    with skills_path.open("r", encoding="utf-8") as f:
        skills = json.load(f)

    return sorted({str(skill).strip().lower() for skill in skills if str(skill).strip()})


@lru_cache
def load_role_templates() -> dict[str, list[str]]:
    role_path = DATA_DIR / "role_templates.json"
    with role_path.open("r", encoding="utf-8") as f:
        templates = json.load(f)

    normalized: dict[str, list[str]] = {}
    for role, values in templates.items():
        role_key = str(role).strip().lower()
        skills = sorted({str(skill).strip().lower() for skill in values if str(skill).strip()})
        normalized[role_key] = skills

    return normalized
