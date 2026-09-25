from datetime import timedelta
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.config import Settings
from app.models import Lead, LeadCache, LeadState, SearchRun, is_expired, now
from app.places import client_for
from app.state_machine import transition


def expiry(settings: Settings):
    return now() + timedelta(days=settings.google_places_cache_ttl_days)


def summary_payload(place: dict) -> dict:
    """Temporary cache; do not put review body or image bytes here."""
    return {
        "name": place.get("displayName", {}).get("text"),
        "category": place.get("primaryType"),
        "address": place.get("formattedAddress"),
        "phone": place.get("nationalPhoneNumber"),
        "rating": place.get("rating"),
        "review_count": place.get("userRatingCount", 0),
        "google_maps_url": place.get("googleMapsUri"),
        "opening_hours": place.get("regularOpeningHours", {}),
        "photos": [],
        "review_attributions": [],
        "public_contacts": [],
    }


def cache(db: Session, lead: Lead, payload: dict, settings: Settings) -> None:
    if lead.cache:
        lead.cache.payload, lead.cache.expires_at, lead.cache.fetched_at = payload, expiry(settings), now()
    else:
        db.add(LeadCache(lead_id=lead.id, payload=payload, expires_at=expiry(settings)))


def run_search(db: Session, settings: Settings, city: str, category: str, max_results: int, min_rating: float, min_reviews: int, dry_run: bool) -> SearchRun:
    effective_settings = settings.model_copy(update={"dry_run": dry_run})
    run = SearchRun(city=city, category=category, max_results=max_results, min_rating_milli=round(min_rating * 1000), min_review_count=min_reviews, dry_run=dry_run, status="running")
    db.add(run); db.flush()
    try:
        places = client_for(effective_settings, city, category).text_search(city, category, max_results)
        run.pages_requested, run.places_seen = 1, len(places)
        # Cost is deliberately 0 for mock; production should use configured SKU pricing.
        for place in places:
            if place.get("websiteUri") or (place.get("rating") or 0) < min_rating or place.get("userRatingCount", 0) < min_reviews:
                continue
            run.leads_qualified += 1
            place_id = place["id"]
            lead = db.scalar(select(Lead).where(Lead.place_id == place_id))
            if not lead:
                lead = Lead(place_id=place_id, is_mock=dry_run)
                db.add(lead); db.flush(); run.leads_created += 1
            cache(db, lead, summary_payload(place), effective_settings)
        run.status = "completed"; db.commit()
    except Exception as exc:
        run.status, run.error_message = "failed", str(exc); db.commit(); raise
    return run


def _attribution_list(items: list[dict], limit: int) -> list[dict]:
    result = []
    for item in items[:limit]:
        author = item.get("authorAttributions") or item.get("authorAttribution") or {}
        if isinstance(author, list):
            author = author[0] if author else {}
        if isinstance(author, dict):
            result.append({"author_name": author.get("displayName"), "author_uri": author.get("uri"), "source": "Google Places"})
    return result


def score(payload: dict) -> tuple[int, dict]:
    contacts = payload.get("public_contacts", [])
    has_email = any(x.get("type") == "email" for x in contacts)
    has_phone = bool(payload.get("phone"))
    has_instagram = any(x.get("type") == "instagram" for x in contacts)
    quality = min(45, int((payload.get("rating") or 0) * 8) + min(10, (payload.get("review_count") or 0) // 20))
    contactability = (35 if has_email else 0) + (12 if has_phone else 0) + (8 if has_instagram else 0)
    completeness = 10 if payload.get("address") and payload.get("opening_hours") else 0
    total = min(100, quality + contactability + completeness)
    return total, {"business_quality": quality, "contactability": contactability, "completeness": completeness, "total": total}


def enrich(db: Session, settings: Settings, lead: Lead, dry_run: bool) -> Lead:
    if not lead.cache:
        raise ValueError("Lead has no cache record; re-run search before enrichment")
    if is_expired(lead.cache.expires_at):
        raise ValueError("Lead cache has expired; re-run search before enrichment")
    if lead.state in {LeadState.rejected, LeadState.demo_generating, LeadState.demo_ready,
                      LeadState.contacted, LeadState.replied,
                      LeadState.paid, LeadState.live, LeadState.churned, LeadState.unsubscribed}:
        raise ValueError(f"Cannot enrich a lead in the {lead.state.value} state")
    effective_settings = settings.model_copy(update={"dry_run": dry_run})
    details = client_for(effective_settings).details(lead.place_id)
    payload = dict(lead.cache.payload)
    payload["opening_hours"] = details.get("regularOpeningHours", payload.get("opening_hours", {}))
    payload["photos"] = _attribution_list(details.get("photos", []), 8)
    payload["review_attributions"] = _attribution_list(details.get("reviews", []), 5)
    contacts = []
    # Real connector intentionally has no public-web crawler: source adapters can be added with compliance review.
    if details.get("email"): contacts.append({"type": "email", "value": details["email"], "source": "public_listing_mock"})
    if details.get("instagram"): contacts.append({"type": "instagram", "value": details["instagram"], "source": "public_listing_mock"})
    payload["public_contacts"] = contacts
    lead.lead_score, payload["score_breakdown"] = score(payload)
    if lead.state == LeadState.demo_failed and lead.lead_score < settings.min_lead_score:
        raise ValueError("Lead score is below the minimum required for demo generation")
    cache(db, lead, payload, effective_settings)
    lead.enriched_at = now()
    if lead.lead_score < settings.min_lead_score:
        transition(db, lead, LeadState.rejected, "below_min_lead_score")
    elif lead.state == LeadState.found:
        transition(db, lead, LeadState.enriched, "meets_min_lead_score")
    db.commit(); db.refresh(lead)
    return lead


def metrics(db: Session) -> dict:
    # Metrics use active cache only, so expired Google profile data never participates.
    rows = db.execute(select(Lead.lead_score, LeadCache.payload).join(LeadCache).where(LeadCache.expires_at > now())).all()
    total = len(rows)
    def contact_ratio(kind: str) -> float:
        return round(100 * sum(any(x.get("type") == kind for x in (p.get("public_contacts") or [])) for _, p in rows) / total, 2) if total else 0.0
    phone = round(100 * sum(bool(p.get("phone")) for _, p in rows) / total, 2) if total else 0.0
    scores = [s for s, _ in rows if s is not None]
    return {"leads_found": db.scalar(select(func.count()).select_from(Lead)) or 0, "active_cached_leads": total, "public_email_percent": contact_ratio("email"), "phone_percent": phone, "instagram_handle_percent": contact_ratio("instagram"), "average_lead_score": round(sum(scores) / len(scores), 2) if scores else None}
