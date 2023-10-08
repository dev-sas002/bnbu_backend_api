# BnBu API

The backend for a short-term-rental investment tool. You upload a spreadsheet of
listings and it asks AirDNA what each address is likely to earn as an Airbnb,
subtracts the rent and utilities, and tells you which ones are worth taking on.
Alongside that it reviews lease PDFs clause by clause and answers questions about
local short-term-let rules.

Django 5.1 · Django REST Framework · Celery + Redis · PostgreSQL · 222 tests.

---

## What it looks like working

This repository ships no product UI — it is a JSON API, and the screens live in
the sibling frontend. What follows is real output from the Docker stack
described below, captured with `curl` against `http://localhost:8131`, plus the
two surfaces the backend does serve itself: Django's admin and the generated
OpenAPI docs. The full transcript, including the property pipeline, the queued
regulation lookup and the ownership checks, is in
[`docs/api-walkthrough.md`](docs/api-walkthrough.md).

### One command, then a populated product

```console
$ docker compose up --build
api-1  | ==> Waiting for the database
api-1  | ==> Applying migrations
api-1  | ==> Collecting static files
api-1  | ==> Seeding demo data
api-1  | Seeded 8 properties, 3 leases and 4 regulation searches.
api-1  | Sign in as admin@bnbu.test / DemoPass!123
api-1  | ==> Starting: gunicorn bnbu_backend_api.wsgi:application --bind=0.0.0.0:8000 --workers=3
api-1  | [1] [INFO] Listening at: http://0.0.0.0:8000 (1)
worker-1  | [INFO/MainProcess] Connected to redis://redis:6379/0
worker-1  | [INFO/MainProcess] celery@c2259aeaac57 ready.
```

### The readiness probe says what is actually wired up

```console
$ curl -s http://localhost:8131/api/ready/
{
    "status": "ready",
    "checks": { "database": true, "cache": true },
    "integrations": {
        "llm_provider": "demo",
        "llm_available": true,
        "regulation_sources": ["curated", "llm"],
        "airdna_configured": false,
        "cloudinary_configured": false
    }
}
```

No OpenAI key, no AirDNA account, no Cloudinary credentials — and every route
still serves.

### A lease review, as a typed object rather than a paragraph

```console
$ curl -s http://localhost:8131/api/documents/2/analysis/ -H "Authorization: Bearer $TOKEN"
{
    "verdict": "Draft",
    "confidence": 0.74,
    "structured": true,
    "provider": "demo",
    "financials": {
        "monthly_rent": 2450.0,
        "security_deposit": 4900.0,
        "late_fee": 150.0,
        "lease_term_months": 12.0
    },
    "clauses": [
        {
            "type": "subletting",
            "risk": "high",
            "excerpt": "Tenant shall not sublet the Premises or any portion thereof, nor assign this Lease, under any circumstance.",
            "finding": "An absolute ban with no landlord-consent carve-out. For a short-term-rental strategy this clause alone makes the unit unusable; ask for 'not to be unreasonably withheld' consent.",
            "confidence": 0.93
        },
        {
            "type": "late_fee",
            "risk": "medium",
            "excerpt": "A late charge of $150 plus $25 per day shall accrue.",
            "finding": "The per-day component is uncapped, so a two-week delay costs $500. Ask for a cap at 5% of one month's rent.",
            "confidence": 0.88
        }
    ],
    "summary": "A twelve-month fixed term at $2,450 a month with a two-month security deposit. Three clauses are worth negotiating before signing: the blanket subletting ban, an uncapped late fee, and a repair responsibility that is pushed onto the tenant below $500."
}
```

### The lookup that used to block the request

A location the curated table covers is answered inside the request. Anything
that needs a model call is queued and the row is filled in by a worker.

```console
$ curl -s -X POST http://localhost:8131/api/regulations/ -d '{"search":"Porto, Portugal"}' ...
HTTP 202
{ "id": 6, "search": "Porto, Portugal", "status": "pending",
  "gpt_response": null, "analysis_state": "pending", "source": "" }

# a moment later, the worker has filled it in
$ curl -s http://localhost:8131/api/regulations/6/ -H "Authorization: Bearer $TOKEN"
{ "id": 6, "status": "STR Allowed with Restrictions",
  "analysis_state": "complete", "source": "llm:demo",
  "gpt_response": { "confidence": 0.7, "citations": [...], "message": "..." } }
```

### The seeded data, through Django's admin

