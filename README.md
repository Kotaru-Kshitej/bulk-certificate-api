# Bulk Certificate Generator API

Backend API that accepts **bulk** certificate generation requests, validates recipients, generates certificates from a **single predefined template**, tracks job progress, and serves downloadable certificate files.

Built for the assignment brief: Python · FastAPI · relational DB · bulk jobs · status · retrieval · tests.

---

## Features

| Requirement | Implementation |
|---|---|
| Accept generation request | `POST /api/v1/jobs` with a list of recipients |
| Validate recipient data | Pydantic schemas (required non-blank `name`, length limits) |
| Generate from template | Pillow renders onto `templates/certificate_template.png` |
| Track status | Job + per-certificate rows in SQLite |
| Check progress | `GET /api/v1/jobs/{id}` (`progress_percent`, counts, statuses) |
| Retrieve certificates | List + metadata + PNG download endpoints |
| Bulk, not 1-req-per-cert | One request can include up to 5000 recipients |
| Isolated failures | One bad cert → `failed`; others still generate |

---

## Project layout

```
bulk-certificate-generator/
├── app/
│   ├── main.py                 # FastAPI app + lifespan (DB init, worker)
│   ├── api.py                  # HTTP routes
│   ├── schemas.py              # Request/response validation
│   ├── models.py               # SQLAlchemy Job / Certificate
│   ├── database.py             # Engine, sessions
│   ├── certificate_service.py  # Template → PNG
│   ├── worker.py               # Background job processor
│   └── config.py               # Settings / paths
├── templates/
│   └── certificate_template.png
├── output/                     # Generated files: output/job_{id}/…
├── data/                       # SQLite DB (certificates.db)
├── tests/
├── requirements.txt
└── README.md
```

---

## Setup

**Python 3.10+** recommended.

```bash
cd bulk-certificate-generator

python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

---

## Run the application

From the `bulk-certificate-generator` directory (so `app` is importable):

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Or:

```bash
python -m app.main
```

- Interactive docs (Swagger): http://127.0.0.1:8000/docs  
- Health: http://127.0.0.1:8000/api/v1/health  

On startup the app creates DB tables and starts a **background worker** thread that processes pending jobs.

---

## Run tests

```bash
cd bulk-certificate-generator
pytest -v
```

Tests cover:

- Creating a generation job  
- Input validation  
- Certificate generation  
- Job status / progress  
- Individual certificate failure isolation  
- Retrieving / downloading certificates  

Tests use an in-memory SQLite DB and process jobs **synchronously** (no reliance on the daemon thread).

---

## API usage

### 1. Submit a bulk generation request

```http
POST /api/v1/jobs
Content-Type: application/json
```

```json
{
  "title": "March 2026 Cohort",
  "recipients": [
    {
      "name": "Aisha Khan",
      "course": "Full Stack Web Development",
      "date": "March 15, 2026",
      "signatory": "Dr. R. Mehta",
      "organization": "Team HMS"
    },
    {
      "name": "Jordan Lee",
      "course": "Data Science Bootcamp",
      "date": "March 15, 2026",
      "signatory": "Dr. R. Mehta",
      "organization": "Team HMS"
    }
  ]
}
```

**Response `202 Accepted`:**

```json
{
  "job_id": 1,
  "status": "pending",
  "total_recipients": 2,
  "message": "Job accepted. Certificate generation is running in the background.",
  "status_url": "/api/v1/jobs/1",
  "certificates_url": "/api/v1/jobs/1/certificates"
}
```

Only `name` is required per recipient. Blank names are rejected (`422`).

### 2. Check job progress / result

```http
GET /api/v1/jobs/{job_id}
```

Returns status (`pending` → `processing` → `completed` | `completed_with_errors` | `failed`), counts, `progress_percent`, and each certificate’s status / error.

### 3. List certificates for a job

```http
GET /api/v1/jobs/{job_id}/certificates
```

### 4. Download a generated certificate

```http
GET /api/v1/certificates/{certificate_id}/download
```

Returns the PNG file. If generation is still pending or failed → `409`.

### cURL example

```bash
# Create job
curl -s -X POST http://127.0.0.1:8000/api/v1/jobs \
  -H "Content-Type: application/json" \
  -d "{\"recipients\":[{\"name\":\"Aisha Khan\",\"course\":\"Python\",\"date\":\"2026-03-15\"}]}"

# Poll status (replace JOB_ID)
curl -s http://127.0.0.1:8000/api/v1/jobs/1

# Download (replace CERT_ID)
curl -s -O -J http://127.0.0.1:8000/api/v1/certificates/1/download
```

---

## Design decisions

### Why FastAPI
Typed request/response models, automatic OpenAPI docs, and async-friendly stack with simple sync SQLAlchemy usage for this workload.

### Why SQLite
Meets the “relational database” requirement with zero external services. Fine for local demos and the assignment; swap `CERT_DATABASE_URL` for PostgreSQL in production.

### Why background processing (not fully synchronous HTTP)
A single request may contain **many** recipients. Image generation is CPU/disk bound. The API:

1. Validates and **persists** the job + certificate rows immediately  
2. Returns **202** with a `job_id`  
3. A **daemon worker thread** picks `pending` jobs and generates files  

**Reasoning:** the client is not blocked for the full bulk render; progress is queryable; the design scales toward a real queue (RQ/Celery) later without changing the API contract.

For tests, the same `process_job` path runs **inline** so results are deterministic.

### Failure handling
Each certificate is generated in its own try/except. One failure sets that row to `failed` with `error_message` and continues. Job ends as:

- `completed` — all succeeded  
- `completed_with_errors` — mix  
- `failed` — none succeeded, or job-level crash  

### Single predefined template
`templates/certificate_template.png` is the only design. Recipient fields (name, course, date, signatory, organization) are drawn at fixed layout coordinates (see `app/config.py`). No template editor (out of scope).

### Optional env overrides
Prefix `CERT_`:

| Variable | Default |
|---|---|
| `CERT_DATABASE_URL` | `sqlite:///…/data/certificates.db` |
| `CERT_WORKER_POLL_INTERVAL` | `0.5` |

---

## Certificate fields

| Field | Required | Notes |
|---|---|---|
| `name` | **yes** | Drawn large on the name line |
| `course` | no | Course / program title |
| `date` | no | Free-text date string |
| `signatory` | no | Left signature label |
| `organization` | no | Right signature label |

---

## Interview notes (quick)

- **Entry:** `app/main.py`  
- **Routes:** `app/api.py`  
- **ORM:** `Job`, `Certificate` in `app/models.py`  
- **Render:** `generate_certificate_file` in `app/certificate_service.py`  
- **Async bulk:** `app/worker.py`  
- To change layout: adjust coordinates in `app/config.py` or replace the PNG template.  
- To force a failure in demos: temporarily raise in `generate_certificate_file`.
