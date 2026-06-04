"""Fetchers turn external sources into a flat list of Job objects.

Two source types are supported, dispatched by the `type` field in config.yaml:
  - "jobs_ac_uk": parse the jobs.ac.uk HTML search-results page (its RSS feed
    was retired, so we read the rendered listing). Requires browser-like headers.
  - "rss": any standard RSS/Atom feed via feedparser (kept for future sources).

A failure in one source is logged and swallowed so it never aborts the run.
"""

from __future__ import annotations

import logging
import socket
import time
from urllib.parse import quote_plus
from urllib.request import Request, urlopen

import feedparser
from bs4 import BeautifulSoup

from .models import Job

log = logging.getLogger("postdoc_finder.fetchers")

# A full browser User-Agent + Accept-Language is required: jobs.ac.uk returns
# 500/redirects to bare programmatic requests.
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
}
_TIMEOUT = 30
_JOBS_AC_UK = "https://www.jobs.ac.uk"


def _download(url: str) -> bytes:
    """Fetch raw bytes with browser-like headers (urllib follows redirects)."""
    req = Request(url, headers=_HEADERS)
    with urlopen(req, timeout=_TIMEOUT) as resp:
        return resp.read()


# --------------------------------------------------------------------------- #
# jobs.ac.uk HTML search                                                       #
# --------------------------------------------------------------------------- #

def _text(node) -> str:
    return node.get_text(strip=True) if node else ""


def _parse_jobs_ac_uk(html: str, source: str, keywords: str) -> list[Job]:
    """Parse one jobs.ac.uk search-results page into Job objects."""
    soup = BeautifulSoup(html, "html.parser")
    jobs: list[Job] = []
    for card in soup.select("div.j-search-result__result"):
        anchor = card.select_one("div.j-search-result__text a[href^='/job/']")
        if not anchor:
            continue
        title = _text(anchor)
        href = anchor.get("href", "")
        if not title or not href:
            continue
        url = _JOBS_AC_UK + href
        department = _text(card.select_one(".j-search-result__department"))
        employer = _text(card.select_one(".j-search-result__employer"))
        loc_div = card.find(
            lambda t: t.name == "div" and t.get_text(strip=True).startswith("Location:")
        )
        location = _text(loc_div)[len("Location:"):].strip() if loc_div else ""
        closes = card.select_one(".j-search-result__date--blue")
        deadline = f"Closes {_text(closes)}" if closes else ""
        # Department + the matched search term go into the summary. The listing
        # page has no full description, so folding the matched query in lets the
        # scorer credit the relevance jobs.ac.uk already established server-side.
        summary = department
        if keywords:
            summary = f"{department}. Matched jobs.ac.uk search: {keywords}."
        jobs.append(
            Job(
                title=title,
                url=url,
                source=source,
                institution=employer,
                location=location,
                deadline=deadline,
                summary=summary,
            )
        )
    return jobs


def fetch_jobs_ac_uk(name: str, keywords: str, pages: int = 2, page_size: int = 25) -> list[Job]:
    """Fetch the first `pages` pages of a jobs.ac.uk keyword search (newest first)."""
    out: list[Job] = []
    for p in range(pages):
        start = p * page_size + 1
        url = (
            f"{_JOBS_AC_UK}/search/?keywords={quote_plus(keywords)}"
            f"&sortOrder=1&pageSize={page_size}&startIndex={start}"
        )
        try:
            html = _download(url).decode("utf-8", errors="ignore")
        except (OSError, socket.timeout) as exc:
            log.warning("source %s: page %d download failed (%s)", name, p + 1, exc)
            break
        page_jobs = _parse_jobs_ac_uk(html, name, keywords)
        if not page_jobs:
            break  # no more results
        out.extend(page_jobs)
        if p + 1 < pages:
            time.sleep(1)  # be polite between page requests
    log.info("source %s: %d entries", name, len(out))
    return out


# --------------------------------------------------------------------------- #
# Generic RSS (kept for future sources such as Euraxess)                       #
# --------------------------------------------------------------------------- #

def _entry_field(entry, *names: str) -> str:
    for n in names:
        val = entry.get(n)
        if val:
            return str(val)
    return ""


def fetch_rss(name: str, url: str) -> list[Job]:
    """Fetch one RSS/Atom feed and normalize entries into Job objects."""
    try:
        raw = _download(url)
    except (OSError, socket.timeout) as exc:
        log.warning("source %s: download failed (%s)", name, exc)
        return []
    parsed = feedparser.parse(raw)
    if parsed.bozo and not parsed.entries:
        log.warning("source %s: feed did not parse (%s)", name, parsed.get("bozo_exception"))
        return []
    jobs: list[Job] = []
    for entry in parsed.entries:
        title = _entry_field(entry, "title")
        link = _entry_field(entry, "link")
        if not title or not link:
            continue
        jobs.append(
            Job(
                title=title,
                url=link,
                source=name,
                institution=_entry_field(entry, "author"),
                summary=_entry_field(entry, "summary", "description"),
                published=_entry_field(entry, "published", "updated", "pubDate"),
            )
        )
    log.info("source %s: %d entries", name, len(jobs))
    return jobs


# --------------------------------------------------------------------------- #
# Dispatch                                                                     #
# --------------------------------------------------------------------------- #

def fetch_all(sources: list[dict]) -> list[Job]:
    """Run every enabled source; isolate failures per source."""
    out: list[Job] = []
    for src in sources:
        if not src.get("enabled", True):
            continue
        name = src.get("name", "unknown")
        stype = src.get("type", "rss")
        try:
            if stype == "jobs_ac_uk":
                out.extend(
                    fetch_jobs_ac_uk(
                        name,
                        keywords=src.get("keywords", ""),
                        pages=int(src.get("pages", 2)),
                    )
                )
            elif stype == "rss":
                if src.get("url"):
                    out.extend(fetch_rss(name, src["url"]))
            else:
                log.warning("source %s: unknown type %r", name, stype)
        except Exception as exc:  # defensive: one bad source must not abort the run
            log.warning("source %s: unexpected error (%s)", name, exc)
    return out