Django's own admin over the database the seed creates — the two addresses
AirDNA could not price are `Error` with a null profit, not a `$0.00`
rejection.

![Seeded properties in the Django admin](docs/01-properties.png)

The generated OpenAPI schema. drf-yasg was installed and its static files were
collected, but no schema URL was ever routed, so the project shipped with no
live documentation; `/api/docs/`, `/api/redoc/` and `/api/schema.json` are now
wired up.

![Swagger UI at /api/docs/](docs/02-swagger.png)

---

## Architecture

The pattern is **thin controllers over a service layer, with the outside world
behind provider interfaces**. A DRF action parses the request, calls one
function in that app's `services.py`, and renders the result. Nothing that
matters to the business happens in a view, and nothing in `services.py` knows
what HTTP is.

Dependencies point inward. `bnbu_core/` holds the seams and imports none of the
four apps; the apps import `bnbu_core`; `bnbu_core` never imports back.

```mermaid
flowchart TB
    subgraph clients[Clients]
        FE["bnbu_frontend_app<br/>(React)"]
        SW["Swagger UI<br/>/api/docs/"]
    end

    subgraph http["HTTP layer — thin"]
        V["ViewSets &amp; APIViews<br/>accounts · rental · lease · regulations"]
        SER["Serializers<br/>validate &amp; render"]
        PERM["bnbu_core.permissions<br/>bnbu_core.mixins<br/>owner scoping"]
    end

    subgraph svc["Service layer — the use cases"]
        LS["lease.services<br/>upload · review · chat"]
        RS["regulations.services<br/>lookup · cache · chat"]
        RTS["rental.services<br/>ingest · filter · export"]
        AS["accounts.services<br/>reset · auth"]
        LA["lease.analysis<br/>PDF → structured review"]
    end

    subgraph seams["bnbu_core — the seams"]
        LLM["llm registry<br/>openai · demo · null"]
        SRC["regulation_sources<br/>curated · llm · chain"]
    end

    subgraph infra[Infrastructure]
        DB[("PostgreSQL")]
        REDIS[("Redis<br/>cache + broker")]
        CEL["Celery workers"]
        OA["OpenAI"]
        AD["AirDNA"]
        CL["Cloudinary"]
    end

    FE --> V
    SW --> V
    V --> SER
    V --> PERM
    V --> LS & RS & RTS & AS
    LS --> LA
    LA --> LLM
    LS --> LLM
    RS --> SRC
    RS --> LLM
    SRC --> LLM
    LLM -.-> OA
    RTS --> AD
    LS --> CL
    LS & RS & RTS & AS --> DB
    RS --> REDIS
    LS -.queue.-> CEL
    RS -.queue.-> CEL
    RTS -.queue.-> CEL
    CEL --> REDIS
    CEL --> LS & RS
```

### The four apps

| App | What it does |
| --- | --- |
| `accounts` | Email-based `CustomUser`, JWT and session auth, an admin → client → customer hierarchy |
| `rental` | The spreadsheet upload, the AirDNA lookup, the profit maths, and the CSV export |
| `lease` | Lease documents (stored on Cloudinary), structured GPT review of them, and a chat over the review |
| `regulations` | One saved "can I run an STR here?" question per row, its answer, and a chat over it |

`bnbu_core/` holds what all four need: the language-model registry, the
regulation-source registry, ownership scoping, pagination, JSON salvage for
legacy rows, the health endpoints and the `seed_demo` command.
`bnbu_constants/` holds the profit maths, the AirDNA client and the spreadsheet
column contract.

---

## The main flow: reviewing a lease

The lease pipeline is the most interesting path through the system and the one
the architecture is shaped around. An upload returns immediately; the review
happens in a worker; the result is a typed object, not a paragraph of prose.

```mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant API as DocumentViewSet
    participant S as lease.services
    participant Q as Redis / Celery
    participant W as Worker
    participant A as lease.analysis
    participant P as LLMProvider
    participant DB as PostgreSQL

    C->>API: POST /api/leases/upload/ (files)
    API->>S: create_lease(user, address, files)
    S->>S: store_document() → Cloudinary URL
    S->>DB: Lease + Document (version n)
    API-->>C: 201 with the lease and its documents

    C->>API: POST /api/documents/review/ {document_ids}
    API->>S: queue_review(documents)
    S->>Q: analyze_document_task.delay(id)
    API-->>C: 200 "review in progress"

    Q->>W: deliver task
    W->>A: analyse_document(document)
    A->>A: fetch PDF, extract text, chunk 5 pages at a time
    loop each chunk (capped at LEASE_MAX_CHUNKS)
        A->>P: complete(purpose=summarize)
        P-->>A: section summary
    end
    A->>P: complete(purpose=lease_analysis, JSON schema)
    P-->>A: {verdict, confidence, financials, clauses[]}
    A->>A: parse, validate, clamp confidences
    A-->>W: LeaseAnalysis
    W->>DB: status + analysis + gpt_response
    Note over W,DB: A failed run writes nothing.<br/>"OpenAI was down" is not a verdict on a lease.

    C->>API: GET /api/documents/{id}/analysis/
    API-->>C: verdict, confidence, clause findings
```

