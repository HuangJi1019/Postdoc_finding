"""Persistence of already-notified job ids.

Stored as a JSON map { job_id: {title, url, first_seen} } so the file is human
readable and the GitHub Action can commit it back after each run. Old entries
are pruned after `retention_days` to keep the file from growing forever.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

from .models import Job

log = logging.getLogger("postdoc_finder.store")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load(path: str | Path) -> dict:
    p = Path(path)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("store load failed (%s); starting empty", exc)
        return {}


def new_jobs(jobs: list[Job], seen: dict) -> list[Job]:
    """Return only jobs whose id is not already in the store."""
    return [j for j in jobs if j.job_id not in seen]


def record(jobs: list[Job], seen: dict) -> dict:
    """Add jobs to the store with a timestamp. Mutates and returns `seen`."""
    ts = _now()
    for j in jobs:
        seen[j.job_id] = {"title": j.title, "url": j.url, "first_seen": ts}
    return seen


def prune(seen: dict, retention_days: int) -> dict:
    if retention_days <= 0:
        return seen
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    kept = {}
    for jid, meta in seen.items():
        raw = meta.get("first_seen", "")
        try:
            when = datetime.strptime(raw, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            kept[jid] = meta  # keep anything we can't parse rather than lose it
            continue
        if when >= cutoff:
            kept[jid] = meta
    return kept


def save(path: str | Path, seen: dict) -> None:
    p = Path(path)
    p.write_text(json.dumps(seen, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
