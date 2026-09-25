# SiteSpark

Lead discovery and enrichment for local Indian businesses. The default configuration is **dry-run only**: it uses deterministic mock Places results and makes no network requests, sends no messages, creates no payment links, and deploys nothing.

## Data retention

`leads` persists the Place ID and operational pipeline state. Google business-profile fields are stored only in `lead_caches.payload`, with `expires_at` set by `GOOGLE_PLACES_CACHE_TTL_DAYS` (default: 30). The service does not persist review body text or photo content—only photo references/attribution and review attribution metadata. Expired caches are excluded from metrics and must be refreshed from Places before use.

## Start locally

```powershell
Copy-Item .env.example .env
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/docs`.

Example safe run:

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/v1/lead-searches -ContentType application/json -Body '{"city":"Hyderabad","category":"salon","max_results":10}'
```

Enrich a returned lead with `POST /api/v1/leads/{lead_id}/enrich`, then inspect `GET /api/v1/metrics/leads`.

## Real Google Places mode

Set `DRY_RUN=false`, configure `GOOGLE_PLACES_API_KEY`, set a real `DATABASE_URL`, and review Google Maps Platform/Places terms, field-level storage restrictions, quota settings, and billing before running. The adapter calls only Places API v1 `places:searchText` and `places/{place_id}` endpoints. Configure production SKU cost accounting before enabling it; dry-run cost is zero.

## Tests

```powershell
pytest -q
```

The tests cover the dry-run pipeline, `enriched -> rejected`, reporting metrics, and local demo rendering. Payment, outreach, and fulfillment are not implemented in this MVP.

## Phase 2 demo sites

`POST /api/v1/leads/{lead_id}/demo` creates a local, no-cost preview by default. It
requires an enriched lead with name, phone, address, and opening hours. The preview
uses a category template, a live Place-ID map embed, masked reviewer names, and only
real review text fetched for the generation request. The previous Places cache does
not retain review body text or Google photo content.

The demo page is a preview: it provides phone and WhatsApp links but does not collect
or submit enquiry forms. Expired Places cache data cannot be used for enrichment or
demo generation; run a fresh search first. Live Places searches paginate up to the
requested limit (at most 60 results).

Set `DEMO_DEPLOY_ENABLED=true` only when a demo should be published. For live deployment
also set the LLM, Google Maps Embed, Cloudflare Pages, and screenshot uploader variables
in `.env`. The uploader must accept a multipart `file` and return
`{"url":"https://..."}`. Install Playwright's Chromium browser before live screenshots.
Run `celery -A app.tasks worker -B` to retry failed generations and unpublish unpaid
demos after 14 days.
