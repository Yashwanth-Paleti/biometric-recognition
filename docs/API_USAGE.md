# API Usage & Reference Guide — v2.0.0

**Base URL:** `http://localhost:8000/api/v1` (Local) or `https://api.yourdomain.com/api/v1` (Production EC2)  
**OpenAPI Specification:** Available interactively at `/docs` (Swagger UI) and `/redoc` (ReDoc).  

---

## 1. Authentication (`POST /auth/token`)

Exchanges administrative credentials for a short-lived signed JWT Bearer access token.

- **Endpoint:** `POST /api/v1/auth/token`
- **Rate Limit:** 20 requests / minute / IP
- **Content-Type:** `application/x-www-form-urlencoded`

### Request Parameters (Form):
| Parameter | Type | Required | Description |
|---|---|---|---|
| `username` | `string` | Yes | Administrative username (configured in `ADMIN_USERNAME`) |
| `password` | `string` | Yes | Administrative password (configured in `ADMIN_PASSWORD`) |

### Example Request:
```bash
curl -X POST http://localhost:8000/api/v1/auth/token \
  -F "username=admin" \
  -F "password=AdminPass123!"
```

### Success Response (HTTP 200 OK):
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 3600
}
```

---

## 2. Health Check (`GET /health`)

Probes service health, database connectivity, and backend storage engine.

- **Endpoint:** `GET /api/v1/health`
- **Authentication:** Public (No token required)

### Example Request:
```bash
curl -X GET http://localhost:8000/api/v1/health
```

### Success Response (HTTP 200 OK):
```json
{
  "status": "healthy",
  "version": "2.0.0",
  "timestamp": "2026-10-04T12:00:00.000000Z",
  "storage_backend": "postgres",
  "database_connected": true
}
```

---

## 3. Biometric Enrollment (`POST /auth/enroll`)

Enrolls a new 512-dimensional facial biometric template. Requires single-face validation and liveness check.

- **Endpoint:** `POST /api/v1/auth/enroll`
- **Authentication:** **Bearer JWT Required** (`Authorization: Bearer <token>`)
- **Rate Limit:** 20 requests / minute / IP
- **Content-Type:** `multipart/form-data`

### Request Parameters:
| Field | Type | Required | Description |
|---|---|---|---|
| `user_id` | `string` | Yes | Unique enterprise / student identifier (e.g. `STU_1001`) |
| `name` | `string` | Yes | Display name of the subject |
| `image` | `file` | Yes | High-resolution face portrait (`.jpg`, `.png`, `.webp`, max 10MB) |

### Example Request:
```bash
curl -X POST http://localhost:8000/api/v1/auth/enroll \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -F "user_id=STU_1001" \
  -F "name=Alice Smith" \
  -F "image=@alice_portrait.jpg"
```

### Success Response (HTTP 201 Created):
```json
{
  "success": true,
  "user_id": "STU_1001",
  "message": "Biometric enrollment successful",
  "template_id": "b18f3a3d-3b98-4dc8-a89e-26f634563a92"
}
```

### Error Responses:
- `HTTP 400 Bad Request`: `{"detail": "No face detected in the provided image.", "error_code": "HTTP_400"}`
- `HTTP 400 Bad Request`: `{"detail": "Presentation attack detected: Liveness verification failed.", "error_code": "HTTP_400"}`
- `HTTP 401 Unauthorized`: `{"detail": "Authentication required. Missing Bearer token.", "error_code": "HTTP_401"}`

---

## 4. 1:1 Biometric Verification (`POST /auth/verify`)

Compares a live probe face photograph against enrolled templates for a claimed identity.

- **Endpoint:** `POST /api/v1/auth/verify`
- **Rate Limit:** 60 requests / minute / IP
- **Content-Type:** `multipart/form-data`

### Request Parameters:
| Field | Type | Required | Description |
|---|---|---|---|
| `user_id` | `string` | Yes | Claimed user identifier to verify against |
| `image` | `file` | Yes | Live probe face capture (max 10MB) |
| `threshold` | `float` | Optional | Custom Euclidean distance threshold (defaults to 0.85) |
| `device_id` | `string` | Optional | Identifier of camera / access gate for audit logging |

### Example Request:
```bash
curl -X POST http://localhost:8000/api/v1/auth/verify \
  -F "user_id=STU_1001" \
  -F "image=@probe_capture.jpg" \
  -F "device_id=GATE_WEST_01"
```

### Verified Response (HTTP 200 OK):
```json
{
  "authenticated": true,
  "user_id": "STU_1001",
  "similarity": 0.9125,
  "distance": 0.4183,
  "message": "Identity verified for user 'STU_1001'."
}
```

### Non-Matching Probe (HTTP 200 OK):
```json
{
  "authenticated": false,
  "user_id": "STU_1001",
  "similarity": 0.3512,
  "distance": 1.1391,
  "message": "Face does not match enrolled template for user 'STU_1001'."
}
```

---

## 5. 1:N Biometric Identification (`POST /auth/identify`)

Searches the entire gallery of enrolled biometric templates using pgvector similarity search.

- **Endpoint:** `POST /api/v1/auth/identify`
- **Rate Limit:** 30 requests / minute / IP
- **Content-Type:** `multipart/form-data`

### Request Parameters:
| Field | Type | Required | Description |
|---|---|---|---|
| `image` | `file` | Yes | Live probe face capture (max 10MB) |
| `threshold` | `float` | Optional | Custom distance threshold (defaults to 0.85) |
| `device_id` | `string` | Optional | Identifier of camera / access gate for audit trail |

### Example Request:
```bash
curl -X POST http://localhost:8000/api/v1/auth/identify \
  -F "image=@probe_capture.jpg" \
  -F "device_id=KIOSK_MAIN_LOBBY"
```

### Identified Response (HTTP 200 OK):
```json
{
  "authenticated": true,
  "user_id": "STU_1001",
  "similarity": 0.9084,
  "distance": 0.4280,
  "message": "Identity confirmed as 'STU_1001'."
}
```

### Unknown Face Response (HTTP 200 OK):
```json
{
  "authenticated": false,
  "user_id": null,
  "similarity": 0.3204,
  "distance": 1.1658,
  "message": "No matching identity found for the provided face."
}
```
