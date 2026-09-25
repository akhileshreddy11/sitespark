from app.db import SessionLocal
from app.models import DemoSite, Lead


def test_dry_run_demo_is_rendered_with_required_direct_lead_data(client):
    search = client.post("/api/v1/lead-searches", json={"city": "Hyderabad", "category": "salon"})
    assert search.status_code == 201
    db = SessionLocal(); lead = db.query(Lead).filter_by(place_id="mock-good-001").one(); lead_id = lead.id; db.close()
    assert client.post(f"/api/v1/leads/{lead_id}/enrich", json={}).status_code == 200
    response = client.post(f"/api/v1/leads/{lead_id}/demo", json={})
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "ready"
    page = client.get(body["preview_url"].replace("http://127.0.0.1:8000", ""))
    assert page.status_code == 200
    assert "Demo preview — not yet live" in page.text
    assert "+91 98765 43210" in page.text
    assert "place_id:mock-good-001" in page.text
    assert "Priya Sharma" not in page.text
    assert "Priya S." in page.text
    assert client.get(body["screenshot_url"].replace("http://127.0.0.1:8000", "")).headers["content-type"].startswith("image/svg+xml")
    db = SessionLocal(); demo = db.query(DemoSite).filter_by(id=body["id"]).one(); assert demo.content; db.close()
