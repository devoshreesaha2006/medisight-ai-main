# MediSight AI — 50% MVP

Privacy-first patient health records & disease trend monitoring.

**Core principle: Intelligence can be shared, but patient identity cannot.**

This repo implements the first 50% of the MediSight AI MVP:

```
Login (patient / clinician / admin) → RBAC → QR Patient Access → Patient Record → AI Risk + SHAP → Admin Analytics → Privacy Protection
```

All of it has been run end-to-end in development (backend tests pass, the
API flow was exercised live via curl, and the frontend builds cleanly) —
see [`docs/DEMO_VERIFICATION.md`](docs/DEMO_VERIFICATION.md) for the actual
output of that run.

## What's here

| Area | Status |
|---|---|
| Auth (JWT + bcrypt) + RBAC | ✅ implemented, tested |
| Patient/visit/condition/lab/prescription schema | ✅ implemented |
| Secure QR issue/scan/validate/revoke | ✅ implemented |
| Three sign-in roles (patient, clinician, admin) with a role picker on the login page | ✅ implemented, tested |
| Patient self-sign-up (`/signup`) | ✅ implemented, tested |
| Patient portal: overview, records, AI insights, create/cancel own QR | ✅ implemented, tested |
| Landing page + redesigned UI (maroon/rose theme, light + dark mode) for all three roles | ✅ implemented |
| Clinician dashboard (React/Vite/Tailwind) | ✅ implemented |
| XGBoost risk model + SHAP explanations | ✅ implemented, real train/test eval |
| Admin analytics + server-side k-anonymity (k=5) | ✅ implemented, tested |
| Audit logging | ✅ implemented |
| Clinicians can add visits/conditions/labs/prescriptions to a record | ✅ implemented (`POST /api/patients/{id}/...`, UI in the record tabs) |
| Real 30,921-patient Synthea dataset for ML training | ✅ implemented (`ml/data/synthea_features.csv`, see below) |
| MIMIC-IV ingestion | ⏳ not started |
| Forecasting, hotspot detection, differential privacy, chatbot, mobile | ⏳ Phase 2, intentionally out of scope |

## Important honesty notes

- **The seeded dev dataset is real Synthea output now, not Faker.**
  `backend/scripts/seed_data.py` loads ~250 real, living Synthea-simulated
  patients (real conditions, visits, labs, prescriptions) from
  `backend/scripts/data/synthea_seed_sample.json`, a pre-extracted sample
  of the same Synthea populations used to train the risk model. Synthea's
  non-clinical "social determinants" entries (employment, education,
  housing, etc.) are filtered out of the Conditions tab. This is still not
  MIMIC-IV or real people — Synthea patients are synthetic, simulated by
  Synthea's disease-progression models — just not Faker-random anymore.
- **The ML training data is the same real Synthea output, at full scale.**
  `ml/data/synthea_features.csv` is built from two full Synthea-generated
  populations (`ml/src/build_synthea_features.py`), 30,921 patients total.
  The label is a genuine forward-looking outcome — not a fabricated
  heuristic: each patient's encounter history is cut at ~70% of the way
  through, features are computed from everything up to that point, and the
  label is whether that patient went on to have an inpatient/emergency
  encounter afterwards. `ml/src/train_model_synthea.py` trains XGBoost on
  this and reports real held-out metrics (ROC-AUC ~0.74 in our run).
  Neither the seed data nor the training data is MIMIC-IV or real-world
  clinical validation. Retrain on real outcomes (e.g. MIMIC-IV) before this
  goes near real patients.

## Repo layout

```
medisight-ai/
├── frontend/    React + Vite + Tailwind UI: landing, sign-in/sign-up, patient, clinician and admin areas
├── backend/     FastAPI + SQLAlchemy + JWT API
├── ml/          XGBoost training (real-Synthea, 30,921 patients), SHAP, saved model artifacts, ml/data/synthea_features.csv
├── scripts/     (backend/scripts/seed_data.py — loads backend/scripts/data/synthea_seed_sample.json, real Synthea patients)
├── docs/        This file + demo verification log
└── tests/       pytest suite (RBAC, k-anonymity, QR flow)
```

## Quick start

### 1. Backend

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env   # edit JWT_SECRET_KEY etc. for anything beyond local demo

python -m scripts.seed_data                    # creates DB + 3 demo users + 250 real Synthea patients
cd .. && python -m ml.src.train_model_synthea   # trains XGBoost on the real 30,921-patient Synthea dataset (run from repo root)
cd backend && uvicorn app.main:app --reload --port 8000
```

By default this uses local SQLite (`backend/medisight_dev.db`) so it runs
with zero external services. For Postgres, set `DATABASE_URL` in `.env` to
e.g. `postgresql+psycopg2://user:pass@localhost:5432/medisight` before
seeding — the code is identical either way (SQLAlchemy).

Demo accounts (seeded automatically):

| Role | Email | Password |
|---|---|---|
| Patient | `patient@medisight.dev` | `Patient123!` |
| Clinician | `clinician@medisight.dev` | `Clinician123!` |
| Admin | `admin@medisight.dev` | `Admin123!` |

