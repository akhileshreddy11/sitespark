from app.models import LeadState
from app.state_machine import ALLOWED


def test_dry_run_search_enrich_and_metrics(client):
    response = client.post("/api/v1/lead-searches", json={"city": "Hyderabad", "category": "salon", "max_results": 10})
    assert response.status_code == 201
    assert response.json()["leads_created"] == 2
    from app.db import SessionLocal
    from app.models import Lead
    db = SessionLocal(); leads = db.query(Lead).all(); db.close()
    outcomes = [client.post(f"/api/v1/leads/{lead.id}/enrich", json={}).json() for lead in leads]
    assert {x["state"] for x in outcomes} == {"enriched", "rejected"}
    report = client.get("/api/v1/metrics/leads").json()
    assert report["leads_found"] == 2
    assert report["public_email_percent"] == 50.0
    assert report["phone_percent"] == 50.0
    assert report["instagram_handle_percent"] == 50.0


def test_enriched_can_be_rejected_but_rejected_is_terminal():
    assert LeadState.rejected in ALLOWED[LeadState.enriched]
    assert not ALLOWED[LeadState.rejected]
