# Stage 3 Security and Architecture Audit

**Project:** Cloud-Based Biometric Authentication System  
**Audit Date:** October 2026 (Stage 3 Initial Phase)  
**Auditor:** Automated Security & Architecture Review  
**Target Environment:** FastAPI + InsightFace (Buffalo_L) + Supabase PostgreSQL (pgvector) on AWS EC2  

---

## 1. Executive Summary

A comprehensive architectural and code security audit was performed across the Cloud-Based Biometric Authentication System following the completion of Stage 1 (Biometric Engine & Local Storage) and Stage 2 (PostgreSQL + pgvector Integration & FastAPI REST API).

The system maintains a sound foundation:
- **No raw face photographs** are stored in PostgreSQL.
- **No raw biometric embeddings** are exposed across public REST endpoints or logged.
- **No database credentials** are leaked via API error responses or application logs.
- SQL injection risks are mitigated through SQLAlchemy 2.0 ORM expressions and parameterized pgvector operators (`<->`).

However, several production security gaps were identified that must be resolved during Stage 3:
1. Absence of authentication/authorization on administrative endpoints (such as `/api/v1/auth/enroll`).
2. Absence of rate limiting on computationally expensive biometric verification and identification endpoints.
3. Absence of presentation attack detection (liveness verification) before biometric matching.
4. Wildcard CORS combined with credential support.
5. Container running as `root` in Docker.
6. Default biometric threshold lacking empirical evaluation metrics (FAR/FRR curves).

---

## 2. Detailed Findings and Vulnerability Matrix

| ID | Issue Description | Severity | Location | Remediation | Status |
|---|---|---|---|---|---|
| **SEC-01** | Unauthenticated Biometric Enrollment | **HIGH** | `app/api/routes/biometric.py:32` | Protect `/api/v1/auth/enroll` with OAuth2 Bearer JWT requiring an administrator role. | Remediation Planned (Checkpoint 3.4) |
| **SEC-02** | Missing Rate Limiting on Biometric APIs | **HIGH** | `app/api/routes/biometric.py:85, 148` | Implement in-memory token-bucket / sliding-window rate limiting returning HTTP 429 on abuse. | Remediation Planned (Checkpoint 3.5) |
| **SEC-03** | Lack of Presentation Attack Detection (Liveness) | **HIGH** | `app/services/biometric_service.py:175, 345` | Introduce a modular liveness validation pipeline prior to embedding extraction. | Remediation Planned (Checkpoint 3.2) |
| **SEC-04** | Permissive CORS with Wildcard and Credentials | **MEDIUM** | `app/api/app.py:42-48`, `app/config/settings.py:70` | Disable `allow_credentials` when wildcard `*` is configured; require explicit allowed origins. | Remediation In Progress (Checkpoint 3.1) |
| **SEC-05** | Image MIME Type Permissiveness | **LOW** | `app/api/dependencies.py:20` | Remove generic `application/octet-stream` or inspect file magic bytes (JPEG/PNG/WEBP/BMP). | Remediation In Progress (Checkpoint 3.1) |
| **SEC-06** | Docker Container Runs as Root | **MEDIUM** | `Dockerfile` | Introduce a non-root system user (`appuser`, UID 10001) in Dockerfile. | Remediation Planned (Checkpoint 3.7) |
| **SEC-07** | Biometric Match Threshold Lacks Empirical Basis | **MEDIUM** | `app/config/settings.py:23` | Implement `scripts/calibrate_threshold.py` to evaluate FAR/FRR distributions. | Remediation Planned (Checkpoint 3.3) |
| **SEC-08** | Audit Log Missing Liveness & Client Metadata | **LOW** | `app/storage/postgres_repository.py:200` | Include liveness result/score and client IP metadata in authentication audit logs. | Remediation Planned (Checkpoint 3.6) |
| **SEC-09** | Legacy Credentials Quarantined in Repository | **LOW** | `legacy/faculty_users.csv`, `legacy/app.py` | Ensure legacy components remain isolated from the production app and never executed in production. | **VERIFIED QUARANTINED** |
| **SEC-10** | Error Information Leakage Prevention | **INFORMATIONAL** | `app/api/app.py:51-81` | Centralized exception handlers successfully catch `BiometricError` and generic exceptions, preventing stack trace leakage. | **VERIFIED SECURE** |

