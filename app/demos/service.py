from datetime import timedelta
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.config import Settings
from app.demos.content import generate
from app.demos.renderer import render, template_for
from app.models import DemoSite, Lead, LeadState, is_expired, now
from app.places import client_for
from app.state_machine import transition


def source_for(lead: Lead) -> dict:
    if not lead.cache:
        raise ValueError("Lead cache is required before demo generation")
    if is_expired(lead.cache.expires_at):
        raise ValueError("Lead cache has expired; re-run search and enrichment before demo generation")
    p = lead.cache.payload
    phone = p.get("phone")
    address = p.get("address")
    hours = p.get("opening_hours")
    if not all([p.get("name"), phone, address, hours]):
        raise ValueError("Demo requires business name, phone, address, and opening hours")
    # Review body text is intentionally not copied from Places cache. Only explicitly
    # owner-approved review excerpts may be supplied here in a later fulfillment step.
    return {"business_name": p["name"], "category": p.get("category"), "formatted_address": address,
            "phone_e164": phone, "opening_hours": hours, "place_id": lead.place_id,
            "enrichment": {"public_contacts": p.get("public_contacts", [])}, "approved_reviews": []}


def approved_reviews_for(settings: Settings, lead: Lead) -> list[dict]:
    """Freshly obtain review text only for the current rendering request.

    Phase 1's cache never retains review body text. Generated quotes are retained in
    the audited demo JSON only when actually selected by the model.
    """
    details = client_for(settings).details(lead.place_id)
    result = []
    for review in details.get("reviews", [])[:5]:
        text = (review.get("text") or {}).get("text")
        author = review.get("authorAttribution") or {}
        if text and author.get("displayName"):
            result.append({"quote": text, "author_name": author["displayName"], "author_uri": author.get("uri"), "source": "Google review"})
    return result


def _url(settings: Settings, path: str) -> str:
    return settings.demo_preview_base_url.rstrip("/") + path


def _screenshot_svg(lead_data: dict) -> str:
    label = str(lead_data["business_name"]).replace("&", "and").replace("<", "")
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630"><rect width="100%" height="100%" fill="#eff5ff"/><text x="70" y="240" font-size="64" fill="#17212b">{label}</text><text x="70" y="320" font-size="32" fill="#2455a6">Demo preview — not yet live</text></svg>'


def deploy(settings: Settings, demo: DemoSite, page: str, slug: str) -> str:
    """Dry-run has a locally served preview. Live Cloudflare upload is deliberately gated."""
    if settings.dry_run or not settings.demo_deploy_enabled:
        return _url(settings, f"/api/v1/demos/{demo.id}/preview")
    if not all([settings.cloudflare_api_token, settings.cloudflare_account_id, settings.cloudflare_pages_project, settings.cloudflare_preview_domain]):
        raise RuntimeError("Cloudflare Pages credentials and preview domain are required when DRY_RUN=false")
    # Cloudflare's Direct Upload endpoint accepts the rendered index as a deployment file.
    # A custom preview hostname must be configured in Cloudflare before this is enabled.
    import httpx
    endpoint = f"https://api.cloudflare.com/client/v4/accounts/{settings.cloudflare_account_id}/pages/projects/{settings.cloudflare_pages_project}/deployments"
    response = httpx.post(endpoint, headers={"Authorization": f"Bearer {settings.cloudflare_api_token}"}, files={"index.html": ("index.html", page, "text/html")}, timeout=60)
    response.raise_for_status()
    result = response.json()
    if not result.get("success"):
        raise RuntimeError(f"Cloudflare deploy failed: {result.get('errors')}")
    return f"https://{slug}.{settings.cloudflare_preview_domain}"


