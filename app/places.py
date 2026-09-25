"""Official Google Places API adapter and deterministic no-network mock."""
from typing import Protocol
import httpx
from app.config import Settings


class PlacesClient(Protocol):
    def text_search(self, city: str, category: str, max_results: int) -> list[dict]: ...
    def details(self, place_id: str) -> dict: ...


class MockPlacesClient:
    def __init__(self, city: str, category: str):
        self.city, self.category = city, category

    def text_search(self, city: str, category: str, max_results: int) -> list[dict]:
        rows = [
            {"id": "mock-good-001", "displayName": {"text": f"Sunrise {category.title()}"}, "formattedAddress": f"12 Market Road, {city}", "rating": 4.6, "userRatingCount": 52, "websiteUri": None, "nationalPhoneNumber": "+91 98765 43210", "googleMapsUri": "https://maps.google.com/?cid=mock-good-001"},
            {"id": "mock-low-score-002", "displayName": {"text": f"Neighbourhood {category.title()}"}, "formattedAddress": f"8 Lake View, {city}", "rating": 4.0, "userRatingCount": 14, "websiteUri": None, "nationalPhoneNumber": None, "googleMapsUri": "https://maps.google.com/?cid=mock-low-score-002"},
            {"id": "mock-has-site-003", "displayName": {"text": f"Online {category.title()}"}, "formattedAddress": f"3 Station Road, {city}", "rating": 4.7, "userRatingCount": 91, "websiteUri": "https://example.test", "nationalPhoneNumber": "+91 90000 00000"},
        ]
        return rows[:max_results]

    def details(self, place_id: str) -> dict:
        common = {"regularOpeningHours": {"weekdayDescriptions": ["Monday: 9:00 AM – 7:00 PM"]}}
        if place_id == "mock-good-001":
            return common | {"photos": [{"name": "places/mock-good-001/photos/1", "authorAttributions": [{"displayName": "Business owner"}]}], "reviews": [{"authorAttribution": {"displayName": "Priya Sharma"}, "text": {"text": "Warm service and a very clean space."}, "publishTime": "2026-01-01T00:00:00Z", "rating": 5}], "email": "hello@sunrise.example", "instagram": "@sunrise_local"}
        return common | {"photos": [], "reviews": [], "email": None, "instagram": None}


class GooglePlacesClient:
    """Uses Google Places API v1 endpoints, never Maps HTML scraping."""
    SEARCH_FIELDS = "places.id,places.displayName,places.formattedAddress,places.rating,places.userRatingCount,places.websiteUri,places.nationalPhoneNumber,places.googleMapsUri,places.primaryType"
    DETAIL_FIELDS = "id,displayName,formattedAddress,nationalPhoneNumber,websiteUri,rating,userRatingCount,regularOpeningHours,photos,reviews,googleMapsUri"

    def __init__(self, settings: Settings):
        if not settings.google_places_api_key:
            raise ValueError("GOOGLE_PLACES_API_KEY is required when DRY_RUN=false")
        self.base_url, self.key = settings.google_places_base_url, settings.google_places_api_key

    def text_search(self, city: str, category: str, max_results: int) -> list[dict]:
        headers = {"X-Goog-Api-Key": self.key, "X-Goog-FieldMask": self.SEARCH_FIELDS}
        places: list[dict] = []
        page_token = None
        while len(places) < max_results:
            body = {"textQuery": f"{category} in {city}, India", "pageSize": min(max_results - len(places), 20)}
            if page_token:
                body["pageToken"] = page_token
            response = httpx.post(f"{self.base_url}/places:searchText", headers=headers, json=body, timeout=20)
            response.raise_for_status()
            result = response.json()
            places.extend(result.get("places", []))
            page_token = result.get("nextPageToken")
            if not page_token or not result.get("places"):
                break
        return places[:max_results]

    def details(self, place_id: str) -> dict:
        headers = {"X-Goog-Api-Key": self.key, "X-Goog-FieldMask": self.DETAIL_FIELDS}
        response = httpx.get(f"{self.base_url}/places/{place_id}", headers=headers, timeout=20)
        response.raise_for_status()
        return response.json()


def client_for(settings: Settings, city: str = "", category: str = "") -> PlacesClient:
    return MockPlacesClient(city, category) if settings.dry_run else GooglePlacesClient(settings)
