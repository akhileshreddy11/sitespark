from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.config import get_settings
from app.db import Base, engine, get_db
from app.models import Lead
from app.schemas import DemoRequest, EnrichRequest, SearchRequest
from app.demos.service import expire_demos, generate_demo, page_for, retry_pending_demos, screenshot_for
from app.models import DemoSite
from app.services import enrich, metrics, run_search


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine())
    yield


app = FastAPI(title="SiteSpark", version="0.1.0", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok", "dry_run": get_settings().dry_run}


@app.post("/api/v1/lead-searches", status_code=201)
def create_search(request: SearchRequest, db: Session = Depends(get_db)):
    settings = get_settings()
    dry_run = settings.dry_run if request.dry_run is None else request.dry_run
    if not dry_run and settings.dry_run:
        raise HTTPException(403, "Set DRY_RUN=false in environment before real Places requests")
    run = run_search(db, settings, request.city, request.category, request.max_results, request.min_rating, request.min_review_count, dry_run)
    return {"id": run.id, "status": run.status, "places_seen": run.places_seen, "leads_qualified": run.leads_qualified, "leads_created": run.leads_created, "estimated_cost_usd_micros": run.estimated_cost_usd_micros}


@app.post("/api/v1/leads/{lead_id}/enrich")
def enrich_lead(lead_id: str, request: EnrichRequest, db: Session = Depends(get_db)):
    lead = db.scalar(select(Lead).where(Lead.id == lead_id))
    if not lead: raise HTTPException(404, "Lead not found")
    settings = get_settings()
    dry_run = settings.dry_run if request.dry_run is None else request.dry_run
    if not dry_run and settings.dry_run:
        raise HTTPException(403, "Set DRY_RUN=false in environment before real Places requests")
    try:
        lead = enrich(db, settings, lead, dry_run)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    return {"id": lead.id, "place_id": lead.place_id, "state": lead.state, "lead_score": lead.lead_score}


@app.get("/api/v1/metrics/leads")
def lead_metrics(db: Session = Depends(get_db)):
    return metrics(db)


@app.post("/api/v1/leads/{lead_id}/demo", status_code=201)
def create_demo(lead_id: str, request: DemoRequest, db: Session = Depends(get_db)):
    lead = db.scalar(select(Lead).where(Lead.id == lead_id))
    if not lead: raise HTTPException(404, "Lead not found")
    settings = get_settings()
    dry_run = settings.dry_run if request.dry_run is None else request.dry_run
    if not dry_run and settings.dry_run:
        raise HTTPException(403, "Set DRY_RUN=false before live demo generation")
    try:
        demo = generate_demo(db, settings.model_copy(update={"dry_run": dry_run}), lead)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    except Exception as exc:
        raise HTTPException(502, str(exc))
    return {"id": demo.id, "status": demo.status, "template": demo.template_name, "preview_url": demo.preview_url, "screenshot_url": demo.screenshot_url, "expires_at": demo.expires_at}


@app.get("/api/v1/demos/{demo_id}/preview", response_class=Response)
def demo_preview(demo_id: str, db: Session = Depends(get_db)):
    demo = db.scalar(select(DemoSite).where(DemoSite.id == demo_id))
    if not demo: raise HTTPException(404, "Demo not found")
    return Response(page_for(demo), media_type="text/html")


@app.get("/api/v1/demos/{demo_id}")
def get_demo(demo_id: str, db: Session = Depends(get_db)):
    demo = db.scalar(select(DemoSite).where(DemoSite.id == demo_id))
    if not demo: raise HTTPException(404, "Demo not found")
    return {"id": demo.id, "lead_id": demo.lead_id, "status": demo.status, "content": demo.content,
            "template": demo.template_name, "preview_url": demo.preview_url, "screenshot_url": demo.screenshot_url,
            "retry_count": demo.retry_count, "next_retry_at": demo.next_retry_at, "expires_at": demo.expires_at,
            "error_message": demo.error_message}


@app.get("/api/v1/demos/{demo_id}/screenshot", response_class=Response)
def demo_screenshot(demo_id: str, db: Session = Depends(get_db)):
    demo = db.scalar(select(DemoSite).where(DemoSite.id == demo_id))
    if not demo: raise HTTPException(404, "Demo not found")
    return Response(screenshot_for(demo), media_type="image/svg+xml")


@app.post("/api/v1/jobs/expire-demos")
def run_demo_expiry(db: Session = Depends(get_db)):
    return {"expired": expire_demos(db, get_settings())}


@app.post("/api/v1/jobs/retry-demos")
def run_demo_retries(db: Session = Depends(get_db)):
    return {"retried": retry_pending_demos(db, get_settings())}
