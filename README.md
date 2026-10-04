# Cloud-Based Biometric Authentication & Attendance Portal

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12-blue?logo=python">
  <img src="https://img.shields.io/badge/FastAPI-0.110+-teal?logo=fastapi">
  <img src="https://img.shields.io/badge/PostgreSQL-16+-blue?logo=postgresql">
  <img src="https://img.shields.io/badge/pgvector-HNSW-green">
  <img src="https://img.shields.io/badge/SQLAlchemy-2.0+-red">
  <img src="https://img.shields.io/badge/Alembic-Migrations-purple">
  <img src="https://img.shields.io/badge/InsightFace-Buffalo__L-orange">
  <img src="https://img.shields.io/badge/Security-JWT%20%2B%20bcrypt%20%2B%20PAD-darkgreen">
  <img src="https://img.shields.io/badge/Tests-77%20Passed-brightgreen">
  <img src="https://img.shields.io/badge/License-MIT-lightgrey">
</p>

An enterprise-grade cloud biometric authentication platform and web attendance portal powered by deep learning facial embeddings (InsightFace Buffalo_L 512-D), PostgreSQL + pgvector similarity search, presentation attack detection (liveness), and a FastAPI backend with dual student & administrative access controls.

---

## 🏛️ System Architecture

```
Client (Webcam / Browser)
         │
         ▼ HTTPS
   Nginx Reverse Proxy (TLS Termination, Proxy Headers)
         │
         ▼ HTTP:8000
   Docker Container (FastAPI ASGI Server, appuser UID 10001)
         │
         ├───────────────────┬───────────────────┐
         ▼                   ▼                   ▼
    Kiosk Terminal    Student Portal     Administrative API
    (/attendance)    (/login, /dashboard)   (/auth/enroll)
         │                   │                   │
         └─────────────┬─────┴───────────────────┘
                       │
                       ▼
       Rate Limiting & Bearer JWT Verification
                       │
                       ▼
        Modular Liveness & Anti-Spoofing (PAD)
         (Texture + 2D FFT + YCrCb Dispersion)
                       │
                       ▼
         InsightFace FaceAnalysis (RetinaFace)
                       │
                       ▼
       512-Dimensional Unit-Normalized Embeddings
                       │
                       ▼
             BiometricService Domain Layer
                       │
                       ▼
       Supabase PostgreSQL 16 + pgvector (HNSW)
                       │
       ┌───────────────┴───────────────┐
       ▼                               ▼
 biometric_templates              attendance
 (Vector HNSW index)      (Same-day uniqueness constraint)
```

---

## 🌟 Key Features

1. **Student Registration (`/register`):**
   - Captures student details and **dual face photographs** for multi-angle template enrollment.
   - Enforces password hashing via salted `bcrypt` (12 rounds).
   - Validates presentation attack detection (liveness) on both captures.
   - Atomic registration: rolls back user and template records if biometric enrollment fails on either image.
   - **Privacy First:** Raw facial captures are discarded immediately; only 512-D mathematical vectors are persisted.

2. **Student Authentication & Login (`/login`):**
   - Authenticates using Student ID or registered email + password.
   - Issues short-lived HMAC-SHA256 signed JSON Web Tokens (`role: "student"`).
   - Strict privilege separation: student tokens cannot access administrative enrollment endpoints, and admin tokens cannot access student-restricted dashboard APIs.

3. **Student Attendance Dashboard (`/dashboard`):**
   - Displays real-time student attendance rate (%), total academic sessions, and sessions attended.
   - Shows last verified attendance timestamp.
   - Renders a cryptographic audit history table with date, time, similarity, Euclidean distance, and terminal ID.

4. **Common Attendance Kiosk (`/attendance`):**
   - Live browser WebRTC camera stream with target reticle and sweeping scan animation.
   - Automated 1:N identification via pgvector's Euclidean distance operator (`<->`).
   - Built-in fallback image file uploader for terminals lacking webcam access.
   - Instant visual feedback: Success, Recognition Failure, or Same-Day Duplicate Notice.

5. **Same-Day Duplicate Prevention:**
   - Enforced at both database schema (`UniqueConstraint("user_id", "attendance_date")`) and application layer.
   - Students can only record attendance once per calendar day. Repeated attempts return: *"Attendance already marked today."*

---

## 🛠️ Technology Stack

| Component | Technology | Description |
|---|---|---|
| **API Framework** | FastAPI (Python 3.12) | Asynchronous REST backend with OpenAPI/Swagger docs |
| **Biometric Engine** | InsightFace Buffalo_L | RetinaFace face detector + ResNet 512-D embedding extractor |
| **Presentation Attack** | PassiveTextureFrequency | Laplacian micro-texture, 2D FFT frequency, and color dispersion |
| **Database** | PostgreSQL 16 + pgvector | Cloud persistence with HNSW Euclidean (`vector_l2_ops`) index |
| **ORM & Migrations**| SQLAlchemy 2.0 + Alembic | Declarative schema modeling and version-controlled migrations |
| **Authentication** | OAuth2 Bearer / JWT + bcrypt | HMAC-SHA256 tokens and salted password hashing |
| **Rate Limiting** | Sliding Window Memory Store | Per-IP request throttling on sensitive endpoints |
| **Frontend** | Vanilla HTML5 / CSS3 / ES6 | Glassmorphism UI with WebRTC camera streaming |

---

