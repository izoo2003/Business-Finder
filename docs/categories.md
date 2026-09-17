# Categories

## Orchestration (Phase 7)

Configured via env / settings (defaults) and editable from the Scraper UI:

- `ORCHESTRATION_CITIES` — default seed `Austin,Dallas,Houston,San Antonio`
- `ORCHESTRATION_CATEGORIES` — default seed `restaurant,cafe`
- `ORCHESTRATION_LIMIT` — candidates per cycle (default 25)

Live lists are stored on `OrchestrationState` (`cities`, `categories`) and updated via
`PUT /api/scraper/orchestration/`. The scheduler prefers DB lists; empty DB falls back to settings.

The scheduler round-robins category then city (`OrchestrationState`).

## OpenStreetMap / Overpass

Mapped in `CATEGORY_TAG_MAP` inside [`acquisition/overpass.py`](../acquisition/overpass.py):

| Category | OSM tag |
|----------|---------|
| restaurant | amenity=restaurant |
| cafe | amenity=cafe |
| fast_food | amenity=fast_food |
| pharmacy | amenity=pharmacy |
| dentist | amenity=dentist |
| bank | amenity=bank |
| fuel | amenity=fuel |

Override with `--osm-tag key=value` on `fetch_overpass`.

## Provider-specific aliases

Geoapify / LocationIQ / TomTom / Yelp / Google / Foursquare each map free-text categories inside their client modules. Prefer simple labels (`restaurant`, `cafe`) so orchestration stays portable.
