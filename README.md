# Cloud-Based Biometric Authentication System

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12-blue?logo=python">
  <img src="https://img.shields.io/badge/FastAPI-0.110+-teal?logo=fastapi">
  <img src="https://img.shields.io/badge/PostgreSQL-16+-blue?logo=postgresql">
  <img src="https://img.shields.io/badge/pgvector-HNSW-green">
  <img src="https://img.shields.io/badge/SQLAlchemy-2.0+-red">
  <img src="https://img.shields.io/badge/Alembic-Migrations-purple">
  <img src="https://img.shields.io/badge/InsightFace-Buffalo__L-orange">
  <img src="https://img.shields.io/badge/Stage-2%20(Cloud%20Biometric%20Backend)-darkgreen">
  <img src="https://img.shields.io/badge/License-MIT-lightgrey">
</p>

An enterprise-ready cloud biometric authentication platform powered by deep learning facial embeddings (InsightFace Buffalo_L), PostgreSQL + pgvector similarity search, and a FastAPI REST backend.

---

## 📌 Development Roadmap

```text
┌────────────────────────────────────────────────────────┐
│  STAGE 1: Local Biometric Core & Architecture (DONE)   │
└──────────────────────────┬─────────────────────────────┘
                           │
                           ▼
┌────────────────────────────────────────────────────────┐
│  STAGE 2: Cloud Backend, PostgreSQL & pgvector (DONE)  │
└──────────────────────────┬─────────────────────────────┘
                           │
                           ▼
┌────────────────────────────────────────────────────────┐
│  STAGE 3: JWT Security, Anti-Spoofing & Liveness       │
└──────────────────────────┬─────────────────────────────┘
                           │
                           ▼
┌────────────────────────────────────────────────────────┐
│  STAGE 4: Cloud Deployment, Frontend UI & Load Testing │
└────────────────────────────────────────────────────────┘
```

> **Current Stage: Stage 2 — Cloud Biometric Backend**  
> Exposes the biometric core through a modular FastAPI REST API, replaces local JSON persistence with PostgreSQL + pgvector (using native HNSW vector indexing and L2 distance operators), records structured authentication audit logs, and preserves backward compatibility with local storage.

---

## 🏛️ Target System Architecture (Stage 2)

```text
                         CLIENT
                           │
                           │ HTTP (Multipart / JSON)
                           ▼
                    ┌──────────────┐
                    │   FastAPI    │
                    │  REST API    │
                    └──────┬───────┘
                           │
                           ▼
                  ┌─────────────────┐
                  │ BiometricService│
                  └────────┬────────┘
                           │
              ┌────────────┴────────────┐
              │                         │
              ▼                         ▼
         FaceEngine                FaceMatcher
       (InsightFace)                    │
              │                         │
              └────────────┬────────────┘
                           │
                           ▼
                  BiometricRepository
                   (Storage Factory)
                           │
              ┌────────────┴────────────┐
              ▼                         ▼
     PostgresBiometricRepository   LocalBiometricRepository
     (PostgreSQL + pgvector)        (Atomic JSON Fallback)
```

### Dependency Decoupling
- The **API** never executes SQL directly; all interactions traverse `BiometricService`.
- The **Service** interacts exclusively with the abstract `BiometricRepository` interface.
- The **FaceEngine** has zero database knowledge.
- Storage backends (`postgres` vs `local`) are selected cleanly through configuration via `get_biometric_repository()`.

---

## 🧬 Vector Search & Distance Metrics

- **Embeddings:** 512-dimensional float32 normalized vectors extracted by InsightFace Buffalo_L.
- **Metric Rationale:** Buffalo_L vectors are normalized on the unit hypersphere ($\|v\|_2 = 1.0$).
  For normalized vectors, Euclidean ($L_2$) distance and Cosine Similarity are strictly related:
  $$\|u - v\|_2^2 = 2 - 2 \cdot \cos(u, v)$$
- **Database Search:** In 1:N identification, the query is executed in PostgreSQL using pgvector's Euclidean distance operator (`<->`):
  ```sql
  SELECT *, embedding <-> :query_vector AS distance
  FROM biometric_templates
  WHERE status = 'active'
  ORDER BY distance ASC
  LIMIT 1;
  ```
- **Indexing:** Biometric templates utilize an HNSW index (`vector_l2_ops`, `m=16`, `ef_construction=64`) for accelerated nearest-neighbor candidate retrieval.

---

## 💾 Database Schema

Managed via **Alembic** migrations (`alembic/versions/001_initial_biometric_schema.py`).

1. **`users`**:
   - `id` (VARCHAR(36), PK)
   - `user_id` (VARCHAR(64), UNIQUE, INDEX)
   - `name` (VARCHAR(128))
   - `email` (VARCHAR(255), NULL)
   - `status` (VARCHAR(32))
   - `created_at`, `updated_at` (TIMESTAMP WITH TIME ZONE)

2. **`biometric_templates`**:
   - `id` (VARCHAR(36), PK)
   - `user_id` (VARCHAR(64), FK -> `users.user_id`, CASCADE)
   - `embedding` (`vector(512)`, NOT NULL)
   - `model_name` (VARCHAR(64))
   - `model_version` (VARCHAR(32))
   - `status` (VARCHAR(32))
   - `metadata_json` (JSON)
   - `created_at`, `updated_at` (TIMESTAMP WITH TIME ZONE)
   - *Index:* HNSW index on `embedding` (`vector_l2_ops`)
   - *Security:* **No raw images** are stored in this table.