---

## 3. In-Depth Component Analysis

### 3.1 Authentication & Authorization
- **Current State:** The API does not implement any token authentication. Endpoints `/api/v1/auth/enroll`, `/api/v1/auth/verify`, and `/api/v1/auth/identify` are completely unauthenticated.
- **Risk:** Anyone with network access can enroll a face into arbitrary user IDs or overwrite biometric data. Impostors can perform unlimited dictionary attacks.
- **Action Required:**
  - Create an administrative JWT token authentication flow (`POST /api/v1/auth/token`).
  - Protect enrollment under `Depends(get_current_admin)`.
  - Require valid API keys or JWT for administrative endpoints.

### 3.2 Biometric Pipeline & Liveness
- **Current State:** The system accepts any image that contains a detectable face via InsightFace. There is no verification of whether the image is from a live person, a printed photograph, or a digital screen replay.
- **Risk:** Presentation attacks (spoofing) using photos or phone displays can deceive 1:1 and 1:N authentication.
- **Action Required:**
  - Build a modular liveness evaluation interface (`LivenessDetector`) that executes BEFORE embedding extraction.
  - Implement an anti-spoofing check appropriate for single-frame image analysis (texture, frequency, color distribution, blur/specular reflection analysis) and clearly document limitations.
  - Record liveness scores in internal metrics and audit logs.

### 3.3 Rate Limiting & Resource Exhaustion (DoS)
- **Current State:** InsightFace `FaceAnalysis.get()` is computationally intensive (runs ONNX detection + feature extraction on CPU). No rate limiting is enforced.
- **Risk:** An attacker sending 20 concurrent requests per second can peg CPU utilization at 100%, starving the server and causing denial-of-service.
- **Action Required:**
  - Implement a lightweight in-memory rate limiter using sliding window counters per client IP.
  - Enforce strict limits on `/verify` (e.g. 10 req/min/IP), `/identify` (e.g. 5 req/min/IP), and `/enroll` (e.g. 5 req/min/IP).
  - Return `HTTP 429 Too Many Requests` with `Retry-After` headers.

### 3.4 Data Privacy & Biometric Template Security
- **Current State:**
  - Raw images are discarded immediately after in-memory processing.
  - Embeddings are stored as 512-dimensional float arrays in `biometric_templates` (PostgreSQL `vector(512)`).
  - API responses return `authenticated`, `user_id`, `distance`, `similarity`, `message`. Embeddings are never returned.
  - Logs write `user_id`, `verification_type`, `similarity`, `distance`, `threshold`, `result`. Neither raw images nor complete embeddings are logged.
- **Status:** **PASS** (Complies with biometric privacy best practices).

### 3.5 CORS & Network Security
- **Current State:** `CORS_ORIGINS` defaults to `*` while `allow_credentials=True`.
- **Risk:** Modern browsers reject wildcard origin when credentials are included. In development or testing with specific origins, credentials should only be enabled for explicit origins.
- **Action:** Update CORS initialization in `app/api/app.py` to sanitize wildcard credentials configuration.

### 3.6 Container & Deployment Hardening
- **Current State:** `Dockerfile` runs as `root` without a custom user.
- **Action:** Add `useradd -m -u 10001 appuser` and `USER appuser` in `Dockerfile`.

---

## 4. Remediation Plan

The audit findings will be remediated across Checkpoints 3.1 to 3.7:
1. **Checkpoint 3.1:** Document audit, adjust CORS security logic and image upload validation.
2. **Checkpoint 3.2:** Implement modular liveness detection layer.
3. **Checkpoint 3.3:** Run empirical threshold calibration script and document metrics.
4. **Checkpoint 3.4:** Implement OAuth2 Bearer / JWT administrative authentication.
5. **Checkpoint 3.5:** Implement in-memory rate limiting middleware with HTTP 429 responses.
6. **Checkpoint 3.6:** Enhance audit logs with security metadata (liveness results, client context).
7. **Checkpoint 3.7:** Production Docker hardening (non-root user, gunicorn/uvicorn configuration).

---

## 5. Verification

All tests run prior to audit: **40 passed, 0 failed, 0 skipped**.
Audited and verified.
