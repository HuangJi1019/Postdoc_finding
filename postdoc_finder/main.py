"""Entry point: fetch -> score/filter -> diff against store -> email -> persist.

Run modes:
  python -m postdoc_finder.main            # normal run, sends email on new jobs
  python -m postdoc_finder.main --dry-run  # print to stdout, send no email, no write
  python -m postdoc_finder.main --seed      # record current matches without emailing
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import yaml

from . import fetchers, notify, scoring, store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("postdoc_finder")

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = ROOT / "config.yaml"


def load_config(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def run(config_path: Path, dry_run: bool, seed: bool) -> int:
    cfg = load_config(config_path)
    store_path = ROOT / cfg.get("store_file", "seen_jobs.json")

    raw = fetchers.fetch_all(cfg["sources"])
    log.info("fetched %d raw entries", len(raw))

    matches = scoring.filter_jobs(
        raw,
        keywords={k: float(v) for k, v in cfg["keywords"].items()},
        role_terms=cfg.get("role_terms", []),
        area_threshold=float(cfg.get("area_threshold", 3.0)),
        require_postdoc_role=bool(cfg.get("require_postdoc_role", True)),
    )
    log.info("%d relevant match(es) after filtering", len(matches))

    seen = store.load(store_path)
    fresh = store.new_jobs(matches, seen)
    log.info("%d new since last run", len(fresh))

    max_items = int(cfg.get("max_email_items", 30))

    if dry_run:
        print(notify.render_text(fresh, max_items) if fresh else "No new matches.")
        return 0

    if not fresh:
        log.info("nothing new; no email sent")
        return 0

    if seed:
        log.info("seed mode: recording %d matches without emailing", len(fresh))
    else:
        # First real run with an empty store would email everything at once; cap it.
        if not seen:
            log.info("store empty (first run): sending capped digest of top %d", max_items)
        notify.send_digest(fresh, max_items)
        log.info("digest sent: %d position(s)", len(fresh))

    seen = store.record(fresh, seen)
    seen = store.prune(seen, int(cfg.get("retention_days", 120)))
    store.save(store_path, seen)
    log.info("store updated: %d ids tracked", len(seen))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Scrape and email new postdoc positions.")
    ap.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    ap.add_argument("--dry-run", action="store_true", help="print results, send nothing, write nothing")
    ap.add_argument("--seed", action="store_true", help="record current matches without emailing")
    args = ap.parse_args(argv)
    try:
        return run(args.config, args.dry_run, args.seed)
    except Exception as exc:
        log.error("run failed: %s", exc, exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
