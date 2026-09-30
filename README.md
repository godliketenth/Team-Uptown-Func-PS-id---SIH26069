# NWAP — National Weather Analytics Platform (Prototype)

A working, end-to-end prototype of a national multi-source weather intelligence
system: collect from many sources → normalize → geocode → classify →
corroborate against real observed weather → deduplicate → score reliability →
cluster into events → serve → visualize on a live operational console.

Everything below runs on a laptop, and it runs with **zero infrastructure by
default** — Postgres and nothing else. Kafka, MinIO and Spark are real and
wired in, each behind a config switch that is off unless you set it, so the
project never *requires* a broker to start. See
[Prototype vs full-scale](#prototype-vs-full-scale) for what is genuinely
running, what is substituted, and the measurements behind each choice.

---

## Quick start

Up in about a minute. For a step-by-step setup on a clean machine, a demo
script and a troubleshooting table, see **[START.md](START.md)** — this section
is the short version.

### 1. Database (PostgreSQL 16 + PostGIS)

```bash
docker compose up -d db
```

> No Docker? Any local PostgreSQL 16/17 with the `postgis` extension works.
> Create a matching database and the default `DATABASE_URL` still applies:
> ```bash
> createdb weather
> psql -d weather -c "CREATE EXTENSION IF NOT EXISTS postgis;"
> psql -d postgres -c "CREATE ROLE postgres LOGIN SUPERUSER PASSWORD 'postgres';"
> ```

### 2. Backend

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # defaults already point at the compose database
alembic upgrade head          # schema + PostGIS and pgvector extensions
python seed.py                # 7 sources + 3 demo users         (idempotent)
python seed_authorities.py    # 15 authorities for alert routing (idempotent)
python fetch_model.py         # optional: ~118MB ONNX model for semantic dedup
uvicorn app.main:app --reload --port 8000
```

API docs: <http://localhost:8000/docs> · health: <http://localhost:8000/health>

> `seed_authorities.py` is easy to skip and awkward to debug: without it alerts
> are raised correctly but have nobody to route to, so the delivery panel sits
> empty and looks like a bug.

Ingestion starts on boot. Within ~8 seconds the first raw events land; within
about a minute you will see multi-report events with rising severity.

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

Console: <http://localhost:5180> (Vite proxies `/api` to port 8000).

> The port is pinned with `strictPort`, so a collision fails loudly instead of
> silently starting the console somewhere else.

### Demo accounts

| Email | Password | Role | Can do |
|---|---|---|---|
| `admin@demo.in` | `admin123` | ADMIN | everything, including pausing sources |
| `verifier@demo.in` | `verifier123` | VERIFIER | verify / reject events |
| `analyst@demo.in` | `analyst123` | ANALYST | read admin views, change nothing |

The public dashboard requires no login at all — a warning nobody can read
without an account is not a warning.

---

## What to look at first

1. **The map fills in.** Pins appear as the scheduler ticks every 8 seconds. New
   pins ripple once. Pin fill = event type, pin ring = verification status, pin
   size = severity.
2. **An event clusters and escalates.** Within a minute or two one city gets a
   burst of reports from several different source types. Watch a single pin grow
   as `report_count` rises and its status walks `DETECTED → CORROBORATING →
   NEEDS_REVIEW`.
3. **Open it.** Click the pin. The slide-over shows the evidence *behind* the
   status — report count, source count, weather corroboration, source diversity,
   every contributing report, and the full status history.
4. **Triage it.** Sign in as the verifier, go to **Admin → Verification Queue**
   (weakest evidence first) and verify or reject. The verdict lands in the audit
   log and the pipeline will never overwrite it.
5. **See what got flagged.** **Admin → Credibility** is the fake/misleading
   surface: the rollup of which signals are firing, and every flagged report with
   the named reasons it tripped — a heatwave claim the observed temperature
   contradicts, or off-topic chatter with no weather terms at all.
6. **Follow a hashtag.** The **Hashtag monitor** in the bottom strip shows which
   tracked tags are carrying traffic. `GET /api/v1/reports?hashtag=IMD` filters
   the intake to one tag.
7. **Watch the plumbing.** **Admin → System Health** shows the bus, the per-stage
   pipeline breakdown, error rate and the raw-lake object count.

---

## Architecture

```
      ┌──────────────── collectors, each on its own poll interval ───────────────┐
      │  StubConnector (synthetic)   OpenMeteoConnector (real)                  │
      │                              SatelliteConnector (real cloud cover)      │
      └────────────────────────────────┬────────────────────────────────────────┘
                                             │  append-only
                                    ┌────────▼────────┐        ┌──────────────────┐
                                    │   raw_events    │───────▶│ data/raw/<type>/ │
                                    │ (immutable log) │        │  YYYY/MM/DD/*.json│
                                    └────────┬────────┘        └──────────────────┘
                                             │  publish id
                                    ┌────────▼────────┐
                                    │ asyncio bus     │  (stands in for Kafka)
                                    └────────┬────────┘
                                             │
  normalize → geo → classify → corroborate → dedupe → reliability → credibility → event_engine
       │       │        │           │           │          │             │             │
   hashtags  PostGIS  keyword   Open-Meteo   3-stage    weighted    fake/misleading  ST_DWithin
   + lang     point    scores     (real)      match      score          flags        15km/90m
                                             │
                                    ┌────────▼────────┐
                                    │ reports, events │──▶ FastAPI ──▶ React console
                                    └─────────────────┘      (5s poll)
```

### The pipeline, stage by stage

| Stage | What it does | Where |
|---|---|---|
| **normalize** | extract **hashtags** (#IMD and a tracked watchlist), mentions, URLs and author; collapse whitespace, sha256 hash, language guess by Unicode script (hi/gu/bn/ta/en) | `pipeline/normalize.py` |
| **geo** | ~65 Indian cities → lat/lon/district/state. GPS wins when present (confidence 1.0), city match jitters ±0.05° (0.6), otherwise unresolved (0.3) | `pipeline/geo.py` |
| **classify** | **trained logistic-regression head over sentence embeddings**, falling back to keyword scoring when the model is absent | `pipeline/classify.py` |
| **corroborate** | real Open-Meteo hourly precipitation / temperature / wind / humidity at the report's location and hour, cached per (0.1°, hour) | `pipeline/corroborate.py` |
| **dedupe** | 1) same source + external id 2) identical text hash 3) **semantic** embedding similarity ≥ 0.82 **and** within 10km (PostGIS) **and** within 30 minutes | `pipeline/dedupe.py` |
| **reliability** | `0.30·source_trust + 0.30·weather + 0.20·nearby_sources + 0.20·location_confidence` | `pipeline/reliability.py` |
| **credibility** | fake / misleading detection: named, weighted flags (contradicted by observation, uncorroborated, low-trust source, unresolved location, no weather signal, duplicate) → 0-1 misinformation risk | `pipeline/credibility.py` |
| **event_engine** | attach to an open event of the same type within 15km / 90 minutes, else create one; recompute counts, evidence, severity, status | `pipeline/event_engine.py` |

Each stage advances `reports.processing_state`, which is what the admin health
view reports — the stage breakdown is measured, not decorative.

### Event lifecycle

```
DETECTED ──(2nd source)──▶ CORROBORATING ──(3rd source)──▶ NEEDS_REVIEW
                                                                │
                                              verifier ─────────┼──▶ VERIFIED
                                                                └──▶ REJECTED
              no new reports for 6h ─────────────────────────────────▶ RESOLVED
```

Severity comes from report volume: `<5` LOW, `<15` MODERATE, `<30` HIGH, else
SEVERE. The engine only ever *escalates* automatically, and never overwrites a
human verdict.

### Hashtag tracking

`#IMD` and a watchlist of weather tags (`#rain`, `#flood`, `#thunderstorm`,
`#heatwave`, `#fog`, `#duststorm`, `#monsoon`, `#waterlogging`, `#mausam`,
`#ndma`, …) are extracted per report, lowercased and de-duplicated, and stored
on the row. Tags on the watchlist are marked `tracked` and rendered in the
event-type hue; incidental tags (`#MumbaiRains`, `#heatalert`) are kept but
shown muted. `GET /analytics/hashtags` ranks them by volume with the event type
each one predominantly carries.

The hashtag markers are stripped for text comparison but the words survive, so
`#MumbaiRains` still reads as rain signal to the classifier.

### Identifying fake and misleading reports

`pipeline/credibility.py` turns the signals the pipeline already computed into
named, weighted flags:

| Flag | Raised when | Weight |
|---|---|---|
| `CONTRADICTED_BY_OBSERVATION` | observed weather **actively opposes** the claim | 0.40 |
| `NO_WEATHER_SIGNAL` | classifier found no weather term at all | 0.25 |
| `UNCORROBORATED` | no independent source reporting nearby | 0.20 |
| `LOW_TRUST_SOURCE` | source trust at or below 0.55 (social) | 0.15 |
| `UNRESOLVED_LOCATION` | location could not be geocoded | 0.10 |
| `DUPLICATE_CONTENT` | collapsed into an earlier report | 0.10 |

Contradiction deliberately requires *active disagreement*, not merely absent
support: a coarse model grid cell reading 0mm does not disprove street-level
waterlogging, because rain is intensely local. Claiming a heatwave where the
observed temperature is 24 °C, or fog where visibility is 24 km, does.

Risk is the summed weight, capped at 1.0; at or above 0.50 a report is flagged
for review, and its event carries a `flagged_report_count`. Every flag is shown
with the reason that raised it — a reviewer argues with a specific claim, never
with an opaque score.

### Learned relevance signal

The credibility stage's `NO_WEATHER_SIGNAL` flag now uses a trained model
rather than a heuristic — and the reason is a bug worth recording.

**The regression.** That flag originally detected off-topic posts by checking
whether the hazard classifier returned a *flat* score distribution: no keyword
matched, so every class scored equally. When classification became a trained
softmax over seven hazard classes (Phase 1.1), that assumption silently broke.
A softmax has no "none of the above" option, so *"anyone know when the power
comes back"* came back as **THUNDERSTORM at 98% confidence** and the flag
stopped firing entirely — **0 times over 90 minutes**, against 1,311 before.

The Phase 1.1 evaluation never caught it because it only ever tested weather
reports. The training set had no irrelevant class, so nothing measured what the
model did with irrelevant input.

**The fix.** Relevance is now its own question, answered by its own model:
embeddings → "is this a weather report at all?". Text-only by design — source
trust and corroboration are already the rule flags' job, and mixing them in
would mean a well-written report from an untrusted source got marked
irrelevant.

| Detector | Precision | Recall | F1 |
|---|---|---|---|
| Keyword fallback | 0.344 | **1.000** | 0.512 |
| **Trained model** | **1.000** | 0.875 | **0.933** |

Precision is what matters here: wrongly calling a genuine report irrelevant
suppresses real signal, which is worse than missing one off-topic post. The
keyword detector never misses but wrongly flags ~1% of genuine reports.

**Generalisation was measured, not assumed.** Six off-topic phrasings are held
out of training entirely — including romanised Hinglish and Devanagari — and
the model catches **6 of 6**, at p=0.67 to p=1.00.

Measured live: **100% of off-topic reports flagged, 1.5% false positives on
genuine reports.** The old rule caught 42%.

#### What this model does not do

It answers *"is this a weather report?"*, **not** *"is this weather claim
true?"*. There are zero human verifier decisions recorded, so no ground truth
for genuine falsehood exists. A plausible but false report of flooding in a dry
district is not something this catches — that needs verifier decisions
accumulated over time, at which point the same script retrains on real labels.

It is also a **second signal, not a replacement**. The six named flags stay,
because an operator in a disaster needs to know *why* something was doubted and
a single opaque score cannot tell them.

Two earlier attempts were wrong in instructive ways, both recorded in
`training/train_credibility.py`:

1. Labels were inferred from a missing `intended_event_type`, which swept in
   every satellite and weather-API observation — the **most trustworthy sources
   in the system** — and labelled them not credible. It scored a perfect 100%,
   because it had learned to recognise INSAT bulletins.
2. The generator's off-topic pool was **four fixed sentences**, making the task
   memorisable rather than learnable. It is now 32 varied posts spanning
   transport, civic complaints, daily life, Hinglish and native scripts.

### Preparedness analytics

The historical view a disaster-management body plans against: which districts
are hit repeatedly, by what hazard, and how fast the platform flags it.
Available at `GET /analytics/preparedness` and **Admin → Preparedness**.

- **District risk profile**, ranked by alert burden rather than raw event
  count — three RED alerts matter more to a planner than thirty quiet events.
- **Hazard mix** per district, so a district that floods is distinguishable
  from one that mostly reports fog.
- **Hour-of-day distribution** in IST, stacked by hazard.
- **Detection lead time** — minutes from an event's first report to its first
  alert.

**It states its own limits.** The coverage note reports the real data span, and
says plainly that seasonal and monsoon-cycle analysis needs a year of data and
is not available. Detection lead time excludes alerts raised more than 3 hours
after their event began, because those are backfill artefacts rather than real
detection — which currently leaves the metric empty rather than showing a
flattering but meaningless number.

#### The generator now models time of day

Building this surfaced a flaw worth fixing: the generator picked event types
without regard to the clock, so fog never clustered at dawn and heatwaves never
peaked at midday. Every hour looked identical, which would have made the
hour-of-day chart noise presented as insight.

The generator now weights hazard selection by **hour of day in IST** — fog
peaks 04:00–07:00, heat 11:00–15:00, convective storms 15:00–19:00, flooding
lagging the rain that causes it. Measured at 08:00 IST the new intake is
RAIN/FLOOD/FOG heavy with heat and dust suppressed, as it should be.

Hazard *type* is weighted rather than timestamps being backdated, because
reports must stay recent for clustering to work.

### Public advisory text

Every event can produce a publishable bulletin: what is happening, where, how
confident we are, and what people should do — in **English and Hindi**, with
safety guidance drawn from standard NDMA/IMD public advice per hazard.

**Deliberately template-based, not model-generated.** A language model that
invents safety instructions in a disaster bulletin is a hazard, not a feature.
Every sentence is fixed text with evidence-driven slots, so output is
deterministic, auditable, and can be reviewed and signed off in advance by the
people whose name goes on it.

Confidence is derived from **corroboration, not volume** — a hundred copies of
one claim is not stronger evidence than three independent ones — and the
bulletin states its own evidence inline:

```
[RED] Heavy rainfall — Bengaluru Urban, Karnataka

WHAT TO DO:
  • Avoid low-lying and waterlogged areas.
  • Do not shelter under trees or near electric poles.
  • Allow extra travel time and drive slowly.

CONFIDENCE: HIGH — This advisory is supported by multiple independent sources.
EVIDENCE: 46 reports from 5 independent sources; reliability 63%,
          observed-weather agreement 44%.
```

If a quarter or more of the contributing reports are flagged for credibility,
the advisory says so rather than hiding it.

Advisories are **computed on demand, never stored** — derived text written once
goes stale the moment the event moves, a mistake this codebase already made
three times with warning levels, alerts and deliveries.

Available at `GET /events/{id}/advisory` and `GET /alerts/{id}/advisory`, and
from the **Advisory** button in the alert queue with a copy-to-clipboard
bulletin.

### Routing alerts to authorities

An alert nobody receives is half a system. The `authorities` registry decides
who is told, and matching is **hierarchical and deliberately over-inclusive** —
telling one authority twice is far cheaper than leaving a district uninformed:

| Authority level | Receives |
|---|---|
| `NATIONAL` | every alert |
| `STATE` | every alert in its state |
| `DISTRICT` | only its own district (state must also match — district names repeat) |

Each authority narrows further by **event type** (Ahmedabad's Heat Action Cell
subscribes only to `HEATWAVE` and `DUST_STORM`) and by **minimum warning
level** (the IMD National Weather Desk is configured for RED only).

Every `(alert × authority × channel)` gets its own `alert_deliveries` row, so a
partial failure is visible — *"the webhook went through but the SMS did not"* is
operationally different from *"nobody was told"*.

**What is genuinely delivered.** Webhook delivery is a **real HTTP POST** —
verified end to end against a local receiver: 48 deliveries sent, all HTTP 202,
carrying the full alert with its frozen evidence. Email and SMS have **no
transport configured** in this build, so they are recorded as `SIMULATED` with
the exact payload that would have gone out, and the reason stored on the row:
*"no transport configured — payload recorded, not sent"*. They are never marked
`SENT`, and never `FAILED` either — "we cannot send" is not "we tried and it
broke".

To see real delivery, point any authority at a URL:

```bash
curl -X PATCH localhost:8000/api/v1/admin/authorities/<id> \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"webhook_url":"https://webhook.site/your-id"}'
```

Dispatch runs on its own 15-second scheduler job, **separate from ingestion**, so
a slow or unreachable webhook can never stall data collection. Failures retry up
to 3 times before being marked `FAILED`.

### Alerting — where the platform asks someone to act

An event reaching **ORANGE or RED** raises an alert. YELLOW is a watch: worth
showing on the dashboard, not worth paging a district officer about.

| Rule | Why |
|---|---|
| **One live alert per event** | A rising level escalates the existing alert in place rather than raising a second one, so a worsening situation does not bury an operator in duplicates |
| **Alerts are closed, never deleted** | Someone told to prepare deserves to be told it stood down, with a reason |
| **Evidence is frozen at raise time** | Events keep changing; the alert records what was true when the call was made, so it stays auditable |
| **Acknowledge ≠ close** | ACKNOWLEDGED means a human has seen it, CLOSED means it no longer applies — conflating them would hide open work |
| **Escalation re-opens** | An acknowledged alert that escalates returns to ACTIVE, because it now needs fresh attention |

Role split: **analysts can acknowledge**, only **verifiers can stand an alert
down**. Both actions are written to the audit log.

The queue lives at **Admin → Alert Queue**, ordered most severe first then
oldest — the order an operator actually works down — with a live count badge
that follows them across every admin screen.

### IMD-style warning levels

Every event carries a four-colour warning level on **IMD's published bulletin
scale**, because that is the vocabulary a district officer already acts on:

| Level | Meaning | Action |
|---|---|---|
| 🟢 GREEN | No warning | No action needed |
| 🟡 YELLOW | Watch | Be updated |
| 🟠 ORANGE | Alert | Be prepared |
| 🔴 RED | Warning | Take action |

**IMD derives these colours from forecast intensity thresholds** (rainfall
mm/day, temperature departure, wind speed). This platform does not forecast —
it aggregates and verifies reports. So the vocabulary and actions follow IMD
while **the trigger logic is ours**, derived from accumulated evidence, and the
UI says exactly that wherever a level is shown.

Volume alone never reaches ORANGE: a crowd repeating itself is not
corroboration, so independent source count and evidence quality gate the upper
levels. Two caps hold a level down — a human REJECTED/RESOLVED verdict drops it
to GREEN, and an event whose reports are mostly flagged for credibility cannot
exceed YELLOW.

Notably, a **low corroboration score does not cap the level**. Absence of
support is not contradiction — the same reasoning applied in the credibility
stage. Only genuine contradiction, surfaced through the flagged-report ratio,
holds a warning down.

On the map, **pin size now encodes warning level** rather than raw report
volume, so the largest marks are the ones needing action rather than merely the
noisiest.

### Event classification

Classification runs a logistic-regression head over the same sentence
embeddings used for deduplication, trained on 23,491 labelled reports. The
exported weights are 12KB and inference is a single numpy matmul, so
scikit-learn is a **training-time dependency only** and never ships in the
serving path. The vector computed for dedup is reused, so each report is
embedded once.

Two evaluations, because only the second is informative:

| Evaluation | Keyword rules | Embedding model |
|---|---|---|
| Held-out split of the synthetic corpus | 95.72% | **99.98%** |
| Hand-written realistic reports | **40.00%** | **65.00%** |

The first benchmark is near-circular: the generator writes the very keywords
the rules search for, so both score high and neither number means much. The
second set (`training/eval_realistic.py`) is written the way people actually
post — implicit phrasing, Hinglish, misspellings, negation traps — and none of
it comes from the generator's templates.

The rules collapse there because they fall back to a flat prior when no keyword
matches, which resolves to RAIN. The model reads *"roads have turned into
rivers"* as FLOOD, *"AC running non stop and still sweating"* as HEATWAVE, and
*"No rain today despite the forecast, just heat"* as HEATWAVE rather than being
fooled by the word "rain".

**Both remain weak on romanised Hinglish** ("bohot paani bhar gaya hai") — a
shared blind spot worth stating plainly, since XLM-R sees little romanised
Hindi. Native Devanagari and Gujarati are handled well.

Blending the two scorers was measured and did **not** beat the model alone, so
it is not done.

Retrain with:

```bash
python training/train_classifier.py
```

### Semantic deduplication

Stage 3 of dedup runs on sentence embeddings rather than character overlap. A
quantized multilingual MiniLM (~118MB) runs under **ONNX Runtime** — chosen over
`sentence-transformers` because PyTorch would add ~2GB and this containerises
cleanly. Vectors live in a pgvector `vector(384)` column and are searched by
cosine distance inside the existing 10km / 30min window.

The model is **multilingual by necessity**: an English-only encoder scored a
Hindi translation of a report no higher than an unrelated sentence (0.189 vs
0.189), which would have silently defeated this stage on a third of the intake.

The 0.82 threshold was calibrated on real intake, not guessed:

| Pair type (measured inside the 10km / 30min window) | Cosine | difflib scored |
|---|---|---|
| Same report syndicated across sources | 0.93 – 0.95 | 0.73 – 0.85 |
| Same event, different wording | 0.86 – 0.88 | **0.448** |
| Cross-language restatement | 0.845 – 0.849 | **0.386** |
| p90 of genuinely independent pairs | 0.785 | — |

Measured effect: the dedup rate is unchanged (~34%) and events still accumulate
3–7 independent sources, but character-level fallbacks disappeared entirely and
matches now include pairs `difflib` could not see — such as *"Smog and fog mix
cutting visibility in Patna"* against *"Fog layer persisting past sunrise in
Patna"*.

The model is optional: without `backend/models/`, stage 3 falls back to
`difflib` and nothing else changes.

### Why "evidence over verdicts"

A green check on its own asks to be trusted rather than earning it. Every
place the UI shows a status it also shows what produced it: how many reports,
how many independent sources, how strongly real observed weather agreed, and
which sources contributed at what reliability. That breakdown component is
shared by the public slide-over and the admin drawer so the two can never drift.

---

## Design language — "Situation Room"

A calm, high-density operational console, not a marketing page.

- **Dark by default** (`#0B0F14` base, `#121821` panels, `#1E2A38` hairlines).
  A light toggle exists; dark is the working default.
- **The map is the anchor** and is never permanently covered — detail arrives as
  a right-side slide-over.
- **Two independent colour scales, never mixed.** Event type owns one hue each
  (rain `#3B82F6`, flood `#0EA5E9`, thunderstorm `#8B5CF6`, heatwave `#F97316`,
  fog `#94A3B8`, dust storm `#CA8A04`, strong wind `#14B8A6`); verification
  status owns a separate neutral scale (grey / yellow / green / red / blue-grey).
  On a map pin, type is the fill and status is the ring.
- **Colour is never the only channel** — every event type also carries a glyph,
  because flood and rain sit close on the hue wheel.
- **Inter for UI, JetBrains Mono for every number**, ID, coordinate and
  timestamp. This is most of what makes it read as an ops tool.
- **Density over whitespace**: 8px grid, 1px borders instead of shadows, small
  caps section labels.
- **Live-feeling without websockets**: 5s polling, new pins ripple once, new
  feed rows flash once.
- **Admin is a mode, not another app**: same tokens, same components; the map
  recedes and tables take over because the job changes from browsing to triage.

---

## API

| Group | Endpoints |
|---|---|
| Reports | `POST /api/v1/reports` (202, async pipeline) · `GET /reports` · `GET /reports/{id}` |
| Events | `GET /events` · `GET /events/{id}` · `GET /events/{id}/reports` |
| Map | `GET /map/events` · `GET /map/reports` (bbox-filtered, lightweight) |
| Analytics | `GET /analytics/summary` · `/timeline` · `/by-state` · `/hashtags` · `/credibility` |
| Verification | `GET /verification/queue` · `POST /verification/{id}/verify` · `/reject` · `/resolve` |
| Admin | `GET /admin/sources` · `PATCH /admin/sources/{id}` · `GET /admin/system-health` · `/audit-logs` |
| Auth | `POST /auth/login` · `GET /auth/me` |

Roles: public dashboard needs none; `/admin/*` needs ANALYST or higher;
verify/reject needs VERIFIER or higher; source changes need ADMIN.

Submit a citizen report yourself:

```bash
curl -X POST localhost:8000/api/v1/reports -H 'Content-Type: application/json' \
  -d '{"text":"Heavy waterlogging near Dadar station Mumbai","city":"Mumbai"}'
```

---

## Synthetic data generator

There is no production access to social or citizen platforms yet, so
`services/ingestion/generator.py` produces realistic traffic: 3–12 items per
tick weighted CITIZEN 40% / SOCIAL 30% / WEATHER_API 15% / GOVERNMENT 10% /
WEB_RSS 5%, drawn from ~65 Indian cities biased toward eight "hot" ones, with
region-appropriate event types (no heatwaves in Srinagar), Hindi and Gujarati
templates so language detection has real input, hashtags (`#IMD` plus event- and
city-specific tags), attributable authors, photo/video attachments, 10%
duplicates so dedup visibly catches something, and periodic multi-source bursts
so clustering and severity escalation actually happen on camera.

Roughly 75% of generated reports are anchored to the weather Open-Meteo actually
observes at that city (`dominant_condition`), so corroboration carries real
information. The remaining quarter are genuinely unsupported claims — which is
what gives the credibility stage something true to find.

Two details exist purely to keep the demo honest: burst reports rotate through
distinct templates (identical texts in one city inside 30 minutes would be
collapsed by dedup, starving the very cluster the burst exists to show), and
they rotate through source types (three independent sources is what escalates an
event to NEEDS_REVIEW).

Open-Meteo is the one genuinely real feed — both as corroboration for every
report and as its own connector emitting observations when a metro actually
crosses a threshold.

---

## Tests

```bash
cd backend && python -m pytest -q      # 35 tests, ~4s, no infrastructure needed
```

Two files, and the split is deliberate:

- **`tests/test_regressions.py`** — one test per bug this project actually
  shipped and fixed. Each is written from the *measurement that exposed the
  bug*, not from the fix, so it fails against the old code rather than merely
  restating the new code. Verified by reverting each fix and watching the
  matching test fail.
- **`tests/test_domain.py`** — the rules the platform exists to enforce:
  warning thresholds, what may cap a level, why absence of corroboration is
  not contradiction, the lake's fallback and partition contract, bus transport
  reporting, and the live-update fan-out.

The suite needs no database, broker, object store or ML model — every rule
worth protecting here is a pure decision. It passes on a checkout with no
`.env` and no `backend/models/`, which is exactly what CI gets.

## Optional: the big data stack

None of this is needed to run the platform — it starts on Postgres alone. Each
piece activates only when its config is set, and each degrades rather than
failing if it goes away.

### MinIO (object-store data lake)

```bash
brew install minio
MINIO_ROOT_USER=nwapadmin MINIO_ROOT_PASSWORD=nwapsecret123 \
  minio server --address :9010 --console-address :9011 /tmp/nwap-minio/data
```

Then in `backend/.env`:

```
S3_ENDPOINT_URL=http://127.0.0.1:9010
S3_BUCKET=nwap-raw
S3_ACCESS_KEY=nwapadmin
S3_SECRET_KEY=nwapsecret123
```

The bucket is created on first write. Partition layout is identical to the
local one, so nothing downstream changes. If MinIO is unreachable the lake
writes to local disk and retries the object store after 60 seconds — Admin →
System Health shows which backend is actually live.

### Kafka (event transport)

```bash
brew install openjdk kafka
export JAVA_HOME=$(brew --prefix openjdk)/libexec/openjdk.jdk/Contents/Home
kafka-storage format -t "$(kafka-storage random-uuid)" \
  -c /opt/homebrew/etc/kafka/server.properties --standalone
kafka-server-start /opt/homebrew/etc/kafka/server.properties
kafka-topics --bootstrap-server localhost:9092 --create \
  --topic nwap.raw-events --partitions 3 --replication-factor 1
```

Then in `backend/.env`:

```
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
KAFKA_TOPIC=nwap.raw-events
```

Offsets commit only *after* the pipeline finishes an event, so a crash
redelivers rather than drops. If the broker is unreachable at startup the bus
logs a warning and uses the in-process queue — ingestion continues either way,
and the health endpoint reports the transport that is genuinely in use rather
than the one that was requested.

### Spark (offline batch job)

Needs **JDK 17 or 21** — not 27, which removed an internal class Spark still
uses.

```bash
brew install openjdk@21 && pip install pyspark
export JAVA_HOME=/opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home
python spark/intake_aggregates.py --source local --refresh   # or --source s3
```

`--refresh` rebuilds the columnar **silver** layer from the raw JSON lake
(~65s for 44k documents); without it, aggregates read the existing silver in
about two seconds. The job prints intake by day and source, top cities, ingest
coverage by hour, and a reconcile of the lake against the serving database.

---

## Prototype vs full-scale

The full HLD targets a national system with real message volume. This prototype
keeps the *shape* of that pipeline and drops the operational weight.

| Full-scale | Here | Why |
|---|---|---|
| Kafka | **implemented and exercised** (`KAFKA_BOOTSTRAP_SERVERS`); the in-process asyncio queue is the default | Measured, not assumed: the load test put the bottleneck in the outbound weather HTTP call, so a broker buys *horizontal scale and a restart-survivable backlog*, not throughput. Default stays in-process because it needs no JVM |
| Spark / Scala | **implemented** (`spark/intake_aggregates.py`) for batch recomputation from the lake; serving aggregations stay in Postgres | Postgres is the right tool for indexed queries on thousands of rows. Spark earns its place on the full-scan, unindexed, whole-history question — and reconciling the derived database against the immutable lake |
| Ray + trained models | rule-based classifier behind `classify(text) -> dict[str, float]` | no labelled data yet; the interface matters more than the model |
| MinIO + Iceberg | **MinIO implemented** (`S3_ENDPOINT_URL`); identical `<source_type>/YYYY/MM/DD/*.json` layout on local disk otherwise. Iceberg not used | The partition layout *is* the contract, so the backend swap changes where bytes land and nothing else. An unreachable object store degrades to local disk rather than dropping the write, and retries after a cooldown |
| PostgreSQL + PostGIS + pgvector | **PostGIS kept**, pgvector dropped | PostGIS earns its place (`ST_DWithin` drives dedup, clustering and bbox queries); semantic dedup is exact + fuzzy for now |
| Redis | none (`lru_cache` where needed); live UI updates fan out in-process | not worth a container at one API worker — several workers would each need their own fan-out, which is what Redis pub/sub would be for |
| K8s, CI/CD, Prometheus | none | out of scope |
| Live social ingestion | synthetic generator + **two genuinely live feeds**: Open-Meteo observations and Google News RSS (real Indian weather reporting, keyless, no scraping) | No social platform grants free write-scale read access. News RSS is a published machine-readable interface, so one real intake stream exists alongside the simulated ones — rows carry `is_real: true` and their own source row |
| Geocoding | **GeoNames IN gazetteer** — 9,093 names (49 states, 856 districts, 8,150 towns ≥5k population), replacing a hand-written 65-city table | Measured need: **0 of 6** live news headlines geocoded against the 65-city table, because real reporting names states and districts, not metros. After: 7 of 8 |
| INSAT raster imagery + CV | `SatelliteConnector` deriving sector findings from real cloud-cover readings | image processing is a separate pipeline; the conclusions and the source contract are what matter here |

### Data attribution

Place-name data is from **[GeoNames](https://www.geonames.org/)**, licensed
**CC BY 4.0**. Attribution is required wherever this data is used or
redistributed. Rebuild the local gazetteer with:

```bash
python build_gazetteer.py --dump IN.txt --admin1 admin1CodesASCII.txt --admin2 admin2Codes.txt
```

Weather observations are from **[Open-Meteo](https://open-meteo.com/)** (free,
keyless). Headlines are polled from Google News RSS and are the property of
their publishers; only the headline, publisher and link are stored, and each
report links back to the original article.

### Swap points left deliberately clean

- `classify(text) -> dict[str, float]` — drop in a trained model, no caller changes.
- `credibility.assess(...) -> CredibilityAssessment` — same seam for a trained
  misinformation classifier; the flag vocabulary stays the UI contract.
- `compute_similarity(a, b) -> float` — now backed by ONNX sentence embeddings,
  falling back to `difflib` when `backend/models/` is absent, so the app still
  runs with no ML download.
- `Connector.poll()` — the seam where a real IMD/NDMA/social connector lands.
- `services/ingestion/lake.py` — filesystem *or* S3/MinIO, selected by config;
  both write the same partition layout.
- `services/bus.py` — in-process queue *or* Kafka, selected by config; callers
  (`bus.publish`, `start_workers`) are unchanged either way.

### Known next steps

The original list here — pgvector embeddings, real geocoding, tests and CI — is
done and has been removed rather than left to rot. What is genuinely still open:

- **Live social ingestion.** Blocked on platform API access, not on effort.
- **Multi-worker deployment.** The live-update fan-out and the corroboration
  cache are in-process, so more than one API worker needs Redis pub/sub (or the
  existing Kafka topic) behind them.
- **Code-splitting the console.** One 1.85 MB chunk (520 KB gzipped), dominated
  by MapLibre; fine on a laptop, slow on a district office connection.
- **Containerising the app layer and deployment config**, still out of scope.

---

## Layout

```
backend/
  app/
    main.py                  FastAPI app, lifespan starts bus + scheduler
    config.py                pydantic-settings, reads .env
    db/models.py             14 tables, PostGIS geography + pgvector columns
    api/v1/                  reports, events, map, analytics, verification, admin, auth
    services/
      bus.py                 event bus façade: in-process queue or Kafka
      kafka_bus.py           Kafka transport (opt-in, degrades to the queue)
      notify.py              fan-out behind the live SSE stream
      scheduler.py           APScheduler: ingest tick, alert dispatch, housekeeping
      ingestion/             generator.py, connectors.py (synthetic + Open-Meteo +
                             satellite + live news RSS), lake.py (disk or S3)
      pipeline/              normalize, geo, classify, corroborate, dedupe,
                             reliability, credibility, warning, alerting, routing,
                             advisory, embeddings, event_engine, runner
    core/security.py         JWT, bcrypt, role dependencies
  alembic/                   migrations
  tests/                     35 tests — regressions + domain rules, no infra
  spark/                     offline batch job over the raw lake
  benchmarks/load_test.py    throughput and per-stage latency
  training/                  classifier and relevance model training + eval
  data/gazetteer.json        9,093 Indian place names (GeoNames, committed)
  seed.py                    sources + demo users
  seed_authorities.py        15 authorities for alert routing
  build_gazetteer.py         rebuilds the gazetteer from the GeoNames dump
  fetch_model.py             downloads the ONNX embedding model
  backfill_*.py              re-derive columns after a rule change
frontend/
  src/
    index.css                design tokens — read this before touching any screen
    lib/domain.ts            event/status/severity colour + label registry
    components/dashboard/    IndiaMap, FilterBar, LiveEventFeed, EventDetailPanel,
                             EvidencePanel, TimelineChart, ActiveEventsSummary
      lib/live.ts              SSE client; polling stays as the fallback
    pages/                   Dashboard, Login, admin/*
docker-compose.yml           Postgres + PostGIS, nothing else
.github/workflows/ci.yml     backend pytest + frontend typecheck and build
START.md                     setup, demo script, troubleshooting
```

## Configuration

All optional — `.env.example` works as-is and lists **every** setting. The
tables below cover the ones you would actually change; the rest are timeouts
and endpoints.

| Variable | Default | Notes |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://postgres:postgres@localhost:5432/weather` | |
| `SCHEDULER_INTERVAL_SECONDS` | `8` | ingestion tick |
| `SCHEDULER_ENABLED` | `true` | set `false` to freeze data generation |
| `OPEN_METEO_ENABLED` | `true` | set `false` to run fully offline (corroboration degrades to a neutral 0.5) |
| `RAW_LAKE_DIR` | `./data/raw` | immutable raw mirror on local disk |
| `NEWS_RSS_ENABLED` | `true` | the live news feed; `false` to run fully offline |
| `JWT_SECRET` | `dev-secret-change-me` | **change outside local use** |

Everything below is **off unless set**, and each degrades rather than failing
if the service it points at goes away:

| Variable | Default | Notes |
|---|---|---|
| `S3_ENDPOINT_URL` | *(empty)* | set to use MinIO/S3 for the raw lake; empty keeps local disk |
| `S3_BUCKET` / `S3_ACCESS_KEY` / `S3_SECRET_KEY` | — | required when the endpoint is set; bucket is created on first write |
| `KAFKA_BOOTSTRAP_SERVERS` | *(empty)* | set to use Kafka as the transport; empty keeps the in-process queue |
| `KAFKA_TOPIC` | `nwap.raw-events` | |
