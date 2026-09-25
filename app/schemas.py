from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    city: str = Field(min_length=2, max_length=120)
    category: str = Field(min_length=2, max_length=120)
    max_results: int = Field(default=20, ge=1, le=60)
    min_rating: float = Field(default=3.8, ge=0, le=5)
    min_review_count: int = Field(default=10, ge=0)
    dry_run: bool | None = None


class EnrichRequest(BaseModel):
    dry_run: bool | None = None


class DemoRequest(BaseModel):
    dry_run: bool | None = None
