# Postdoc Finder

Scrapes academic job feeds, keeps the postings relevant to your research, and
emails you a digest of anything new. Runs itself on a schedule via GitHub
Actions. No server to maintain.

Tuned out of the box for video moment retrieval / multimodal / vision-language
research, sourcing from jobs.ac.uk (the main UK academic board).

## How it works

```
GitHub Actions (daily cron)
        │
        ▼
  fetch RSS feeds ──► normalize ──► keyword score + postdoc-role filter
        │                                      │
        │                                      ▼
        │                          diff against seen_jobs.json
        │                                      │
        │                              new postings only
        │                                      ▼
        │                             email digest (Gmail)
        ▼                                      │
  commit updated seen_jobs.json ◄──────────────┘
```

Each piece is isolated: a source that fails (network blip, feed change) is
logged and skipped, never aborting the run.

| File | Responsibility |
| --- | --- |
| `postdoc_finder/fetchers.py` | Fetch + parse each source (jobs.ac.uk HTML search; RSS) into `Job` objects |
| `postdoc_finder/models.py` | The unified `Job` shape, stable id, dedup keys |
| `postdoc_finder/scoring.py` | Weighted keyword score, role gate, dedup, sort |
| `postdoc_finder/store.py` | `seen_jobs.json` load/diff/record/prune |
| `postdoc_finder/notify.py` | Render and send the Gmail HTML digest |
| `postdoc_finder/main.py` | Orchestration + CLI |
| `config.yaml` | Everything tunable: sources, keywords, thresholds |

## One-time setup

1. **Secrets** (Settings → Secrets and variables → Actions → New repository secret):
   - `GMAIL_ADDRESS` — your Gmail address
   - `GMAIL_APP_PASSWORD` — a 16-char app password from
     <https://myaccount.google.com/apppasswords> (requires 2-step verification).
     Never use your account password.
   - Optional: `RECIPIENT` if you want the digest sent somewhere other than `GMAIL_ADDRESS`.

2. **Enable Actions** on the repo (Actions tab → enable workflows).

3. **Seed the store** so the first scheduled run doesn't email every currently
   open position at once. Go to Actions → `postdoc-finder` → Run workflow →
   mode `seed`. This records today's matches as "already seen" without emailing.
   From then on you only get genuinely new postings.

That's it. The workflow then runs daily at 07:00 UTC and emails you when new
matching positions appear.

## Test it locally first (recommended)

Do one real run from your Mac to confirm jobs.ac.uk fetches and the relevance
filter looks right before trusting the scheduled email:

```bash
pip install -r requirements.txt
python -m postdoc_finder.main --dry-run    # prints matches, sends nothing, writes nothing
```

If the dry run lists sensible positions, you're good. To test the email path,
export the two env vars and drop `--dry-run`.

## Tuning (`config.yaml`)

- **Keywords**: phrases with weights. Title hits count double. Add your own,
  reweight, or delete. Multi-word phrases are matched as substrings.
- **`area_threshold`**: minimum keyword score to keep a job. Raise to cut noise,
  lower (e.g. to 3) to widen the net.
- **`require_postdoc_role`**: when true, a job must also contain a term from
  `role_terms` (postdoc, research fellow, research associate, …). Set false to
  include lectureships etc.
- **`max_email_items`**: cap on positions listed per email (the rest are counted).
- **Weekly instead of daily**: change the cron in
  `.github/workflows/postdoc.yml` to `'0 7 * * 1'` (Mondays). The logic is identical.

## Adding a source

Sources live under `sources` in `config.yaml`. Two types:

**`jobs_ac_uk`** runs a keyword search on jobs.ac.uk and parses the rendered
listing (jobs.ac.uk retired its RSS feed, so the bot reads the HTML results
page with browser headers). Copy a block and change `keywords`:

```yaml
  - name: jobs.ac.uk · my topic
    type: jobs_ac_uk
    keywords: scene graph
    pages: 2          # pages of 25 results, newest first
    enabled: true
```

Each result folds the matched search term into its text, so that term's weight
in `keywords:` is what gets it past `area_threshold`. Keep the terms you search
for listed under `keywords:`.

**`rss`** is any standard RSS/Atom feed, kept for future sources:

```yaml
  - name: My Feed
    type: rss
    url: https://example.org/jobs.rss
    enabled: true
```

**Euraxess / Nature Careers**: left as a disabled `rss` placeholder. Their
portals moved and I could not confirm a clean public feed URL, so I did not ship
an unverified scraper. Paste a working feed URL and flip `enabled: true` if you
find one; a broken source just yields nothing rather than breaking the run.

## Notes

- **Cost**: free on a public repo; on a private repo a daily 1-2 min run uses
  well under the 2000 free Actions minutes/month.
- **State**: `seen_jobs.json` is committed back after each run by the workflow.
  Entries older than `retention_days` (default 120) are pruned automatically.
- **Credentials** live only in GitHub Secrets and are read from the environment;
  nothing is hardcoded or logged.
