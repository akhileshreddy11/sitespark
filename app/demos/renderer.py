import html
import json

from app.demos.content import DemoContent

THEMES = {
    "clinic": ("#126782", "#e7f7fb"),
    "salon": ("#8a285b", "#fff0f6"),
    "gym": ("#b14b13", "#fff3eb"),
    "restaurant": ("#8a3b18", "#fff6e9"),
    "generic": ("#2455a6", "#eff5ff"),
}


def template_for(category: str | None) -> str:
    value = (category or "").lower()
    return next((name for name in THEMES if name in value), "generic")


def _e(value: object) -> str:
    return html.escape(str(value or ""), quote=True)


def _masked_name(name: str | None) -> str | None:
    if not name:
        return None
    words = name.strip().split()
    return words[0] + (f" {words[-1][0]}." if len(words) > 1 else "")


def render(content: DemoContent, lead_data: dict, template: str, demo_id: str, map_api_key: str = "") -> str:
    primary, pale = THEMES.get(template, THEMES["generic"])
    name, address, phone, hours, place_id = (
        lead_data[key]
        for key in ("business_name", "formatted_address", "phone_e164", "opening_hours", "place_id")
    )
    services = "".join(
        f"<li><strong>{_e(item.name)}</strong>{('<br>' + _e(item.description)) if item.description else ''}</li>"
        for item in content.services
    )
    testimonials = "".join(
        f"<figure><blockquote>&ldquo;{_e(item.quote)}&rdquo;</blockquote>"
        f"<figcaption>&mdash; {_e(_masked_name(item.author_name) or 'Verified reviewer')}</figcaption></figure>"
        for item in content.testimonials
    )
    faqs = "".join(
        f"<details><summary>{_e(item.question)}</summary><p>{_e(item.answer)}</p></details>"
        for item in content.faqs
    )
    hours_html = "<br>".join(_e(item) for item in (hours.get("weekdayDescriptions") or []))
    map_src = f"https://www.google.com/maps/embed/v1/place?key={_e(map_api_key)}&q=place_id:{_e(place_id)}"
    schema = {"@context": "https://schema.org", "@type": "LocalBusiness", "name": name,
              "address": address, "telephone": phone}
    schema_json = json.dumps(schema, ensure_ascii=False)
    schema_json = (schema_json.replace("<", "\\u003c").replace(">", "\\u003e")
                  .replace("&", "\\u0026").replace("\u2028", "\\u2028")
                  .replace("\u2029", "\\u2029"))
    title = content.seo.title or name
    description = content.seo.meta_description or f"Contact {name}."
    whatsapp = "https://wa.me/" + "".join(char for char in phone if char.isdigit())
    gallery_alt = content.seo.image_alt_text or f"{name} business image"
    about = f"<section><h2>About</h2><p>{_e(content.about)}</p></section>" if content.about else ""
    service_section = f'<section><h2>Services</h2><ul class="grid">{services}</ul></section>' if services else ""
    testimonial_section = f'<section><h2>What people say</h2><div class="grid">{testimonials}</div></section>' if testimonials else ""
    faq_section = f"<section><h2>FAQ</h2>{faqs}</section>" if faqs else ""
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_e(title)}</title><meta name="description" content="{_e(description)}">
<script type="application/ld+json">{schema_json}</script>
<style>:root{{--primary:{primary};--pale:{pale}}}*{{box-sizing:border-box}}body{{margin:0;font:16px system-ui;color:#17212b}}main,header,footer{{max-width:960px;margin:auto;padding:24px}}.banner{{background:#17212b;color:#fff;text-align:center;padding:10px}}header{{background:var(--pale)}}h1{{font-size:clamp(2rem,7vw,4rem)}}section{{padding:20px 0}}.grid{{display:grid;gap:16px;grid-template-columns:repeat(auto-fit,minmax(210px,1fr))}}li,figure,details{{background:#fff;border:1px solid #dde3e8;padding:16px;border-radius:10px;list-style:none}}a.button{{display:inline-block;background:var(--primary);color:#fff;padding:12px 18px;border-radius:8px;text-decoration:none;margin:4px}}iframe{{width:100%;min-height:300px;border:0}}@media(max-width:600px){{main,header{{padding:16px}}}}</style></head>
<body><div class="banner">Demo preview &mdash; not yet live. Placeholder domain only.</div>
<header><p>{_e(content.tagline)}</p><h1>{_e(content.headline or name)}</h1>
<a class="button" href="tel:{_e(phone)}">{_e(content.cta.primary_label)}</a>
<a class="button" href="{_e(whatsapp)}">{_e(content.cta.secondary_label)}</a></header>
<main>{about}{service_section}<section><h2>Gallery</h2><div class="grid"><img src="https://placehold.co/800x500?text={_e(template.title())}" alt="{_e(gallery_alt)}"></div><p>Illustrative category image; replace with owner-approved imagery.</p></section>
{testimonial_section}<section><h2>Opening hours</h2><p>{hours_html}</p></section>
<section><h2>Find us</h2><p>{_e(address)}</p><iframe title="Map for {_e(name)}" src="{map_src}" loading="lazy"></iframe></section>
{faq_section}<section><h2>{_e(content.cta.heading or 'Get in touch')}</h2><p>{_e(content.cta.body)}</p>
<p>Contact the business by phone or WhatsApp. This preview does not collect or send enquiry forms.</p></section></main>
<footer><small>Preview ID: {_e(demo_id)}</small></footer></body></html>'''
