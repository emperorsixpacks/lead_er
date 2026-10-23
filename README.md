# lead_er

Cold-email outreach pipeline: **discover → enrich → verify → personalize → send → track**.

Tracking is pixel-based and event-driven (no inbox polling): every sent email carries a
tracking pixel and wrapped links that hit a Cloudflare Worker, which writes the event to
Postgres via FastAPI and pushes a notification to your phone (ntfy).

## Architecture

```
Gmail API send → email contains pixel + wrapped links (one token per email)
   → recipient opens/clicks → Cloudflare Worker (t.yourdomain.com)
   → POST /events (FastAPI) → updates Postgres + ntfy push to your phone
```

The pipeline stages are plain async functions (`app/pipeline.py`), triggered via
HTTP endpoints (`/pipeline/*`) or the CLI (`scripts/run_pipeline.py`). No Celery, no Redis.

## Layout

```
app/
  main.py            FastAPI entry (health, /events, /leads, /pipeline/*)
  config.py          settings from env (.env)
  db.py              async SQLAlchemy engine + init (tables, full-text index)
  models.py          Lead, Email, Event
  pipeline.py        discover/enrich/verify/personalize/send
  api/               events.py, leads.py, pipeline.py
  services/          gmail, places, overpass, enrich, verifier, llm, tracking, notify
scripts/
  run_pipeline.py    CLI to run stages manually / from cron
worker/
  src/index.js       Cloudflare Worker: /o pixel, /c click, /u unsubscribe
```

## Quickstart

1. **Env**: `cp .env.example .env`, set `API_SECRET`, `NTFY_TOPIC`, `TRACKING_BASE_URL`,
   `SEND_FROM_EMAIL`, and your API keys (`GOOGLE_MAPS_API_KEY`, `ZEROBOUNCE_API_KEY`, `LLM_API_KEY`).

2. **DB**: `docker compose up -d postgres` (or point `DATABASE_URL` at any Postgres 14+).

3. **API**:
   ```
   pip install -r requirements.txt
   uvicorn app.main:app --reload
   ```
   Tables + full-text index are created on startup. The search dashboard is at `http://localhost:8000/`.

4. **Tracking Worker**: in `worker/`, install `wrangler`, set secrets, deploy:
   ```
   cd worker
   npx wrangler secret put API_URL      # https://your-api.example.com
   npx wrangler secret put API_SECRET   # must match .env API_SECRET
   npx wrangler secret put NTFY_TOPIC
   npx wrangler deploy
   ```
   Point `t.yourdomain.com` at the worker (route in `wrangler.toml` or dashboard).

5. **ntfy**: install the ntfy app on your phone, subscribe to `NTFY_TOPIC`.

6. **Gmail (SMTP app password)**: enable 2-Step Verification on your Gmail account,
   create an App Password at https://myaccount.google.com/apppasswords, and set
   `GMAIL_SMTP_USER` + `GMAIL_SMTP_PASSWORD` in `.env`.

7. **Discover & run**:
   ```
   python scripts/run_pipeline.py discover
   python scripts/run_pipeline.py run --limit 20
   ```
   Or hit `POST /pipeline/run` from anywhere. For daily discovery, add
   `python scripts/run_pipeline.py discover` to cron.

## Tracking endpoints

| Path              | Action                          |
|-------------------|---------------------------------|
| `/o/<token>.gif`  | records `open`, returns 1px GIF |
| `/c/<token>?u=..` | records `click`, 302 redirects  |
| `/u/<token>`      | records `unsub`, confirmation   |

The Worker signs each event with HMAC-SHA256 (`x-sig`); FastAPI verifies before writing.
Gmail's image proxy and prefetchers fire within seconds of send and are flagged `is_bot`.

## Compliance notes

- Every email includes an unsubscribe link and (when `SENDER_COMPANY`/`SENDER_ADDRESS`
  are set) a physical address — CAN-SPAM minimum.
- Bounces/unsubscribes set lead status to `bounced`/`unsub` and are suppressed in `send_lead`.
- Cold B2B email in the EU/UK needs a legitimate-interest basis under GDPR; Nigeria has NDPR.
  US B2B is generally CAN-SPAM only. Set `TARGET_COUNTRY` accordingly.
- Do not scrape LinkedIn (bans). The enrich crawler only reads the business's own site.
- Check ToS for Google Places/Overpass/Zerobounce usage.
