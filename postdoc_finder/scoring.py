"""Relevance scoring and filtering.

Two independent signals:
  1. area score  - weighted research-keyword match against the user's field
  2. role gate   - whether the posting looks like a postdoc / research role

A job is kept when its area score clears the threshold AND (if required) it
looks like a postdoc role. Titles are weighted more heavily than body text.
"""

from __future__ import annotations

from .models import Job

TITLE_MULTIPLIER = 2.0


def _count_phrase(haystack: str, phrase: str) -> int:
    """Substring count; phrases are already lowercased."""
    if not phrase:
        return 0
    return haystack.count(phrase)


def score_job(job: Job, keywords: dict[str, float], role_terms: list[str]) -> Job:
    title = job.title.lower()
    body = job.body
    total = 0.0
    matched: list[str] = []

    for phrase, weight in keywords.items():
        p = phrase.lower()
        in_title = _count_phrase(title, p)
        in_body = _count_phrase(body, p)
        if in_body or in_title:
            matched.append(phrase)
        # title hits get the multiplier; body adds at most one more hit per phrase
        total += weight * in_title * TITLE_MULTIPLIER
        total += weight * min(in_body, 1)

    job.score = round(total, 2)
    job.matched = matched
    job._is_role = any(term.lower() in job.haystack for term in role_terms)  # type: ignore[attr-defined]
    return job


def filter_jobs(
    jobs: list[Job],
    keywords: dict[str, float],
    role_terms: list[str],
    area_threshold: float,
    require_postdoc_role: bool,
) -> list[Job]:
    """Score, gate, dedup, and sort. Returns highest-relevance first."""
    seen_id: set[str] = set()
    seen_dedup: set[str] = set()
    kept: list[Job] = []

    for job in jobs:
        score_job(job, keywords, role_terms)
        if job.score < area_threshold:
            continue
        if require_postdoc_role and not getattr(job, "_is_role", False):
            continue
        if job.job_id in seen_id or job.dedup_key in seen_dedup:
            continue
        seen_id.add(job.job_id)
        seen_dedup.add(job.dedup_key)
        kept.append(job)

    kept.sort(key=lambda j: j.score, reverse=True)
    return kept
