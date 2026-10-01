# START — running NWAP

**Team Uptown Func · SIH26069 · National Weather Big Data Analytics Platform**

Everything here assumes a clean machine. The rest of this file is what to click
once it is up, and what to say when someone asks a hard question about it.

The `README.md` explains *why* the system is built the way it is. This file is
only about getting it running.

---

## Just open it

**Already set up, and you only want it running?** Two terminals:

```bash
# terminal 1 — backend (needs PostgreSQL running)
cd backend && source .venv/bin/activate && uvicorn app.main:app --reload --port 8000

# terminal 2 — console
cd frontend && npm run dev
```

Then open **<http://localhost:5180>**. It lands on `/monitor`.

**No backend, no database, no network?** One terminal, and open the mock URL:

```bash
cd frontend && npm run dev
```

**<http://localhost:5180/?mock=1>** — the whole console served from captured
fixtures. Use this for screenshots, for UI work, and as demo-day insurance.

First time on this machine, or something is missing? Work through sections 0–3
below.

---

## 0. What you actually need

| Required | Why |
|---|---|
| **PostgreSQL 16 or 17** with **PostGIS** | The database is the centralised store, and PostGIS drives clustering, dedup and map queries. Not optional. |
| **Python 3.12+** | Backend. |
| **Node 20+** | Console. |

| Optional | What you lose without it |
|---|---|
| ONNX model (~118 MB, one command) | Semantic dedup and the trained classifier fall back to keyword and character matching. Everything still runs. |
| Kafka · MinIO · Spark | Nothing. These are off by default and the platform runs on Postgres alone. |
| Docker | Only used to start Postgres; a local install works identically. |

> **The platform starts with no broker, no object store and no ML download.**
> That is deliberate, and it is the honest answer to "what if the wifi dies on
> demo day".

---

## 1. Database

```bash
docker compose up -d db
```

No Docker? A local PostgreSQL works and the default `DATABASE_URL` still applies:

```bash
createdb weather
psql -d weather -c "CREATE EXTENSION IF NOT EXISTS postgis;"
psql -d postgres -c "CREATE ROLE postgres LOGIN SUPERUSER PASSWORD 'postgres';"
```

## 2. Backend

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env

alembic upgrade head        # schema + PostGIS and pgvector extensions
python seed.py              # 7 sources + 3 demo users        (idempotent)
python seed_authorities.py  # 15 authorities for alert routing (idempotent)
python fetch_model.py       # optional, ~118MB — semantic dedup + classifier