The demo patient login is linked to one of the synthetic patient records.
Anyone can also create their own patient account at `/signup`; clinician and
admin accounts can only be provisioned by an operator (there is deliberately
no public endpoint that creates them).

**Upgrading an older database:** the patient role adds a `users.patient_id`
column. Starting the API (or running `python -m scripts.seed_data`) adds it
automatically to an existing SQLite/Postgres dev database, and re-running the
seed script adds the demo patient login without touching existing data. For
production, move this into an Alembic migration.

API docs: `http://localhost:8000/docs` (FastAPI's built-in Swagger UI).

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. The dev server proxies `/api` to
`http://127.0.0.1:8000` (see `vite.config.js`), so run the backend first.

### 3. Run the test suite

```bash
# from repo root
pip install -r backend/requirements.txt   # if not already
python -m pytest tests -v
```

Covers: login success/failure, role-tab enforcement, patient sign-up
(duplicates, weak passwords, under-18, no way to self-register as admin),
clinician can access patients, **admin cannot** (403), **patients cannot reach
clinician/admin routes or other patients' records**, unauthenticated requests
rejected, k-anonymity suppression at/below/above the threshold, and the full
QR generate→validate→revoke round trip (clinician-issued and patient-issued).

## Roles and routes

| Role | Signs in at | Lands on | Can do |
|---|---|---|---|
| Patient | `/login` (Patient tab) or `/signup` | `/patient` | View **own** record, AI insights, create/cancel own QR |
| Clinician | `/login` (Clinician tab) | `/dashboard` | Scan QR → patient record → risk score |
| Admin | `/login` (Admin tab) | `/admin` | k-anonymised analytics, audit log |

The tab on the login page is sent to the API as `role`; the server rejects an
account that belongs to a different role, so the tab is enforced server-side
rather than just being a UI hint.

New endpoints:

| Endpoint | Who | Purpose |
|---|---|---|
| `POST /api/auth/register/patient` | public | Create a patient account + linked record, returns a session |
| `GET /api/me/record` | patient | Own record (id comes from the session, never the URL) |
| `GET /api/me/risk` | patient | Own risk score + SHAP factors |
| `POST /api/me/qr` | patient | Mint own short-lived QR |
| `POST /api/me/qr/revoke/{token}` | patient | Cancel own QR (404 for anyone else's token) |
| `GET /api/analytics/regional-distribution` | admin | Active-case counts by region ("location"), k-anonymized |

The admin Population page now has three tabs — **By condition**, **By
region**, **Trends over time** — covering the three axes the brief names:
`GET /api/analytics/disease-distribution` (condition), the new
`regional-distribution` (location), and the existing
`GET /api/analytics/disease-trends` (time, now with a line chart per top
condition; a gap in a line means that month was suppressed, not zero).

## Demo script (matches the spec's demo requirement)

1. Log in as the clinician.
2. Click **Generate demo QR** for a patient ID (or use a second device to
   scan a printed code) — the QR encodes only `medisight://patient/<random
   token>`, nothing else.
3. Click **Scan Patient QR**, scan/paste the token → lands on that
   patient's record (conditions, timeline, labs, prescriptions).
4. Click **Run risk model** → XGBoost risk score + SHAP-explained top
   contributing features, with a "decision support, not diagnosis"
   disclaimer.
5. Log out, log in as the admin.
6. Admin dashboard shows only aggregated disease distribution — any
   condition with fewer than 5 patients is labeled **SUPPRESSED** with the
   reason, computed server-side.
7. Click **Attempt patient record access** — the same `GET
   /api/patients/{id}` call a clinician uses returns `403 Forbidden` for
   the admin, and it's logged in the audit trail below.
8. Log in on the **Patient** tab (`patient@medisight.dev`): overview, health
   records, AI insights, and **Share access** to create a QR a clinician can
   scan (and cancel it with *Stop sharing*).
9. Or create a brand-new patient at `/signup`. Their record starts empty, so
   the dashboard shows an empty state and no AI score (a score from age and
   gender alone would be misleading).

## Security notes

- RBAC is enforced in the backend (`app/core/deps.py`), not just hidden in
  the UI — the 403 in step 7 above comes from the API itself.
- QR tokens are generated with `secrets.token_urlsafe`, expire after 15
  minutes by default, and can be explicitly revoked
  (`POST /api/qr/revoke/{token}`). They carry no patient identity or
  medical data.
- k-anonymity (k=5) is enforced in `app/services/privacy.py`, called from
  the analytics endpoints — the raw count is never serialized for a
  suppressed bucket, not just hidden client-side.
- Patient identity (name, email) lives on the `users` row; the clinical
  `patients` row stays de-identified (age, gender, region). A patient's
  endpoints take the record id from the authenticated user, never from the
  URL, so there is no id to tamper with.
- Passwords are bcrypt-hashed, 8–72 characters with a letter and a number.
  There is no rate limiting or email verification yet; add both before any
  real deployment.
- `.env` is gitignored; only `.env.example` (no real secrets) is committed.
- No real MIMIC-IV data is present in or intended for this repo — see
  `.gitignore`.
