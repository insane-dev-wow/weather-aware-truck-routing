# Wayline — Weather-Aware Truck Routing

A Django + React web app that compares truck routes using forecast wind, rain, snow,
load weight, and estimated arrival time at each checkpoint. Wayline presents the route
comparison in a light dashboard with a map and a forecast timeline.

Enter an origin, destination, departure time, and load weight. The app seeks **three distinct
route options**, samples weather every **10 / 25 / 50 miles**, applies the assessment's risk
rules, and draws a **0–48 hour corridor forecast**. If the provider cannot supply three
reasonable alternatives, the app shows the available routes and an explicit warning.

| | |
|---|---|
| **App** | _Hosted frontend URL not recorded_ |
| **API** | _Hosted backend URL not recorded_ |
| **Source** | _GitHub URL for the current implementation not recorded_ |
| **Walkthrough** | _Loom recording pending; [script](docs/DEMO_SCRIPT.md) available_ |

> The default Valhalla, Open-Meteo, Photon, and Nominatim integrations need no API keys. Public services
> have usage limits. Photon provides autocomplete. Nominatim resolves submitted free text, with cached results and
> serialized requests at least one second apart; its [usage policy](https://operations.osmfoundation.org/policies/nominatim/)
> prohibits autocomplete. Keep the default public-geocoder deployment on one application host.

---

## Table of contents

- [What it does](#what-it-does)
- [Risk rules implemented](#risk-rules-implemented)
- [How the recommendation is made](#how-the-recommendation-is-made)
- [Architecture](#architecture)
- [Run locally](#run-locally)
- [API reference](#api-reference)
- [Testing](#testing)
- [Deployment](#deployment)
- [Project layout](#project-layout)
- [Notes and limitations](#notes-and-limitations)

---

## What it does

**Inputs**

- Origin and destination (type a place, then click its search icon to choose a result)
- Departure date/time (local; converted to UTC for the forecast)
- Exact load weight in pounds (numeric input, 0–80,000 lb)
- Weather sampling distance: 10, 25 or 50 miles

**Outputs**

- **Three route options where available** from Valhalla, with distance, drive time, and a corridor summary
  (`I 70 · US 40 · KS 23`).
- **Checkpoints** along each route at the chosen spacing. Each carries the forecast **at the
  truck's estimated arrival hour**: wind (mph), rain (in/hr), snow (in/hr), temperature,
  conditions, and the computed risk level.
- **A recommendation status** and reasons: recommended, blocked by No Travel, or insufficient forecast coverage.
- **Miles-by-risk breakdown** per route, including unassessed miles and forecast coverage.
- **An interactive map**: all returned routes, the selected route's checkpoints (click for a
  detail popup), and classified forecast cells from departure through **+48 hours**.

### Screens

The **Route planning** screen uses a compact horizontal form with a **Calculate routes** action.
A full-width **Route comparison** table sits above the full-width map. Rows follow the backend
ranking and show drive time, distance, peak risk, No-Travel/Severe/High miles, and average risk.
Choose a route with its native radio control or by clicking its row. On smaller screens, the
table scrolls horizontally.

**Recommended** appears once beside the eligible route. **Ranking rules** opens the rationale
in a **Route ranking** dialog. Blocked and insufficient-forecast results retain a warning
banner. Below the map, the selected-route summary shows departure, arrival, load, and forecast
coverage; **View details** expands the **Checkpoints** table.

Selecting another route changes the map highlight and its checkpoints. **Fit routes** frames
all alternatives; **Fit selected** frames the selected route. Origin and destination use **O**
and **D** markers, separate from route labels A, B, and C. The **Routing rules** dialog contains
the risk and load rules.

The **Weather** button toggles the overlay. Beneath the map, **Forecast +Nh** and its timestamp
identify the selected frame, followed by playback, the slider, and a compact risk legend.
The **Grid** checkbox shows cell outlines. Hiding weather pauses playback and disables the
forecast controls. Each polygon uses its sampled risk class directly; missing forecasts have
their own neutral color.

---

## Risk rules implemented

Weather at each checkpoint is banded, then the **worst** of the three threats applies.
Rain risk includes both the provider's rain and showers amounts. Wind uses mph and rain/snow
use inches per hour.

| Condition | Low | Moderate | High | Severe | No Travel |
|---|---|---|---|---|---|
| **Wind** | < 25 mph | 25–34 | 35–44 | 45–54 | ≥ 55 mph |
| **Rain** | < 0.10 in/hr | 0.10–0.25 | 0.25–0.50 | 0.50–1.00 | > 1.00 in/hr |
| **Snow** | < 0.5 in/hr | 0.5–1.0 | 1.0–2.0 | 2.0–3.0 | > 3.0 in/hr |

Load rules escalate a **wind-driven** level (they never lower it):

| Condition | Result |
|---|---|
| Wind ≥ 55 mph | **No Travel** for any load |
| Wind 45–54 mph **and** load > 30,000 lb | **No Travel** |
| Wind 35–44 mph **and** load > 40,000 lb | **Severe** |

The shared table has overlapping textual endpoints for rain and snow. The implementation
assigns 0.25 in/hr rain to High and 0.50 to Severe; 1.00 in/hr rain remains Severe. Likewise,
1.0 in/hr snow is High, 2.0 is Severe, and 3.0 remains Severe. Wind thresholds use continuous
half-open bands: 25 ≤ wind < 35, 35 ≤ wind < 45, and 45 ≤ wind < 55.

The engine lives in `backend/routing/services/risk.py` and `backend/routing/constants.py`.
Boundary tests cover these choices and the strict load comparisons: exactly 30,000 lb is
not escalated by the >30,000 rule; 30,001 lb is.

## How the recommendation is made

Only routes with complete arrival-time forecasts can receive a recommendation. Any No-Travel
checkpoint blocks that route, including a short segment whose displayed mileage rounds to zero.
Among fully assessed routes without No Travel, the preference order is:

1. Fewest **Severe** miles
2. Fewest **High** miles
3. Lowest **average risk score** (mean level score weighted by the corridor length each
   checkpoint owns)
4. Shortest **travel time**

Endpoint checkpoints own half of the adjacent segment; interior checkpoints own half of each
neighboring segment. Their weights sum to the sampled route length, so distance is not counted
twice. The average risk uses those same weights.

The API returns a rationale, comparison criteria, and one of three statuses:

| Status | Meaning |
|---|---|
| `recommended` | A fully assessed route without No Travel is selected. |
| `blocked` | Every fully assessed option includes No Travel. The least-risk option is identified for comparison, with a delay-departure warning. |
| `insufficient_forecast` | No route has complete coverage; `route_id` and `label` are `null`. |

Incomplete routes remain visible with `forecast_complete`, `forecast_coverage_pct`,
`known_miles`, `unknown_miles`, and scored-checkpoint counts. Missing data is never assigned
Low risk. When comparing blocked routes, fewest No-Travel miles precedes the four criteria above.

---

## Architecture

```
React (Vite + MapLibre GL)  ──HTTP/JSON──▶  Django REST (DRF)
                                             │
                    ┌────────────────────────┼─────────────────────────┐
                    ▼                        ▼                         ▼
           Photon / Nominatim           Valhalla (auto)           Open-Meteo
           (place suggestions / lookup) (route alternatives)     (hourly forecast, batched)
```

The backend is a pipeline of small, independently testable units:

```
geocoding → directions (up to 3 distinct candidates) → resample to checkpoints
          → batched forecast fetch → risk.classify per checkpoint
          → aggregate + rank → corridor heatmap → response
```

**Performance choices**

- Checkpoints and corridor cells share batched Open-Meteo requests, with 50 unique coordinates
  per batch and up to 2 workers by default. Forecast series are cached for 30 minutes.
- The heat map samples a **coarse grid inside a buffer around the routes** (not the whole
  bounding box), capped at 240 points by default to bound public-provider load, with a minimum 0.1° tile size. Each tile uses its own forecast sample;
  the denser grid reduces block size without inventing detail by subdividing old tiles.
- Route geometry is thinned to ~700 points before it hits the wire.
- MapLibre is **lazily loaded**. The client reuses polygon geometry and updates one forecast
  GeoJSON source per frame; playback does not rebuild map layers.

See [Architecture](docs/ARCHITECTURE.md) for weather interval handling, aggregation, and provider limits.

---

## Run locally

Use Python 3.12 and Node.js 20.19+ or 22.12+ for the current toolchain.

**Backend — http://127.0.0.1:8000**

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

**Frontend — http://127.0.0.1:5173**

```bash
cd frontend
npm ci
npm run dev
```

Vite proxies `/api` to `http://127.0.0.1:8000`, so no configuration is required. To point at a
deployed API instead, copy `frontend/.env.example` to `frontend/.env` and set `VITE_API_URL`.

A runnable plan needs outbound internet access to Valhalla, Open-Meteo, Photon, Nominatim, and map tiles.
Origin and destination suggest locations after two characters and a 200 ms pause. Exact-query
results are reused immediately from a bounded five-minute browser memory cache. Use the
arrow keys and Enter, or click a result; Escape closes the list. Stale requests are cancelled.
Suggestions use [Photon's search-as-you-type API](https://github.com/komoot/photon) and are cached
for an hour. Configure `PHOTON_URL` for a different Photon instance. Selected coordinates are
cached for planning; unselected free text is resolved through Nominatim only on **Calculate routes**.
The initial Denver–Kansas City values and all sample trips are resolved from the same
autocomplete API before filling the fields. Failed lookups leave existing values intact.
Resolved sample locations are cached in the browser for seven days. Startup lookup is
non-blocking and stops after four seconds; typing cancels it so late defaults cannot
overwrite edits. A first visit with a slow provider leaves the fields ready for manual search.
Request errors and validation messages appear as dismissible toast notifications; failed
route requests offer a Retry action. Critical No-Travel status remains in the route workspace.

Routing defaults to Valhalla with a primary route and two alternatives. If fewer than three
distinct usable paths remain, a second request uses the engine's shorter-distance preference.
Both requests contain only the actual origin and destination. Results are deduplicated and
checked for excessive duration, distance, and repeated road segments before weather ranking.

For a hosted Valhalla endpoint, configure `VALHALLA_BASE_URL` and `ROUTING_CLIENT_ID` in
`backend/.env`. The public demo is intended for light use: routing requests are cached for
30 minutes and spaced at least 1.1 seconds apart within the single application worker.
Keep one worker and one instance when using that endpoint. Before publishing against the
public demo, follow its [usage instructions](https://github.com/valhalla/valhalla#demo-server),
including an identifying client header and a notice to the maintainers. Use a managed or
self-hosted endpoint for larger deployments. Legacy OSRM remains opt-in via `ROUTING_PROVIDER=osrm`.

---

## API reference

### `GET /api/health/`

`{"status": "ok"}`

### `GET /api/thresholds/`

Returns the rule book (levels, wind/rain/snow bands with labels, load rules, and ranking order)
used by the Routing rules dialog.

### `GET /api/places/?q=chic`

Explicit place search. Called when the user clicks the location search icon, not on each
keystroke. Returns `{"results": [{"value": "...", "label": "Chicago, IL", "lat": ..., "lon": ...}]}`.
No matches returns an empty list; provider failure returns HTTP 502 with a `detail` message.

### `POST /api/route-plans/`

```json
{
  "origin": "Denver, CO",
  "destination": "Kansas City, MO",
  "depart_at": "2026-10-14T15:30:00Z",
  "load_lbs": 44000,
  "sample_interval_miles": 25,
  "heatmap_hours": 48
}
```

Use a departure within the available forecast window. The date and weather values below are
illustrative. Response fields (abridged to one route, checkpoint, and cell):

```json
{
  "id": 1,
  "origin": { "name": "Denver, Colorado, ...", "lat": 39.739, "lon": -104.985 },
  "destination": { "name": "Kansas City, Missouri, ...", "lat": 39.1, "lon": -94.58 },
  "routes": [
    {
      "id": "route-1",
      "label": "Route A",
      "summary": "I 70 · US 40",
      "distance_miles": 603.5,
      "duration_hours": 10.35,
      "geometry": [[39.739, -104.985], [39.1, -94.58]],
      "no_travel_miles": 0.0,
      "severe_miles": 0.0,
      "high_miles": 12.5,
      "avg_score": 0.041,
      "max_level": "high",
      "forecast_complete": true,
      "forecast_coverage_pct": 100.0,
      "known_miles": 603.5,
      "unknown_miles": 0.0,
      "scored_checkpoint_count": 26,
      "checkpoint_count": 26,
      "eligible_for_recommendation": true,
      "checkpoints": [
        {
          "index": 0, "mile": 0.0, "lat": 39.739, "lon": -104.985,
          "eta": "2026-10-14T15:30:00Z", "eta_label": "Wed Oct 14 · 15:30Z",
          "weight_miles": 12.5,
          "wind_mph": 21.4, "rain_in_hr": 0.0, "snow_in_hr": 0.0,
          "weather": "Partly cloudy", "level": "low", "score": 0.0,
          "headline": "Clear — no weather threats at this checkpoint",
          "factors": [ { "key": "wind", "value": 21.4, "unit": "mph", "level": "low" } ],
          "escalations": []
        }
      ]
    }
  ],
  "recommendation": {
    "status": "recommended",
    "route_id": "route-1",
    "label": "Route A",
    "headline": "Route A recommended",
    "reasons": ["Fewest severe-risk miles: 0 mi vs 46 mi on the next-best route."],
    "order": ["route-1", "route-2", "route-3"],
    "rank": { "route-1": 1, "route-2": 2, "route-3": 3 },
    "criteria": [ { "key": "severe_miles", "label": "Severe miles", "values": {}, "winner": "route-1" } ]
  },
  "heatmap": {
    "reference_time": "2026-10-14T15:30:00Z",
    "horizon_hours": 48,
    "hours": ["2026-10-14T15:30:00Z", "2026-10-14T16:30:00Z"],
    "cell_size_degrees": 0.25,
    "levels": ["low", "moderate", "high", "severe", "no_travel"],
    "colors": { "low": "#22c55e" },
    "radius_miles": 35,
    "bbox": [36.0, -106.0, 40.5, -93.0],
    "cells": [ { "lat": 39.2, "lon": -104.1, "scores": [0.0, null] } ]
  },
  "warnings": []
}
```

The full 48-hour response contains **49 frames**, starting at the exact departure minute and
ending at departure +48 hours. Every cell has one score per frame. `scores[i]` is an integer
class 0–4 at `hours[i]`; `null` means missing, incomplete, or out-of-range weather. The client
renders a neutral unknown class for null or invalid scores. `cell_size_degrees` defines the
grid polygons; their colors use each score directly.

### `GET /api/route-plans/<id>/`

Replays a saved plan (inputs + full result) from the database.

---

## Testing

```bash
cd backend
python manage.py test routing
```

The backend suite covers threshold boundaries, load escalation, distance conservation,
recommendation eligibility and ordering, missing data, rain plus showers, hourly precipitation
timing, the +48-hour endpoint, API behavior, route alternatives, and geocoder caching/throttling.
Provider-dependent cases use mocks.

Live routing checks on 2026-10-13 returned three distinct options for each sample trip:
Phoenix–Los Angeles, Denver–Kansas City, Chicago–Minneapolis, and Houston–New Orleans.
These checks used the final duplicate, duration, distance, and retracing filters. Provider
data can change; this is recorded verification, not a guarantee for every location pair.

```bash
cd frontend
npm test
npm run build
```

Frontend regression tests cover direct risk classes, unknown values, shared polygon
edges, the forecast-slider endpoint, autocomplete debounce, cancellation, errors, and actual
default-place selection. These are data-helper tests; visual browser
checks and a live-provider smoke test remain separate verification steps.

---

## Deployment

Deployment configuration is included; this local update does not publish an application.

`render.yaml` configures the Django API with backend root directory, `bash build.sh`, health
check `/api/health/`, and Gunicorn with one worker, four threads, and a 120-second worker timeout.
Weather and geocoding requests default to 10 seconds. Valhalla routing uses `ROUTING_TIMEOUT`
(15 seconds) and retries a timeout, connection failure, or HTTP 502/503/504 once. All attempts
respect the routing rate limiter; HTTP 429 is reported without automatic retries. There are
at most two alternative searches, each with at most two HTTP attempts.
The build installs dependencies, collects static files, and runs migrations.

During Render setup, supply:

- `CORS_ALLOWED_ORIGINS`: the exact frontend origin, without a trailing slash; comma-separate multiple origins.
- `GEOCODER_USER_AGENT`: a descriptive application identifier with a contact address.
- `ROUTING_CLIENT_ID`: a stable identifier for your deployed app, such as its domain name.

The blueprint generates `DJANGO_SECRET_KEY`, disables debug, enables trusted proxy HTTPS
handling, and uses `RENDER_EXTERNAL_HOSTNAME` for allowed hosts. For another host, set
`DJANGO_ALLOWED_HOSTS` explicitly and configure trusted origins if using the Django admin.

**Split hosting (recommended)**

| Surface | Host | Root / config |
|---|---|---|
| React UI | Vercel | **Root Directory = `frontend`** (uses `frontend/vercel.json`) |
| Django API | Render | `render.yaml` (`backend/`) |

In the Vercel project: Settings → General → Root Directory → `frontend`. Clear any custom
Install/Build overrides that still say `npm install --prefix frontend` (those assume the repo
root and fail when the root is already `frontend` or wrongly set to `backend`).

Use **two** Vercel projects (or Vercel UI + Render API). Example when the API is already on
Vercel at `https://weather-aware-truck-routing-green.vercel.app`:

1. Frontend project → Root Directory `frontend`.
2. Frontend → Settings → Environment Variables →  
   `VITE_API_URL` = `https://weather-aware-truck-routing-green.vercel.app`  
   (Production + Preview; no trailing slash). Redeploy so Vite inlines it.
3. Backend project keeps Root Directory `backend`. With `DJANGO_DEBUG=False`, either keep
   `CORS_ALLOW_ALL=False` (Vercel API builds already allow `*.vercel.app` via regex) or set
   `CORS_ALLOWED_ORIGINS` to the exact frontend origin.

Do **not** point the frontend project at `backend/` — that URL is the JSON API only.
Vite's development `/api` proxy is not part of the static production build.

SQLite is the local/demo default. Configure `DATABASE_URL` for persistent PostgreSQL;
`dj-database-url` and `psycopg[binary]` are included. A disposable filesystem does not preserve
saved plans across replacement or redeployment. WhiteNoise serves collected Django static files.

The Nominatim throttle uses `GEOCODER_RATE_LIMIT_DB`, a writable SQLite file shared by all
workers on one host. Keep one application instance with the public provider. Before scaling
across hosts, use a suitable geocoding provider or a centralized service with shared rate limits.

---

## Project layout

```
backend/
  config/                 Django project (settings, urls, wsgi/asgi)
  routing/
    constants.py          Risk bands, load thresholds, levels
    services/
      types.py            GeoPoint + time helpers
      geo.py              Haversine, resampling, polyline thinning
      geocoding.py        Photon autocomplete; Nominatim place lookup
      directions.py       Valhalla/OSRM alternatives + quality checks
      weather.py          Batched Open-Meteo fetch
      corridor.py         Heatmap grid inside the route buffer
      risk.py             Pure classification engine
      recommend.py        Route ranking and rationale
      heatmap.py          Corridor forecast frames
      planner.py          Pipeline orchestration
    models.py             RoutePlan (persisted plans)
    serializers.py        Request validation
    views.py / urls.py    API surface
    tests.py / test_*.py  Unit and provider regressions
frontend/
  src/
    theme.js              MUI theme
    lib/                  API, formatters, risk palette, map GeoJSON helpers
    hooks/                plan lifecycle, place search, forecast player, map height
    components/           planner, map, tables, panels, routing guide dialog
    styles/               globals + map
```

---

## Notes and limitations

- Forecast requests are capped at 16 days. Out-of-range, null, or missing risk inputs mark a
  checkpoint as "No forecast"; any such checkpoint excludes its route from recommendation.
- Travel time comes from the routing provider's estimated duration; hours-of-service scheduling is
  **not** modelled. Checkpoint ETAs spread that total time proportionally along route distance;
  they do not use per-road speeds. The driving profile does not model truck restrictions.
- Valhalla searches for three routes using standard and, when needed, shorter-distance costing;
  the app never inserts artificial waypoints to fill the count. Routes sharing at least 95%
  of the shorter path's full-geometry segments are treated as duplicates.
  Alternatives exceeding 1.55× the fastest usable route's distance or 1.5× its duration are
  excluded before weather ranking. Substantial repeated road segments are also rejected.
  Some locations have fewer than three usable road paths, and providers can fail. In those
  cases the response still reports the actual count rather than inventing options.
- The weather layer is a coarse classified forecast grid, not radar or a road-closure feed.
  Grid spacing coarsens to stay within the sample budget without leaving interior holes.
  Boundary tiles may extend beyond the corridor; missing forecasts remain marked unknown.
- All tests can pass while a public provider is unavailable or rate-limited. Hosted URLs and
  an actual 5–10 minute Loom recording remain separate submission deliverables.
- Planning aid only. Check official conditions and road closures before rolling.