uvicorn app.main:app --reload --port 8000
```

**Do not skip `seed_authorities.py`.** Without it, alerts are raised correctly
but have nobody to route to, and the delivery panel sits empty — which looks
like a bug during a demo and is not one.

Ingestion starts on boot. First raw events land within ~8 seconds; multi-report
events with rising warning levels appear within about a minute.

- API docs — <http://localhost:8000/docs>
- Health — <http://localhost:8000/health>

## 3. Console

```bash
cd frontend
npm install
npm run dev
```

Open **<http://localhost:5180>**. Vite proxies `/api` to port 8000.

> The port is pinned to 5180 with `strictPort`, so if something else already
> holds it the server refuses to start rather than quietly moving to another
> port and leaving you looking at the wrong app.

### What you are looking at

`/` redirects to `/monitor`. The console is **four destinations**, not one
dashboard — each of the first three answers a different question, and they want
opposite things from a layout, which is why they are separate screens.

| Where | The question it answers | What is on it |
|---|---|---|
| **Monitor** `/monitor` | What is happening across India right now | The national map, live feed, reporting timeline, hashtags, source health. The only screen where the map leads. |
| **Verify** `/verify` | Is this reported event real | Queue on the left, evidence on the right, **no map**. `j` and `k` walk the queue. Weakest evidence first. |
| **Advise** `/advise` | What have we told people, and what still needs telling | Alert queue on IMD's four-colour scale, and district preparedness. Two tabs. |
| **System** `/admin` | Is the machine healthy | Sources, credibility, raw reports, events, pipeline health, audit log. |

Monitor is public — **no account needed**. Verify, Advise and System need a
sign-in (next section).

Ingestion starts on boot. First raw events land within ~8 seconds; multi-source
events with rising warning levels appear within a minute or two. If the map
looks sparse, give it a few minutes before demoing.

---

## Sign in

The public dashboard needs **no account at all** — that is the point of a
public warning platform. Sign in only for the operations console.

| Email | Password | Role | Can do |
|---|---|---|---|
| `admin@demo.in` | `admin123` | ADMIN | everything, including pausing sources |
| `verifier@demo.in` | `verifier123` | VERIFIER | verify, reject and stand down alerts |
| `analyst@demo.in` | `analyst123` | ANALYST | read every admin view, change nothing |

---

## A five-minute demo path

Roughly in this order — each step answers the question the previous one raises.
Sign in as `verifier@demo.in` first so steps 3–7 work.

1. **Monitor.** Pins sized by IMD warning level, not by noise; colour is the
   event type, the ring is verification status. Watch the counters climb and a
   feed row arrive. *"This is what a district officer sees."*
2. **Filter down.** Last 24 hours → an event type → a state → a district. Point
   out that date, event and location filtering are all here and none of it is
   hidden — it is a stated requirement of the problem statement.
3. **Click an event → evidence panel.** Report count, how many *independent*
   sources, weather corroboration against observed conditions, misinformation
   risk with **named** reasons. *"We show the evidence, not just a verdict."*
4. **Verify.** The queue is ordered weakest-evidence-first, because that is
   where a human verdict changes the outcome. Press `j` a couple of times on
   camera. Verify one with a reason — note that the reason lands in the audit
   log and that nothing is decided anonymously.
5. **Advise → Alerts.** Most severe first, then oldest — the order someone
   actually works down. Acknowledge one; note that **closing** needs a verifier
   and that the split is enforced server-side. Then **"Advisory"**: a
   publishable bulletin in English and Hindi with NDMA guidance. Say plainly it
   is **template-generated, not model-generated** — a language model inventing
   safety instructions in a disaster bulletin is a hazard, not a feature.
6. **Advise → Preparedness.** District risk ranking and hour-of-day. Point at
   the coverage note that says what the data **cannot** support yet — that
   honesty tends to land better than another chart.
7. **System → Credibility.** Six named, weighted flags. Open one flagged report
   and read why it was flagged. *"Not a black-box score."*
8. **System → Pipeline health.** Live per-stage breakdown, bus transport,
   raw-lake backend and object count. Good place to mention Kafka, MinIO and
   Spark are real and opt-in.

> **If you only have ninety seconds:** Monitor (scale) → an event's evidence
> panel (the thinking) → Verify (the decision). Those three carry the project.

---

## Optional: the big data stack

Not needed for the demo. Each piece activates only when its config is set, and
each **degrades rather than fails** if it goes away.

```bash
# MinIO — object-store data lake
brew install minio
MINIO_ROOT_USER=nwapadmin MINIO_ROOT_PASSWORD=nwapsecret123 \
  minio server --address :9010 --console-address :9011 /tmp/nwap-minio/data
```
Then set `S3_ENDPOINT_URL=http://127.0.0.1:9010` (plus bucket and keys) in
`backend/.env`. If MinIO is unreachable the lake writes to local disk and
retries after 60 seconds.

```bash
# Kafka — event transport (needs a JDK)
brew install openjdk kafka
export JAVA_HOME=$(brew --prefix openjdk)/libexec/openjdk.jdk/Contents/Home
kafka-storage format -t "$(kafka-storage random-uuid)" \
  -c /opt/homebrew/etc/kafka/server.properties --standalone
kafka-server-start /opt/homebrew/etc/kafka/server.properties
kafka-topics --bootstrap-server localhost:9092 --create \
  --topic nwap.raw-events --partitions 3 --replication-factor 1
```
Then set `KAFKA_BOOTSTRAP_SERVERS=localhost:9092`. If the broker is down at
startup the bus logs a warning and uses the in-process queue — ingestion
continues either way, and System Health reports the transport genuinely in
use rather than the one requested.