---

## Quickstart

One command. It builds the images, waits for Postgres, migrates, collects
static files, seeds a populated demo database, and starts the API and a Celery
worker.

```bash
docker compose up --build
```

| Service | URL |
| --- | --- |
| API | <http://localhost:8131> |
| Swagger UI | <http://localhost:8131/api/docs/> |
| ReDoc | <http://localhost:8131/api/redoc/> |
| Django admin | <http://localhost:8131/admin/> |
| Health / readiness | <http://localhost:8131/api/health/> · `/api/ready/` |
| Postgres | `localhost:8132` |
| Redis | `localhost:8133` |

The seed creates three accounts, all with the password `DemoPass!123`:

| Email | Role |
| --- | --- |
| `admin@bnbu.test` | staff / superuser — sees everything |
| `analyst@bnbu.test` | client — owns the seeded properties, leases and searches |
| `rival@bnbu.test` | client — owns nothing, so the ownership scoping is visible |

Get a token and look around:

```bash
TOKEN=$(curl -s -X POST http://localhost:8131/api/token/ \
  -H 'Content-Type: application/json' \
  -d '{"email":"analyst@bnbu.test","password":"DemoPass!123"}' \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["access"])')

curl -s http://localhost:8131/api/rental_properties/ -H "Authorization: Bearer $TOKEN"
```

**No API keys are needed.** The compose file sets `LLM_PROVIDER=demo`, which
returns canned-but-realistic analysis payloads through the same parsing,
validation and persistence code the live pipeline uses. Set `OPENAI_API_KEY`
and remove `LLM_PROVIDER` to talk to the real thing.

Tear it down with `docker compose down -v`.

---

## Configuration

Everything is read from the environment; a `.env` file in the project root is
loaded automatically. Nothing has a value baked into the source.

| Variable | Required | Default | What it does |
| --- | --- | --- | --- |
| `ENVIRONMENT` | no | `development` | `staging`/`production` tighten `ALLOWED_HOSTS` and require `SECRET_KEY` |
| `SECRET_KEY` | in staging/production | insecure dev key | Startup fails without it when deployed |
| `DEBUG` | no | `False` | `true`/`1`/`yes` turn it on |
| `ALLOWED_HOSTS` | no | `localhost,127.0.0.1,0.0.0.0` | Comma-separated |
| `DATABASE_URL` | no | local Postgres | Any `dj-database-url` URL |
| `DB_CONN_MAX_AGE` | no | `60` | Seconds a database connection is reused |
| `REDIS_URL` | no | `redis://localhost:6379/0` | Cache, Celery broker and result backend. `rediss://` switches on TLS |
| `CORS_ALLOWED_ORIGINS` | no | `[]` | A **JSON array**, e.g. `["http://localhost:5173"]` |
| `LOG_LEVEL` | no | `INFO` | Root log level |
| **Language model** | | | |
| `LLM_PROVIDER` | no | auto | `openai`, `demo`, `null`. Empty means OpenAI when a key is set, otherwise null |
| `OPENAI_API_KEY` | no | unset | Required only by the `openai` provider |
| `LLM_MODEL` | no | `gpt-4` | Default model for the OpenAI provider |
| `LLM_MODEL_OVERRIDES` | no | `{}` | JSON map of purpose → model, e.g. `{"lease_chat":"gpt-4o-mini"}` |
| `LEASE_MAX_CHUNKS` | no | `12` | Cap on five-page chunks sent for one document's review |
| **Regulations** | | | |
| `REGULATION_SOURCES` | no | `curated,llm` | Comma-separated source chain, consulted in order |
| `REGULATION_CACHE_TTL` | no | `86400` | Seconds an answer about a location is reused |
| **Integrations (all optional)** | | | |
| `AIRDNA_URL`, `AIRDNA_API_KEY` | no | unset | Required by the rental batch |
| `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET` | no | unset | Required to upload lease documents |
| `CLICKUP_URL`, `LIST_ID`, `TEAM_ID`, `ACCESS_TOKEN`, `ZILLOW_CUSTOM_ID`, `PROPERTY_STATUS_CUSTOM_ID` | no | unset | Approved properties are pushed to a ClickUp board; without `CLICKUP_URL` the push is skipped and logged |
| `APPROVED`, `CLICKUP_OPTION_REJECTED`, `CLICKUP_OPTION_CALL_BACK`, `CLICKUP_OPTION_OWNER_APPROVAL`, `CLICKUP_OPTION_ON_HOLD`, `CLICKUP_OPTION_SEE_NOTES`, `CLICKUP_OPTION_FOR_CHI_ONLY` | no | unset | ClickUp dropdown option ids, which differ per board |
| **Mail** | | | |
| `EMAIL_BACKEND` | no | console | Password-reset mail is printed to the console by default |
| `DEFAULT_FROM_EMAIL` | no | `no-reply@localhost` | Sender for password-reset mail |
| `PASSWORD_RESET_URL_BASE` | no | `http://localhost:5173` | Frontend that serves the reset form; the emailed link is built from it |
| **Docker entrypoint** | | | |
| `SEED_DEMO_DATA` | no | `1` | Run `seed_demo` on boot |
| `RUN_COLLECTSTATIC` | no | `1` | Collect static files on boot |
| `CELERY_CONCURRENCY`, `WEB_CONCURRENCY` | no | `2`, `3` | Read by the `Procfile` |

