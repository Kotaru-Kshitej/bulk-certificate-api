# Deploy to Render — Step by Step

## What was added/changed for deployment
| File | Purpose |
|---|---|
| `render.yaml` | Render Blueprint (service, start command, env vars, persistent disk) |
| `.gitignore` | Keeps junk (venv, db, generated PNGs) out of GitHub |
| `requirements.txt` | Runtime deps only (pytest moved to `requirements-dev.txt`) |
| `fonts/DejaVuSans.ttf` | Bundled font — Render servers have no system fonts, text would look tiny/broken without it |
| `app/config.py` | `CERT_DATA_DIR` / `CERT_OUTPUT_DIR` env vars so DB + PNGs can live on the persistent disk |
| `app/database.py` | SQLite-only args now conditional (also works with PostgreSQL) |

## Important: storage
Render's normal filesystem is **wiped on every deploy/restart**. This API stores a SQLite DB and
generated PNGs on disk, so you need a **Persistent Disk**, which requires a paid plan
(Starter ≈ $7/mo + $0.25/GB disk). `render.yaml` is already set up for that.

Free plan alternative (for demos/assignment review only): works, but all jobs/certificates are
lost on restart, and the service sleeps after ~15 min idle (first request takes ~50 s).
To do that: in `render.yaml` change `plan: starter` to `plan: free`, delete the whole `disk:` block
and the two `CERT_*_DIR` env vars.

## Step 1 — Push to GitHub
The files in this folder must be at the **root** of the repo (`render.yaml`, `requirements.txt`, `app/` visible at top level).

```bash
cd "kshitej project"
git init
git add .
git commit -m "Prepare for Render deployment"
git branch -M main
git remote add origin https://github.com/<your-username>/<your-repo>.git
git push -u origin main
```

## Step 2A — Deploy with the Blueprint (easiest)
1. Go to https://dashboard.render.com → **New +** → **Blueprint**.
2. Connect your GitHub account and select the repo.
3. Render reads `render.yaml` → click **Apply**.
4. Wait for the build (2–4 min) until status shows **Live**.

## Step 2B — Deploy manually (if you skip the Blueprint)
1. **New +** → **Web Service** → pick your repo.
2. Settings:
   - **Runtime:** Python 3
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1`
   - **Health Check Path:** `/api/v1/health`
   - **Instance type:** Starter (or Free)
3. **Environment** tab → add:
   - `PYTHON_VERSION` = `3.12.3`
   - `CERT_DATA_DIR` = `/var/data/db`
   - `CERT_OUTPUT_DIR` = `/var/data/output`
4. **Disks** tab → **Add Disk**: name `cert-data`, mount path `/var/data`, size 1 GB.
5. Click **Create Web Service**.

> Keep `--workers 1`. The background job thread and SQLite are designed for a single process.

## Step 3 — Test the live API
Replace `YOUR-APP` with your Render URL (e.g. `bulk-certificate-api.onrender.com`).

```bash
# Health
curl https://YOUR-APP.onrender.com/api/v1/health

# Create a job
curl -X POST https://YOUR-APP.onrender.com/api/v1/jobs \
  -H "Content-Type: application/json" \
  -d '{"recipients":[{"name":"Aisha Khan","course":"Python","date":"2026-03-15"}]}'

# Check status
curl https://YOUR-APP.onrender.com/api/v1/jobs/1

# Download the certificate
curl -O -J https://YOUR-APP.onrender.com/api/v1/certificates/1/download
```
Swagger docs: `https://YOUR-APP.onrender.com/docs`

## Troubleshooting
- **Build fails on Python version** → check `PYTHON_VERSION` env var is set.
- **"Application failed to respond" / port errors** → start command must use `--host 0.0.0.0 --port $PORT`.
- **Certificates disappear after redeploy** → disk not attached, or `CERT_*_DIR` not pointing under `/var/data`.
- **Template not found** → make sure `templates/certificate_template.png` was committed (not git-ignored).
- **View logs** → Render dashboard → your service → **Logs**.

## Optional: use PostgreSQL instead of SQLite
Create a Render PostgreSQL DB, then set env var
`CERT_DATABASE_URL` = its *Internal Database URL*, and add `psycopg2-binary` to `requirements.txt`.
(The PNGs still need the persistent disk.)
