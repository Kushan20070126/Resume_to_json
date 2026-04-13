import re

import spacy


class NLPService:
    EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
    YEARS_PATTERN = re.compile(r"(\d{1,2})\+?\s*(?:years|yrs)", re.IGNORECASE)
    YEAR_RANGE_PATTERN = re.compile(r"(19\d{2}|20\d{2})\s*[-–]\s*(present|current|19\d{2}|20\d{2})", re.IGNORECASE)

    EXPERIENCE_KEYWORDS = (
        "experience",
        "engineer",
        "developer",
        "intern",
        "manager",
        "lead",
        "consultant",
        "architect",
    )

    EDUCATION_KEYWORDS = (
        "b.sc",
        "bachelor",
        "master",
        "m.sc",
        "phd",
        "university",
        "college",
        "diploma",
        "degree",
    )
    NON_NAME_KEYWORDS = (
        "address",
        "street",
        "st.",
        "road",
        "rd.",
        "lane",
        "avenue",
        "city",
        "district",
        "state",
        "country",
        "linkedin",
        "github",
        "portfolio",
        "phone",
        "mobile",
        "email",
        "university",
        "college",
        "undergraduate",
        "foundation",
        "bachelors",
        "engineering",
        "experience",
        "skills",
        "top skills",
        "technical skills",
        "summary",
        "profile",
        "projects",
        "certifications",
        "languages",
        "interests",
        "about",
        "overview",
    )
    NON_NAME_TOKENS = {
        "top",
        "skills",
        "technical",
        "machine",
        "learning",
        "linux",
        "summary",
        "profile",
        "projects",
        "education",
        "experience",
        "certifications",
        "languages",
        "interests",
        "about",
        "overview",
    }

    def __init__(self, model_name: str = "en_core_web_sm") -> None:
        try:
            self.nlp = spacy.load(model_name)
        except Exception:
            self.nlp = spacy.blank("en")
            if "sentencizer" not in self.nlp.pipe_names:
                self.nlp.add_pipe("sentencizer")

    def extract_email(self, text: str) -> str:
        match = self.EMAIL_PATTERN.search(text)
        return match.group(0) if match else ""

    def extract_name(self, text: str) -> str:
        sample = text[:6000]
        doc = self.nlp(sample)
        email = self.extract_email(text)
        email_local = self._email_local_part(email)
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        head_lines = lines[:15]

        blocked_geo = {
            self._clean_name(ent.text).lower()
            for ent in doc.ents
            if ent.label_ in {"GPE", "LOC", "FAC"}
        }
        best_candidate = ""
        best_score = -10**9

        for ent in doc.ents:
            candidate = ent.text.strip()
            cleaned = self._clean_name(candidate)
            if ent.label_ != "PERSON":
                continue
            if not self._is_name_like(cleaned):
                continue
            if self._looks_like_non_name(candidate):
                continue

            score = 100 + self._email_overlap_score(cleaned, email_local)
            if cleaned.lower() in blocked_geo:
                score -= 20
            if score > best_score:
                best_candidate = cleaned
                best_score = score

        for idx, line in enumerate(head_lines):
            cleaned = self._clean_name(line)
            if not self._is_name_like(cleaned):
                continue
            if self._looks_like_non_name(line):
                continue

            score = self._line_name_score(line, cleaned, idx, email_local)
            if cleaned.lower() in blocked_geo:
                score -= 15
            if score > best_score:
                best_candidate = cleaned
                best_score = score

        if best_score >= 8:
            return best_candidate

        return self._name_from_email(email)

    def extract_skills(self, text: str, skills_catalog: list[str]) -> list[str]:
        lowered_text = text.lower()
        matched = [skill for skill in skills_catalog if self._contains_skill(lowered_text, skill)]
        return sorted(set(matched))

    def extract_experience(self, text: str) -> list[str]:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        matches: list[str] = []
        seen: set[str] = set()

        for line in lines:
            lowered = line.lower()
            if any(keyword in lowered for keyword in self.EXPERIENCE_KEYWORDS):
                normalized = re.sub(r"\s+", " ", line)
                if len(normalized) >= 15 and normalized.lower() not in seen:
                    matches.append(normalized)
                    seen.add(normalized.lower())
            if len(matches) >= 6:
                break

        return matches

    def extract_education(self, text: str) -> list[str]:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        matches: list[str] = []
        seen: set[str] = set()

        for line in lines:
            lowered = line.lower()
            if any(keyword in lowered for keyword in self.EDUCATION_KEYWORDS):
                normalized = re.sub(r"\s+", " ", line)
                if normalized.lower() not in seen:
                    matches.append(normalized)
                    seen.add(normalized.lower())
            if len(matches) >= 5:
                break

        return matches

    def estimate_years_experience(self, text: str, experience_lines: list[str]) -> int:
        direct_matches = [int(value) for value in self.YEARS_PATTERN.findall(text)]
        if direct_matches:
            return max(direct_matches)

        total_years = 0
        for start, end in self.YEAR_RANGE_PATTERN.findall(text):
            start_year = int(start)
            end_year = 2026 if end.lower() in {"present", "current"} else int(end)
            if end_year >= start_year:
                total_years += end_year - start_year

        if total_years > 0:
            return min(total_years, 30)

        return 1 if experience_lines else 0

    @staticmethod
    def _clean_name(value: str) -> str:
        cleaned = re.sub(r"[^A-Za-z\s.'-]", " ", value)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    @staticmethod
    def _is_name_like(value: str) -> bool:
        if not value or "@" in value:
            return False

        parts = value.split()
        if len(parts) < 2 or len(parts) > 4:
            return False

        if any(any(ch.isdigit() for ch in part) for part in parts):
            return False

        if any(len(part) <= 1 for part in parts):
            return False

        if all(part.islower() for part in parts):
            return False

        title_like = 0
        for part in parts:
            if re.fullmatch(r"[A-Z][A-Za-z'.-]*", part) or part.isupper():
                title_like += 1

        return title_like >= max(1, len(parts) - 1)

    @classmethod
    def _looks_like_non_name(cls, value: str) -> bool:
        lowered = value.lower()
        tokens = [t for t in re.findall(r"[a-z]+", lowered) if t]
        if any(keyword in lowered for keyword in cls.NON_NAME_KEYWORDS):
            return True
        if tokens and all(token in cls.NON_NAME_TOKENS for token in tokens):
            return True
        if any(ch.isdigit() for ch in value):
            return True
        if "(" in value or ")" in value:
            return True
        return False

    @staticmethod
    def _email_local_part(email: str) -> str:
        if not email or "@" not in email:
            return ""
        return email.split("@", 1)[0].lower()

    @classmethod
    def _email_overlap_score(cls, candidate: str, email_local: str) -> int:
        if not email_local:
            return 0

        score = 0
        for token in candidate.lower().split():
            if len(token) >= 3 and token in email_local:
                score += 6
        return score

    @classmethod
    def _line_name_score(cls, raw_line: str, cleaned: str, index: int, email_local: str) -> int:
        score = 0
        parts = cleaned.split()

        if index == 0:
            score += 6
        elif index < 3:
            score += 4
        else:
            score += 1

        if len(parts) in {2, 3}:
            score += 4
        else:
            score += 1

        score += cls._email_overlap_score(cleaned, email_local)

        if "," in raw_line:
            score -= 2
        if "." in raw_line:
            score -= 1

        return score

    @classmethod
    def _name_from_email(cls, email: str) -> str:
        local = cls._email_local_part(email)
        if not local:
            return ""

        alpha = re.sub(r"[^a-z]", "", local)
        if len(alpha) < 4:
            return ""

        parts = [p for p in re.split(r"[._-]+", local) if p]
        if len(parts) >= 2:
            tokens = [re.sub(r"[^a-z]", "", p) for p in parts]
            tokens = [t for t in tokens if len(t) >= 2]
            if len(tokens) >= 2:
                return " ".join(token.capitalize() for token in tokens[:3])

        if len(alpha) >= 8:
            split_idx = cls._best_email_split(alpha)
            if split_idx is not None:
                left = alpha[:split_idx]
                right = alpha[split_idx:]
                if len(left) >= 3 and len(right) >= 3:
                    return f"{left.capitalize()} {right.capitalize()}"

        return alpha.capitalize()

    @staticmethod
    def _best_email_split(alpha: str) -> int | None:
        n = len(alpha)
        if n < 8:
            return None

        vowels = set("aeiou")
        best_idx: int | None = None
        best_score: float | None = None
        center = n / 2

        for idx in range(3, n - 2):
            left = alpha[:idx]
            right = alpha[idx:]
            if not any(ch in vowels for ch in left) or not any(ch in vowels for ch in right):
                continue

            score = abs(idx - center) * 2
            if left[-1] in vowels:
                score += 1
            if right[0] in vowels:
                score += 1
            if left[-1] not in vowels and right[0] not in vowels:
                score -= 2

            if best_score is None or score < best_score:
                best_score = score
                best_idx = idx

        return best_idx

    @staticmethod
    def _contains_skill(text: str, skill: str) -> bool:
        pattern = rf"(?<!\w){re.escape(skill)}(?!\w)"
        return bool(re.search(pattern, text))