def generate_demo(db: Session, settings: Settings, lead: Lead) -> DemoSite:
    if lead.state not in {LeadState.enriched, LeadState.demo_failed}:
        raise ValueError("Only enriched or failed-demo leads can generate a demo")
    if lead.state != LeadState.demo_generating:
        transition(db, lead, LeadState.demo_generating, "demo_requested")
    demo = db.scalar(select(DemoSite).where(DemoSite.lead_id == lead.id, DemoSite.status.in_(("retry_pending", "failed"))).order_by(DemoSite.created_at.desc()))
    if demo and demo.retry_count >= settings.demo_max_retries:
        raise ValueError("Demo retry cap reached")
    if not demo:
        template = template_for((lead.cache.payload if lead.cache else {}).get("category"))
        demo = DemoSite(lead_id=lead.id, template_name=template, expires_at=now() + timedelta(days=settings.demo_expiry_days))
        db.add(demo); db.flush()
    else:
        demo.status, demo.error_message, demo.next_retry_at = "generating", None, None
        demo.expires_at = now() + timedelta(days=settings.demo_expiry_days)
    template = demo.template_name
    try:
        source = source_for(lead)
        source["approved_reviews"] = approved_reviews_for(settings, lead)
        content = generate(settings, source)
        demo.content = content.model_dump(mode="json")
        page = render(content, source, template, demo.id, settings.google_maps_embed_api_key)
        slug = "-".join(c.lower() if c.isalnum() else "-" for c in source["business_name"]).strip("-")[:45] + "-" + demo.id[:8]
        demo.preview_url = deploy(settings, demo, page, slug)
        demo.screenshot_url = _url(settings, f"/api/v1/demos/{demo.id}/screenshot") if settings.dry_run or not settings.demo_deploy_enabled else capture_live_screenshot(settings, demo.preview_url)
        demo.status, demo.deployed_at = "ready", now()
        transition(db, lead, LeadState.demo_ready, "demo_deployed")
    except Exception as exc:
        demo.error_message = str(exc)
        demo.retry_count += 1
        if demo.retry_count >= settings.demo_max_retries:
            demo.status = "failed"
            transition(db, lead, LeadState.demo_failed, "demo_retry_cap_reached")
        else:
            demo.status = "retry_pending"
            demo.next_retry_at = now() + timedelta(minutes=2 ** demo.retry_count)
            transition(db, lead, LeadState.demo_failed, "demo_generation_failed")
        db.commit()
        raise
    db.commit(); db.refresh(demo)
    return demo


def expire_demos(db: Session, settings: Settings) -> int:
    rows = db.scalars(select(DemoSite).join(Lead).where(DemoSite.status == "ready", DemoSite.expires_at <= now(), Lead.state != LeadState.paid)).all()
    for demo in rows:
        # A live adapter would delete/unpublish the matching Cloudflare deployment here.
        demo.status, demo.unpublished_at = "expired", now()
    db.commit()
    return len(rows)


def retry_pending_demos(db: Session, settings: Settings) -> int:
    """Scheduler entry point; each retry keeps the same demo audit record and cap."""
    lead_ids = db.scalars(select(DemoSite.lead_id).where(DemoSite.status == "retry_pending", DemoSite.next_retry_at <= now())).all()
    completed = 0
    for lead_id in lead_ids:
        lead = db.scalar(select(Lead).where(Lead.id == lead_id))
        if not lead or lead.state != LeadState.demo_failed:
            continue
        try:
            generate_demo(db, settings, lead)
            completed += 1
        except Exception:
            pass  # Error, retry timestamp, and terminal state are persisted by generate_demo.
    return completed


def page_for(demo: DemoSite) -> str:
    from app.demos.content import DemoContent
    from app.config import get_settings
    return render(DemoContent.model_validate(demo.content), source_for(demo.lead), demo.template_name, demo.id, get_settings().google_maps_embed_api_key)


def screenshot_for(demo: DemoSite) -> str:
    return _screenshot_svg(source_for(demo.lead))


def capture_live_screenshot(settings: Settings, url: str) -> str:
    """Capture after deployment and send the PNG to a controlled uploader."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("Playwright is required for live demo screenshots") from exc
    if not settings.screenshot_upload_url:
        raise RuntimeError("SCREENSHOT_UPLOAD_URL is required for live demo screenshots")
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto(url, wait_until="networkidle", timeout=60_000)
        image = page.screenshot(full_page=True, type="png")
        browser.close()
    import httpx
    headers = {"Authorization": f"Bearer {settings.screenshot_upload_token}"} if settings.screenshot_upload_token else {}
    response = httpx.post(settings.screenshot_upload_url, headers=headers, files={"file": ("demo.png", image, "image/png")}, timeout=60)
    response.raise_for_status()
    screenshot_url = response.json().get("url")
    if not screenshot_url:
        raise RuntimeError("Screenshot uploader did not return a URL")
    return screenshot_url