---

## Development

Without Docker you need a Postgres and, for anything queued, a Redis.

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt

export DATABASE_URL=postgres://dev_user:dev_password@localhost:5432/dev_database
python manage.py migrate
python manage.py seed_demo          # populated demo data, idempotent
python manage.py runserver

celery -A bnbu_backend_api worker -l info    # in a second shell
```

### Tests

```bash
python manage.py test
```

222 tests. The suite needs a database and nothing else: under test the cache is
in-memory, Celery runs tasks inline, and the default language-model provider is
the **null** provider — so a forgotten mock fails loudly instead of reaching a
paid endpoint. **No test makes a network call or needs an API key.** Tests that
need a model install a `ScriptedProvider` through the same registry the
application uses, which means they exercise the real prompt building, parsing
and persistence rather than asserting on a mock's return value.

For a database-free quick run, point `DATABASE_URL` at SQLite:

```bash
DATABASE_URL=sqlite:///dev.sqlite3 python manage.py test
```

| Area | Covers |
| --- | --- |
| `bnbu_core/tests.py` | the provider registry and its fallbacks, JSON salvage, health and readiness, the OpenAPI schema, the seed command |
| `rental/tests.py` | the profit maths and status thresholds, spreadsheet validation, the AirDNA retry loop, ownership, filters, CSV export, pagination bounds |
| `lease/tests.py` | document versioning and lease status mirroring, access scope, structured analysis parsing, the chat, the analysis task's failure path |
| `regulations/tests.py` | classification, the curated source, the source chain, cache and queueing behaviour, access scope |
| `accounts/tests.py` | user creation, first-login password change, password reset, login, the client/customer boundary |

### Linting

```bash
isort .       # import order
black .       # formatting, 100 columns
flake8 .      # style and complexity
pre-commit install   # run all three on every commit
```

The same three run in CI (`.github/workflows/ci.yml`), along with a
`makemigrations --check` so a model change without a migration fails the build.

---

## Project structure

```
bnbu_backend_api/        settings, URL routing, Celery app, WSGI/ASGI
bnbu_core/               shared seams — imports none of the four apps
  llm/                     provider registry: base, openai, demo, null
  regulation_sources/      source registry: curated table, LLM, chain
    data/str_rules.json      the curated table
  management/commands/     seed_demo
  permissions.py           owner scoping, shared by all four apps
  pagination.py            the page-size contract
  mixins.py                OwnerScopedQuerysetMixin
  json_utils.py            legacy-row salvage, JSON-out-of-prose
  health.py                /api/health/ and /api/ready/
  testing.py               ScriptedProvider, ScriptedSource, use_provider
bnbu_constants/          profit maths, AirDNA client, spreadsheet contract
accounts/                CustomUser, auth, client/customer hierarchy
  services.py              password reset, authentication, visibility
