# Compliance notes

This agent collects **publicly listed US business phone numbers** via official APIs first. Stay inside free/approved quotas and company permissions.

## Principles

1. Prefer structured APIs over scraping.
2. Never store API secrets in the database — only env var names.
3. Obey provider rate limits and safety buffers (`quota-tracking` rules).
4. Websites: crawl **only** when `source_type=website` and `allowed_params.authorized=true` with an allowlisted `base_url`.
5. Keep provenance (`source`, query, raw payload) on every phone record.

## Per-source notes (review against current ToS before production)

| Source | Notes |
|--------|--------|
| OpenStreetMap / Overpass / Nominatim | ODbL / attribution; polite use of public instances; set a real User-Agent. |
| Yelp Fusion | Display and usage restrictions in Yelp API Terms; limited free calls. |
| Google Places | Google Maps Platform Terms; SKU-based billing; phone fields may be higher-cost. |
| Foursquare Places | Foursquare API Terms; Pro endpoints often required for phones. |
| Geoapify | Follow Geoapify terms and daily free limits. |
| LocationIQ | OSM-backed; follow LocationIQ terms and rate limits. |
| TomTom | Search API key required; Maps SDK keys will not work. |
| DialCode | Free tier ~1k/month; carrier often null for NANP; risk data for reference. |
| Authorized websites | Explicit written company approval; respect robots/terms of that site; polite delays. |

Operators should re-check each provider’s current terms and internal legal approvals before going live.