```bash
# Spark — offline batch job. Needs JDK 17 or 21, NOT 27.
brew install openjdk@21 && pip install pyspark
export JAVA_HOME=/opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home
cd backend && python spark/intake_aggregates.py --source local --refresh
```

Full rationale and measurements: `README.md` → *Optional: the big data stack*.

---

## Frozen mode for UI work — `?mock=1`

<http://localhost:5180/?mock=1>

The platform ingests continuously and pushes updates over SSE, which is right
for an operations console and hostile to UI work: every screenshot differs,
every before/after comparison drifts, and a layout bug looks exactly like new
data arriving.

`?mock=1` makes the screen a pure function of the code:

- every `/api/v1` call is served from `src/fixtures/api.json` — **real
  responses captured from a running backend**, not hand-written objects that
  drift from the schema;
- the SSE stream is never opened and polling is disabled, so nothing refetches
  behind you;
- the map starts at a fixed centre and zoom instead of fitting bounds to the
  container, which otherwise reframes with window size.

**It needs no backend running at all** — which is the easiest way to prove the
freeze is real. Turn it off with `?mock=0`; the flag is remembered per tab.

Mutations (acknowledge, verify) are accepted and deliberately do nothing, so a
click never throws but the dataset never moves.

Re-record after a schema change — backend must be up:

```bash
cd frontend && npm run capture-fixtures
```

The fixtures load through a dynamic import, so they are a separate chunk that
normal sessions never download.

---

## Tests

```bash
cd backend && python -m pytest -q      # 35 tests, ~4s, no infrastructure
```

No database, broker, object store or ML model required. Passes on a checkout
with no `.env` and no `backend/models/` — which is exactly what CI gets.

---

## When something looks wrong

| Symptom | Cause | Fix |
|---|---|---|
| `npm run dev` refuses to start | Port 5180 already taken (`strictPort`) | Stop the other app, or change `server.port` in `frontend/vite.config.ts` |
| Terminal reaches the console but the browser says **"This site can't be reached"** | Vite bound only to IPv6 `[::1]`, so `curl localhost` works while Chrome tries `127.0.0.1` | `host: true` in `frontend/vite.config.ts` fixes this permanently. If it recurs, `npm run dev -- --host`, and check `lsof -nP -iTCP:5180 -sTCP:LISTEN` shows `*:5180` rather than `[::1]:5180` |
| Console loads but stays empty | Backend not running, or ingestion off | Check <http://localhost:8000/health>; confirm `SCHEDULER_ENABLED` is not `false` |
| Alert queue fills, delivery panel empty | `seed_authorities.py` was skipped | Run it; it is idempotent |
| Dedup looks weak, classifier looks crude | `backend/models/` absent | `python fetch_model.py`, then restart the backend |
| Map pins but no districts/states on news items | Gazetteer missing | `backend/data/gazetteer.json` is committed; if absent, rebuild with `build_gazetteer.py` |
| `Pipeline health` says `in-process` after enabling Kafka | Broker unreachable — the bus fell back on purpose | Check the broker; the field reports what is *working*, not what was requested |
| A rule changed and old rows look stale | Derived columns are computed at ingest | Run the matching `backfill_*.py` in `backend/` |

---

## Honest limits — say these before a judge finds them

- **No live social-platform ingestion.** X and Meta do not grant free read
  access at this scale. Social traffic is synthetic; **news RSS and weather
  observations are genuinely live**.
- **The warning thresholds are ours, not IMD's.** The four-colour scale, its
  vocabulary and its actions follow IMD; what *triggers* each level is derived
  from accumulated evidence, and the UI says so wherever a level appears.
- **Detection lead time has very few qualifying measurements**, and the API
  says so rather than presenting a median of one observation as a trend.
- **Seasonal and monsoon-cycle analysis needs a year of data.** The
  preparedness endpoint states that in its own coverage note.