3. **`authentication_logs`**:
   - `id` (VARCHAR(36), PK)
   - `user_id` (VARCHAR(64), NULL for unknown attempts)
   - `timestamp` (TIMESTAMP WITH TIME ZONE)
   - `verification_type` (`1:1_VERIFICATION` or `1:N_IDENTIFICATION`)
   - `similarity` (FLOAT, NULL)
   - `distance` (FLOAT, NULL)
   - `threshold` (FLOAT)
   - `result` (`SUCCESS` or `FAILURE`)
   - `error_code` (VARCHAR(64), NULL)
   - `device_id` (VARCHAR(64), NULL)
   - `created_at` (TIMESTAMP WITH TIME ZONE)
   - *Security:* **Never stores** raw images, complete embeddings, passwords, or tokens.

---

## 🚀 Setup & Execution Guide

### 1️⃣ Install Dependencies

```bash
python -m venv venv
venv\Scripts\activate      # Windows
# source venv/bin/activate # Linux/macOS

pip install -r requirements.txt
```

### 2️⃣ Configure Environment

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

Set your configuration variables:

```env
APP_ENV=development
BIOMETRIC_STORAGE=postgres
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/biometrics
BIOMETRIC_MATCH_THRESHOLD=0.85
LOG_LEVEL=INFO
```

*(To run offline without PostgreSQL, set `BIOMETRIC_STORAGE=local`)*

### 3️⃣ Start PostgreSQL + pgvector (Local or Hosted)

#### Option A: Docker Compose
```bash
docker-compose up -d db
```

#### Option B: Hosted PostgreSQL
Provide any PostgreSQL instance with `pgvector` enabled (e.g. Supabase, Neon, AWS RDS) by setting `DATABASE_URL` in `.env`.

### 4️⃣ Apply Database Migrations

```bash
alembic upgrade head
```

To inspect generated SQL without running against a live DB:
```bash
alembic upgrade --sql head
```

### 5️⃣ Run FastAPI Backend

```bash
uvicorn app.api.app:app --host 0.0.0.0 --port 8000 --reload
```

---

## 📡 REST API Documentation

Interactive OpenAPI / Swagger documentation is available at:
- **Swagger UI:** `http://localhost:8000/docs`
- **ReDoc:** `http://localhost:8000/redoc`

### Endpoints

| Method | Endpoint | Description | Status Codes |
|---|---|---|---|
| `GET` | `/api/v1/health` | Health status and active storage engine | `200` |
| `POST` | `/api/v1/auth/enroll` | Enroll a new biometric identity (`user_id`, `name`, `image`) | `201`, `400`, `500` |
| `POST` | `/api/v1/auth/verify` | 1:1 facial verification (`user_id`, `image`, `threshold`) | `200`, `400`, `404`, `500` |
| `POST` | `/api/v1/auth/identify` | 1:N facial search across gallery (`image`, `threshold`) | `200`, `400`, `500` |

---

## 🛠️ Manual Testing via cURL

### 1. Health Check
```bash
curl -X GET http://localhost:8000/api/v1/health
```

### 2. Enrollment (1:1)
```bash
curl -X POST http://localhost:8000/api/v1/auth/enroll \
  -F "user_id=USR_001" \
  -F "name=Yashwanth" \
  -F "image=@dataset/1_Malhar.jpg"
```

### 3. 1:1 Verification
```bash
curl -X POST http://localhost:8000/api/v1/auth/verify \
  -F "user_id=USR_001" \
  -F "image=@dataset/1_Malhar.jpg"
```

### 4. 1:N Identification
```bash
curl -X POST http://localhost:8000/api/v1/auth/identify \
  -F "image=@dataset/1_Malhar.jpg"
```

---

## 🧪 Automated Test Suite

Run the full automated test suite (Stage 1 + Stage 2):

```bash
python -m pytest tests/ -v
```

The test suite covers 40 tests:
- **API Tests (`tests/test_api.py`):** Health check, successful enrollment, missing fields, multiple faces rejection, unsupported media types, 1:1 verification match/mismatch, 404 user not found, 1:N identification match/unknown person, and end-to-end multi-endpoint real image pipeline.
- **Biometric Core Tests (`tests/test_biometric_service.py`):** Face detection, 512-dim embedding extraction, positive/negative matching, controlled failure cases (no face, multiple faces, invalid files).
- **Matching & Metric Tests (`tests/test_matching.py`):** Identity distance, similarity calculations, threshold adjustments, 1:N best candidate search.
- **Database & Factory Tests (`tests/test_database.py`):** ORM models validation, privacy constraint verification, 512-dim vector sanitization, storage factory backend switching, and live pgvector integration test.

---

## ⚠️ Current Limitations (Stage 2)

1. **No Liveness / Anti-Spoofing Detection:** The system currently operates on 2D static images without liveness verification (planned for Stage 3).
2. **Threshold Calibration:** The Euclidean distance threshold (`0.85`) is a preliminary heuristic; empirical ROC / FAR / FRR calibration will be completed in Stage 3.
3. **No JWT Authorization / Access Tokens:** Endpoints authenticate biometrics but do not yet issue signed JWT authorization tokens for protected resource access (planned for Stage 3).
4. **Cloud Infrastructure Hardening:** Production AWS/GCP infrastructure, S3 image offloading, and rate limiting will be provisioned in Stage 4.

---

## 📜 License

Distributed under the **MIT License**.
