import json
from typing import Any
import httpx
from pydantic import BaseModel, Field, ValidationError
from app.config import Settings


class Service(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=300)


class Testimonial(BaseModel):
    quote: str = Field(min_length=1, max_length=500)
    author_name: str | None = Field(default=None, max_length=100)
    source: str = "Google review"
    author_uri: str | None = None


class FAQ(BaseModel):
    question: str = Field(min_length=1, max_length=200)
    answer: str = Field(min_length=1, max_length=500)


class CTA(BaseModel):
    heading: str | None = Field(default=None, max_length=120)
    body: str | None = Field(default=None, max_length=300)
    primary_label: str = "Call us"
    secondary_label: str = "WhatsApp us"


class SEO(BaseModel):
    title: str | None = Field(default=None, max_length=60)
    meta_description: str | None = Field(default=None, max_length=160)
    image_alt_text: str | None = Field(default=None, max_length=160)


class DemoContent(BaseModel):
    headline: str | None = Field(default=None, max_length=120)
    tagline: str | None = Field(default=None, max_length=200)
    about: str | None = Field(default=None, max_length=800)
    services: list[Service] = Field(default_factory=list, max_length=12)
    testimonials: list[Testimonial] = Field(default_factory=list, max_length=5)
    faqs: list[FAQ] = Field(default_factory=list, max_length=6)
    cta: CTA = Field(default_factory=CTA)
    seo: SEO = Field(default_factory=SEO)


PROMPT = """You create accurate, concise website copy for a local-business demo. Return JSON only.
Use only the supplied business data. Do not infer or invent prices, discounts, years in
business, certifications, services, availability, claims, addresses, phone numbers, or
promises. Use null or [] when data is insufficient. Testimonials must be copied only
from approved_reviews, never paraphrased or invented, and retain their source fields.
Do not mention ratings, reviews, awards, or credentials unless supplied. Do not make
medical, legal, financial, performance, or outcome claims. This is a preview website.

Business data:\n{data}\n
Return this schema exactly:\n{schema}\n{repair}"""


def prompt_for(data: dict[str, Any], repair: str = "") -> str:
    return PROMPT.format(data=json.dumps(data, ensure_ascii=False), schema=json.dumps(DemoContent.model_json_schema()), repair=repair)


def safe_default(data: dict[str, Any]) -> DemoContent:
    """No-cost, source-grounded content used only in dry-run mode."""
    name, category = data.get("business_name"), data.get("category")
    headline = f"{name}" if name else None
    tagline = f"{category.title()} in your neighbourhood" if category else None
    testimonials = [Testimonial.model_validate(item) for item in data.get("approved_reviews", [])]
    return DemoContent(headline=headline, tagline=tagline, testimonials=testimonials, seo=SEO(title=name, meta_description=tagline, image_alt_text=f"{name or 'Business'} storefront"))


def generate(settings: Settings, source: dict[str, Any]) -> DemoContent:
    if settings.dry_run:
        return safe_default(source)
    if not settings.llm_api_key:
        raise RuntimeError("LLM_API_KEY is required when DRY_RUN=false")
    repair = ""
    last_error = "unknown validation error"
    for attempt in range(3):  # original call plus two schema-repair attempts
        response = httpx.post(f"{settings.llm_base_url}/chat/completions", headers={"Authorization": f"Bearer {settings.llm_api_key}"}, json={"model": settings.llm_model, "response_format": {"type": "json_object"}, "messages": [{"role": "user", "content": prompt_for(source, repair)}]}, timeout=45)
        response.raise_for_status()
        raw = response.json()["choices"][0]["message"]["content"]
        try:
            return DemoContent.model_validate_json(raw)
        except (ValidationError, ValueError) as exc:
            last_error = str(exc)
            repair = f"Your prior JSON failed validation: {last_error}. Correct it and return JSON only."
    raise RuntimeError(f"LLM output failed schema validation after 3 attempts: {last_error}")