## 🚀 Quickstart & Local Development

### 1. Prerequisites
- Python 3.12+
- PostgreSQL with pgvector extension enabled (or Supabase PostgreSQL connection string)
- C++ build tools (required by InsightFace / ONNX Runtime)

### 2. Installation
```powershell
# Clone the repository
git clone https://github.com/MalharBhatt-dev/Facial-Recognition-Attendance-System.git
cd Facial-Recognition-Attendance-System

# Checkout demo branch
git checkout feature/attendance-demo

# Create virtual environment and install dependencies
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
```

### 3. Environment Configuration
Copy `.env.example` to `.env` and configure your database and secret keys:
```ini
DATABASE_URL=postgresql+psycopg://postgres:<PASSWORD>@<HOST>:5432/postgres
BIOMETRIC_STORAGE=postgres
BIOMETRIC_MATCH_THRESHOLD=0.85
JWT_SECRET_KEY=generate-a-secure-random-64-character-hex-string
ADMIN_USERNAME=admin
ADMIN_PASSWORD=AdminPassword123!
```

### 4. Database Migrations
Apply the initial biometric schema and student attendance schema:
```powershell
python -m alembic upgrade head
```

### 5. Run the Local Development Server
```powershell
uvicorn app.api.app:app --host 0.0.0.0 --port 8000 --reload
```
Navigate to:
- **Attendance Kiosk:** [http://localhost:8000/attendance](http://localhost:8000/attendance)
- **Student Registration:** [http://localhost:8000/register](http://localhost:8000/register)
- **Student Login:** [http://localhost:8000/login](http://localhost:8000/login)
- **Interactive OpenAPI Docs:** [http://localhost:8000/docs](http://localhost:8000/docs)

---

## 🧪 Test Suite Execution

Run the complete test suite across all 10 test modules (77 tests):
```powershell
python -m pytest -v
```

### Test Coverage Highlights:
- `tests/test_api.py`: Core health check, enrollment, 1:1 verification, 1:N identification.
- `tests/test_attendance_portal.py`: Student registration, duplicate validation, bcrypt verification, JWT claims, student vs admin authorization, kiosk attendance, duplicate day rejection, and dashboard metrics.
- `tests/test_auth.py`: OAuth2 Bearer token generation, expired tokens, role verification.
- `tests/test_biometric_service.py`: Same-person positive match, impostor rejection, face counts.
- `tests/test_database.py`: Live PostgreSQL connection, pgvector HNSW vector search.
- `tests/test_liveness.py`: Passive texture & frequency PAD, synthetic spoof rejection.
- `tests/test_rate_limit.py`: Sliding window rate limit enforcement and 429 Retry-After headers.
- `tests/test_audit_logging.py`: Credential and embedding redaction in audit logs.

---

## 👥 Demo Acceptance Walkthrough

Follow these steps to demonstrate the attendance portal:

1. **Register a Student (`/register`):**
   - Name: `Yashwanth Paleti`
   - Student ID: `YASH_001`
   - Email: `yashwanth@university.edu`
   - Password: `Password123!`
   - Upload Face Photo 1 and Face Photo 2.
   - Click **Complete Registration & Biometric Enrollment**.
   - Dual templates are enrolled and linked to `YASH_001`.

2. **Login (`/login`):**
   - Enter `YASH_001` (or email) and `Password123!`.
   - On success, student receives a signed JWT and is redirected to `/dashboard`.

3. **Inspect Dashboard Initial State (`/dashboard`):**
   - Displays `Yashwanth Paleti (YASH_001)`.
   - Attendance Rate: `0%` | Present: `0` | Sessions: `0`.
   - Last Attendance: `Never`.
   - Log table is empty.

4. **Mark Attendance at Kiosk (`/attendance`):**
   - Open `/attendance`. Allow camera access (or choose image upload fallback).
   - Position face in the reticle and click **MARK ATTENDANCE**.
   - Pipeline stages: Liveness Check $\rightarrow$ 512-D Extraction $\rightarrow$ pgvector Search $\rightarrow$ Ledger Write.
   - Card updates: **✓ Attendance Marked — Yashwanth Paleti (Present)** with current timestamp.

5. **Re-check Dashboard (`/dashboard`):**
   - Refresh `/dashboard`.
   - Attendance Rate: `100%` | Present: `1` | Sessions: `1`.
   - Last Attendance: Displays current timestamp.
   - Table displays recorded log entry with similarity and distance scores.

6. **Test Duplicate Prevention:**
   - Return to `/attendance` and attempt to mark attendance again.
   - System recognizes the student but detects an existing record for today.
   - Result card: **Attendance Already Marked Today** (Duplicate prevented; record count remains 1).

---

## 🐳 Docker Deployment

The application runs inside a production-hardened container under unprivileged user `appuser` (UID 10001):

```bash
# Build production Docker image
docker compose build

# Start services in detached mode
docker compose up -d

# Verify container health
curl http://localhost:8000/api/v1/health
```

---

## 🔒 Privacy & Compliance

- **No Raw Images Stored:** Photographs submitted for enrollment or attendance are decoded in memory, processed into 512-D unit vectors, and discarded immediately.
- **No Vector Leakage:** Biometric embedding vectors are strictly omitted from all public and student API payloads.
- **Redacted Audit Trails:** Application loggers sanitize database connection URLs, JWT tokens, passwords, and vector coordinates.
