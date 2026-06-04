"""Unified job representation shared across all fetchers."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field, asdict
from html import unescape


def _strip_html(text: str) -> str:
    """Remove tags and collapse whitespace from an HTML/RSS description."""
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _canonical_url(url: str) -> str:
    """Drop query string and trailing slash so the same posting maps to one key."""
    if not url:
        return ""
    url = url.split("?", 1)[0].split("#", 1)[0]
    return url.rstrip("/")


def _norm_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (title or "").lower()).strip()


@dataclass
class Job:
    title: str
    url: str
    source: str
    institution: str = ""
    location: str = ""
    deadline: str = ""
    summary: str = ""
    published: str = ""
    score: float = 0.0
    matched: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.title = (self.title or "").strip()
        self.summary = _strip_html(self.summary)
        self.institution = (self.institution or "").strip()
        self.location = (self.location or "").strip()

    @property
    def job_id(self) -> str:
        """Stable per-posting id, based on the canonical URL when available."""
        basis = _canonical_url(self.url) or f"{self.source}:{_norm_title(self.title)}"
        return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:16]

    @property
    def dedup_key(self) -> str:
        """Secondary key to catch the same posting syndicated by two sources."""
        return f"{_norm_title(self.title)}|{(self.institution or '').lower().strip()}"

    @property
    def haystack(self) -> str:
        """Lowercased full text (title + body), used for role detection."""
        return f"{self.title} {self.institution} {self.summary}".lower()

    @property
    def body(self) -> str:
        """Lowercased text excluding the title, used for body keyword scoring."""
        return f"{self.institution} {self.summary}".lower()

    def to_dict(self) -> dict:
        return asdict(self)