lease/                   leases and documents
  analysis.py              PDF → structured review (the AI pipeline)
  services.py              upload, queue, review, chat
  storage.py               Cloudinary, behind one catchable error
  tasks.py                 the review worker
rental/                  spreadsheet ingest and property underwriting
  services.py              validation, filter building, CSV streaming
  tasks.py                 the AirDNA batch worker
regulations/             saved STR-legality questions
  services.py              cache, routing, persistence, chat
  tasks.py                 the lookup worker
docs/                    the captured API transcript and screenshots
```

---

## Design notes

### Business logic out of the views

Every app started with its logic in the viewset: `regulations` built a GPT
prompt, called OpenAI, regex-classified the answer and saved the row inside
`perform_create`; `lease` built a second prompt inside a DRF action; `rental`
had four copies of the same filter-building block across two methods.

Each app now has a `services.py` holding its use cases. The actions that remain
are three to ten lines. The test suite got the biggest benefit: the review
pipeline, the cache routing and the CSV export are now tested as functions,
without a request.

`bnbu_core/permissions.py` replaced three byte-identical copies of the same two
permission classes — which mattered, because one of them had a bug that only
`rental` needed fixed (its model stores the owner as a plain integer column,
not a relation, so `obj.user` was an `AttributeError`), and that fix had to be
remembered in three places. `OwnerScopedQuerysetMixin` replaced four hand-written
`get_queryset` overrides; a new action on one of those viewsets is now scoped by
default rather than by remembering.

### Scalability: the real bottleneck was a synchronous GPT call

`RegulationsViewSet.perform_create` called GPT-4 inline, inside the POST. With
three gunicorn workers, three people asking about three cities took the whole
API down for the length of a GPT-4 completion. That was the bottleneck; the
N+1s were second.

Creating a regulation now does three things in order:

1. **Cache.** Answers are keyed on a normalised location, so "Kirkland, WA" and
   `kirkland wa` are the same question. A hit answers inside the request.
2. **Curated source.** A reviewed table of city rules answers common searches
   locally, in microseconds, for free — and more reliably, because a person
   wrote it. Sources declare `is_offline`, and only offline sources are allowed
   to run inside a request.
3. **Queue.** Anything else returns `202` with `analysis_state: "pending"` and
   a worker fills the row in. The client polls the row it already has, which is
   the shape the frontend already expected — it types `gpt_response` as
   nullable "until analysis runs".

The rest of the scalability work:

- **N+1 on the lease list.** `num_of_docs` is a model method, so a page of ten
  leases issued ten `COUNT` queries on top of ten more for the nested
  documents. The list queryset now annotates the count and prefetches the
  documents: 22 queries became 3.
- **Payload size.** A lease list embedded every document's full review text and
  entire chat transcript. Nested documents now use a summary serializer; the
  full record is still on the document routes.
- **Missing indexes.** `RentalProperty.user_id` is a plain integer column, so
  it had no index at all — and it is in the `WHERE` clause of every list,
  filter and export route. Added, along with composite indexes matching the
  actual query shapes: `(user, -created_at)` on leases and regulations,
  `(user_id, -created_at)` and `(property_status, monthly_estimated_profit)` on
  properties, `(lease, -version)` on documents.
- **Unbounded queries.** The admin dashboard serialized every user in the
  database in one response; the client list and customer list were unpaginated;
  `filtered_list` pulled the entire unpaginated result set into Python just to
  collect its distinct batch ids. All paginated or pushed into SQL.
- **CSV export.** It used `StreamingHttpResponse` but iterated the queryset
  normally, so the "stream" materialised every row first. Now `.iterator()`
  with a 500-row chunk.
- **Unbounded fan-out.** A 400-page PDF meant 80 sequential GPT-4 calls.
  `LEASE_MAX_CHUNKS` caps it. Chat histories are replayed to the model 20 turns
  deep rather than in full.
- **Worker semantics.** `task_acks_late` with `worker_prefetch_multiplier=1`,
  so a worker that dies mid-review returns the job to the queue instead of
  losing it, and a soft time limit so a hung vendor call cannot pin a worker
  forever.

### Extensibility: two seams

**`LLMProvider`** (`bnbu_core/llm/`) — a protocol with two methods,
`is_available()` and `complete(messages, purpose=...)`. Four call sites used to
poke `openai.api_key` and `openai.ChatCompletion.create` directly. Now exactly
one module imports the OpenAI SDK, and the registry decides which
implementation answers. Three ship: `openai`, `demo` (deterministic canned
answers — the Docker stack runs on this, and so does the seed), and `null`
(reports itself unavailable, so "no API key" is a clean `503` rather than a
vendor traceback). The `purpose` argument travels with every call so a cheap
model can serve chat while extraction keeps the strong one, configured through
`LLM_MODEL_OVERRIDES` without touching a call site. Migrating to the OpenAI 1.x
client is a rewrite of one file.

**`RegulationSource`** (`bnbu_core/regulation_sources/`) — `lookup(query)`
returns a `RegulationFinding` or `None` for "I don't know".
`RegulationSourceChain` asks each configured source in order and takes the
first real answer; a source that is configured but broken is logged and
skipped, so one dead upstream cannot take the feature down. `REGULATION_SOURCES`
is the order. Adding a municipal-code index or a paid compliance feed is a class
with one method and a registry line.

Both seams have a scripted implementation in `bnbu_core/testing.py`, which is
how the tests stay honest without mocking vendor internals.

### AI: a typed lease review instead of a paragraph

The review used to ask GPT-4 for prose and then decide the verdict with
`if "approved" in analysis_result.lower()` — which reads *"this lease would not
be approved"* as an approval, and gives a reviewer no way to see which clause
drove the answer.

`lease/analysis.py` asks for a JSON object instead and parses it into a
`LeaseAnalysis`: a verdict, a confidence, the money (`monthly_rent`,
`security_deposit`, `late_fee`, `lease_term_months`), and one `ClauseFinding`
per clause that matters — its type, the lease's own words, a risk level, what to
negotiate, and its own confidence. `GET /api/documents/<id>/analysis/` serves it.

Three things make it robust rather than hopeful:

- Models wrap JSON in prose and fences whatever the prompt says, so
  `first_json_object` scans for the first balanced object, respecting strings
  and escapes.
- When there is no parseable JSON it falls back to reading the prose — with a
  recorded confidence of 0.3 and `structured: false`, so a guess is visibly a
  guess. That fallback is negation-aware; the bug above is fixed in both paths.
- Every field is validated on the way in: unknown verdicts become `Draft`,
  confidences are clamped to 0..1, unknown risk levels become `medium`, clauses
  with neither an excerpt nor a finding are dropped, and currency strings like
  `"$2,450"` are coerced to numbers.

The legacy `gpt_response` payload is still written alongside it, so the existing
frontend keeps working unchanged.

### Honest failure

Two related decisions, both visible in the tests:

A failed analysis writes **nothing**. `analyze_document_with_gpt` returns
`status: "Error"`, which is deliberately outside `Document.STATUS_CHOICES`, and
because `Document.save()` mirrors the newest document's status onto its lease,
storing it would have marked a whole lease "Error" because OpenAI had a bad
minute. Same in `regulations`: a failed lookup records `analysis_state:
"failed"` and leaves `status` at `pending`, rather than writing a value no
filter matches.

And a property AirDNA has no data for is `Error` with a **null** profit, not
`$0.00` and `Rejected`. A verdict on an investment that was never evaluated is
worse than no verdict.

---

## Limitations

- **The curated regulation table is illustrative.** Six cities, summarised from
  their ordinances, shipped so the chain has a working first source and the demo
  stack answers without an API key. It is not legal advice and it is not
  maintained against amendments. Real use means a real data source behind the
  same interface.
- **No RAG.** The regulation answers are the model's own knowledge plus the
  curated table. A retrieval index over municipal codes is the obvious next
  step and is the reason `RegulationSource` exists, but shipping a vector store
  with no real corpus behind it would have been theatre.
- **Lease review reads text PDFs only.** A scanned lease produces no extractable
  text and is reported as such; there is no OCR.
- **Regulation chat and lease chat are still synchronous.** They are
  interactive, so a queue would not help the user; they do hold a worker for the
  length of a completion. Streaming responses are the right fix and are not done.
- **`RentalProperty.user_id` is an integer column, not a foreign key.** The data
  is live, so it was indexed rather than migrated. It means no referential
  integrity on property ownership and a permission class that compares ids.
- **No rate limiting and no request-level authorization audit.** DRF throttling
  is not configured; a busy account can queue as many reviews as it likes.
- **The demo provider is a fixture, not a model.** Runs with `LLM_PROVIDER=demo`
  produce the same four clause findings every time. It is there so the product
  can be seen working, not to stand in for analysis.
