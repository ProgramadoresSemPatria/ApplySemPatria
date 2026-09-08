"""Extract role tech keywords from job text for ResumeChameleon."""

from __future__ import annotations

import re
from typing import Any

DEFAULT_TECH_LEXICON: tuple[str, ...] = (
    "agentic ai",
    "agentic",
    "multi-agent",
    "langsmith",
    "langfuse",
    "langgraph",
    "langchain",
    "openai",
    "anthropic",
    "claude",
    "gpt-4",
    "gpt",
    "llm",
    "rag",
    "retrieval augmented generation",
    "vector database",
    "pinecone",
    "weaviate",
    "chromadb",
    "qdrant",
    "mcp",
    "model context protocol",
    "fastapi",
    "django",
    "flask",
    "nestjs",
    "node.js",
    "nodejs",
    "typescript",
    "javascript",
    "python",
    "kotlin",
    "java",
    "go",
    "golang",
    "rust",
    "c++",
    "react",
    "next.js",
    "nextjs",
    "vue",
    "angular",
    "android",
    "ios",
    "swift",
    "terraform",
    "pulumi",
    "docker",
    "kubernetes",
    "k8s",
    "aws",
    "gcp",
    "azure",
    "vertex ai",
    "bedrock",
    "sagemaker",
    "lambda",
    "ec2",
    "s3",
    "cloudformation",
    "ci/cd",
    "github actions",
    "gitlab ci",
    "jenkins",
    "rest api",
    "graphql",
    "grpc",
    "microservices",
    "postgresql",
    "postgres",
    "mysql",
    "mongodb",
    "redis",
    "kafka",
    "spark",
    "airflow",
    "dbt",
    "snowflake",
    "databricks",
    "mlflow",
    "huggingface",
    "pytorch",
    "tensorflow",
    "scikit-learn",
    "pandas",
    "numpy",
    "computer vision",
    "nlp",
    "fine-tuning",
    "prompt engineering",
    "observability",
    "datadog",
    "prometheus",
    "grafana",
    "elasticsearch",
    "opensearch",
    "selenium",
    "playwright",
    "pytest",
    "jest",
    "unit tests",
    "integration tests",
    "agile",
    "scrum",
)

def normalize_keyword(keyword: str) -> str:
    return re.sub(r"\s+", " ", (keyword or "").strip().lower())


_KEYWORD_ALIASES: dict[str, str] = {
    "postgres": "postgresql",
    "nodejs": "node.js",
    "nextjs": "next.js",
    "k8s": "kubernetes",
}


def _canonical_keyword(key: str) -> str:
    key = normalize_keyword(key)
    return _KEYWORD_ALIASES.get(key, key)


def _term_matches(lower: str, key: str) -> bool:
    if not key:
        return False
    if " " in key:
        return key in lower
    return re.search(rf"(?<![a-z0-9/+.#-]){re.escape(key)}(?![a-z0-9/+.#-])", lower) is not None
    return re.sub(r"\s+", " ", (keyword or "").strip().lower())


def lexicon_for_config(cfg: dict[str, Any] | None) -> list[str]:
    custom = list((cfg or {}).get("tech_lexicon") or [])
    seen: set[str] = set()
    out: list[str] = []
    for term in [*custom, *DEFAULT_TECH_LEXICON]:
        key = normalize_keyword(term)
        if key and key not in seen:
            seen.add(key)
            out.append(term.strip())
    return out


def job_text_blob(job: dict[str, Any]) -> str:
    parts = [
        job.get("role") or "",
        job.get("company") or "",
        job.get("search_role") or "",
        job.get("description_snippet") or "",
        job.get("title") or "",
    ]
    return "\n".join(p for p in parts if p)


def extract_role_keywords(
    text: str,
    *,
    lexicon: list[str] | None = None,
    extra_terms: list[str] | None = None,
) -> list[str]:
    """Return role requirement keywords found in text, longest matches first."""
    lower = (text or "").lower()
    terms = lexicon or list(DEFAULT_TECH_LEXICON)
    if extra_terms:
        terms = [*extra_terms, *terms]

    found: list[str] = []
    seen: set[str] = set()
    for term in sorted(terms, key=lambda t: len(normalize_keyword(t)), reverse=True):
        key = _canonical_keyword(normalize_keyword(term))
        if not key or key in seen:
            continue
        raw = normalize_keyword(term)
        if _term_matches(lower, raw):
            found.append(term.strip())
            seen.add(key)
    return found


def extract_role_keywords_for_job(job: dict[str, Any], cfg: dict[str, Any] | None = None) -> list[str]:
    lexicon = lexicon_for_config(cfg)
    return extract_role_keywords(job_text_blob(job), lexicon=lexicon)


def parse_pipe_skills(line: str, separator: str = " | ") -> list[str]:
    sep = separator or " | "
    return [part.strip() for part in line.split(sep) if part.strip()]


def split_headline_paragraph(text: str) -> tuple[str, str]:
    """Split headline paragraph into title block and skills line."""
    lines = [ln.rstrip() for ln in (text or "").split("\n")]
    while lines and not lines[-1].strip():
        lines.pop()
    if not lines:
        return "", ""
    if len(lines) == 1:
        return lines[0], ""
    return lines[0], lines[1]


def join_headline_paragraph(title_block: str, skills_line: str) -> str:
    title_block = (title_block or "").rstrip()
    skills_line = (skills_line or "").strip()
    if title_block and skills_line:
        return f"{title_block}\n{skills_line}"
    return title_block or skills_line


def display_keyword(keyword: str, existing: list[str]) -> str:
    target = normalize_keyword(keyword)
    for item in existing:
        if normalize_keyword(item) == target:
            return item.strip()
    if keyword.islower() and " " not in keyword:
        return keyword.upper() if len(keyword) <= 4 else keyword.title()
    return keyword.strip()


def merge_headline_skill_list(
    required: list[str],
    existing: list[str],
    *,
    max_skills: int | None = None,
) -> list[str]:
    """Requirements first, then existing skills; dedupe; optional cap."""
    seen: set[str] = set()
    merged: list[str] = []
    for kw in [*required, *existing]:
        key = _canonical_keyword(normalize_keyword(kw))
        if not key or key in seen:
            continue
        seen.add(key)
        merged.append(display_keyword(kw, existing))
        if max_skills and len(merged) >= max_skills:
            break
    return merged


def merge_headline_keywords(
    required: list[str],
    existing: list[str],
    *,
    separator: str = " | ",
    max_chars: int | None = None,
    max_skills: int | None = None,
) -> str:
    """Requirements first, then existing headline skills; dedupe; respect max length."""
    merged = merge_headline_skill_list(required, existing, max_skills=max_skills)
    sep = separator or " | "
    line = sep.join(merged)
    if max_chars and len(line) > max_chars:
        while len(merged) > 1 and len(sep.join(merged)) > max_chars:
            merged.pop()
        line = sep.join(merged)
    return line
