# Stage 1 Audit: Architecture, Biometrics, and Security Review

**Project Title:** Cloud-Based Biometric Authentication System  
**Stage:** 1 — Repository Audit, Refactoring & Biometric Core  
**Date:** September 2026  
**Auditor:** Senior Software Architect & Computer Vision Engineer  

---

## 1. Existing Architecture Summary

The existing repository ([MalharBhatt-dev/Facial-Recognition-Attendance-System](https://github.com/MalharBhatt-dev/Facial-Recognition-Attendance-System)) was built as a proof-of-concept student facial recognition attendance system.

The codebase consists of:
1. **Flask Application (`app.py`):**
   - Implements a basic web portal with session-based login (`/login`) and a schedule dashboard (`/dashboard`).
   - Reads schedules directly from `timetable.csv` using `pandas`.
   - Has no direct connection to the face recognition engine; serves only as a static schedule visualizer for faculty.
2. **Streamlit Applications (`launcher.py`, `admin_login.py`, `facial_gui_attendance.py`, `student_dashboard.py`):**
   - Provide interactive dashboards for administrators (to register students and run attendance) and students (to view attendance records).
   - Use `subprocess.Popen` to spawn new Streamlit sub-processes dynamically.
3. **Core Biometric & Script Utilities:**
   - `encode_faces.py`: Batch extraction of face encodings from a student dataset CSV and image folder.
   - `register_student.py`, `register_student_image.py`, `register_student_live.py`: CLI and GUI enrollment workflows.
   - `recognize_and_mark_attendance.py`: Real-time webcam attendance tracking using OpenCV and InsightFace.
   - `controller.py`: Timetable-driven automated attendance via IP camera RTSP/HTTP streams.
   - `split_encodings.py`: Script grouping pickle encodings by branch and semester into individual pickle files.
   - `extract_faces_from_video.py`: Haar-cascade utility for frame sampling from video feeds.

---

## 2. Existing Biometric Pipeline

### Deep Learning Model
- **Library:** `insightface.app.FaceAnalysis` (running on `onnxruntime` engine).
- **Model Name:** `buffalo_l` (InsightFace Buffalo Large model family).
- **Execution Provider:** `CPUExecutionProvider` configured via `FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])`.
- **Initialization:** `face_app.prepare(ctx_id=0)` (called in `encode_faces.py`, `recognize_and_mark_attendance.py`, `controller.py`, `register_student.py`, etc.).

### Face Detection & Preprocessing
- **Detection Algorithm:** RetinaFace (integrated inside InsightFace `buffalo_l`).
- **Input Preprocessing:**
  - In `encode_faces.py`, `register_student.py`, and `controller.py`, images are loaded with OpenCV (`cv2.imread`), then color-converted: `rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)`.
  - In `recognize_and_mark_attendance.py` and `controller.py`, frames from video capture are resized (`cv2.resize(frame, (0, 0), fx=0.5, fy=0.5)`) and sampled with a frame-skipping factor (`frame_skip = 8` or `12`).
  - Face bounding boxes are extracted as `face.bbox.astype(int)`.

### Embedding Generation & Dimensionality
- **Embedding Property:** `face.normed_embedding` from InsightFace `Face` objects.
- **Dimensionality:** **512-dimensional vector** of `float32` values.
- **Vector Property:** L2-normalized ($||\mathbf{v}||_2 = 1.0$).
- **Handling of Edge Cases:**
  - *No face detected:* Returns an empty list (`faces = []`). Handled via simple `if not faces:` checks that abort or print warnings.
  - *Multiple faces detected:* In `encode_faces.py` and `register_student.py`, the code naively selects the first face index: `faces[0].normed_embedding`, silently ignoring any additional faces or background individuals. In `recognize_and_mark_attendance.py`, all detected faces are iterated in a loop.

### Matching & Comparison Logic
- **Distance Metric:** Euclidean ($L_2$) distance computed via NumPy:
  ```python
  dists = np.linalg.norm(known_encodings - embedding, axis=1)
  min_dist = np.min(dists)
  min_idx = np.argmin(dists)
  ```
- **Equivalence with Cosine Similarity:**
  Because the vectors are unit-normalized ($||\mathbf{a}|| = 1, ||\mathbf{b}|| = 1$):
  $$||\mathbf{a} - \mathbf{b}||_2^2 = ||\mathbf{a}||^2 + ||\mathbf{b}||^2 - 2(\mathbf{a} \cdot \mathbf{b}) = 2(1 - \cos(\theta))$$
  $$\cos(\theta) = 1 - \frac{||\mathbf{a} - \mathbf{b}||_2^2}{2}$$
- **Threshold Used:**
  - Hardcoded `tolerance = 0.85` (in `recognize_and_mark_attendance.py` line 27 and `controller.py` line 21).
  - Corresponding Cosine Similarity:
    $$\cos(\theta) = 1 - \frac{0.85^2}{2} = 1 - \frac{0.7225}{2} = 1 - 0.36125 = 0.63875$$
  - Pairs with $L_2 < 0.85$ (or $\text{similarity} > 0.64$) are declared matches.
  - While this is effective as a heuristic for local verification, it is not a calibrated false acceptance rate (FAR) threshold. A production biometric system requires tunable, calibrated thresholds.
- **Unknown Face Handling:**
  - If `min_dist >= tolerance`, identity is assigned `"Unknown"`. No attendance is recorded, and a red bounding box is drawn.

---

## 3. Existing Enrollment Pipeline

The existing enrollment mechanism is implemented across three files:
- `encode_faces.py` (offline batch script)
- `register_student.py` (interactive CLI)
- `register_student_image.py` / `register_student_live.py` (Streamlit UI components)

**Execution Flow:**
1. User provides metadata (Name, Roll Number, Semester, Branch, Section).
2. Image input is acquired via:
   - File upload (saved to `dataset/{roll_no}_{name}.jpg`).
   - Webcam capture using `cv2.VideoCapture(0)` on keypress `'s'`.
3. Image is passed to `extract_embedding(image_path)`:
   - InsightFace detects faces on RGB frame.
   - Extracts `faces[0].normed_embedding`.
4. Metadata is appended to `dataset/students_fixed.csv`.
5. The 512-d embedding is appended to `encodings/face_encodings.pickle` using Python `pickle.dump`.
6. `split_encodings.py` is called via `subprocess.run` to partition `face_encodings.pickle` into branch/semester files (e.g., `split_encodings/CE_3.pickle`).

**Limitations & Critical Issues:**
- Stores raw face images permanently in the local `dataset/` folder.
- Only captures 1 frame (single template enrollment), which is susceptible to pose/lighting variations.
- Overwrites/appends directly to binary pickle files on disk with no concurrency control, indexing, or transaction rollback.
- Tightly couples student academic properties (semester, branch, roll number) directly into the core face encoding structure.

---

## 4. Existing Recognition Pipeline

Implemented in `recognize_and_mark_attendance.py` and `controller.py`:
1. **Initialization:**
   - Loads `encodings/face_encodings.pickle` or a partition from `split_encodings/`.
   - Initializes `FaceAnalysis(name="buffalo_l")`.
2. **Video Capture:**
   - Opens webcam (`cv2.VideoCapture(0)`) or IP camera stream URL from `camera_mapping.csv`.
   - Loops over incoming frames, skipping $N$ frames (`FRAME_SKIP = 8` or `12`).
3. **Detection & Matching:**
   - Resizes frame down by 50% for speed.
   - Calls `face_app.get(rgb_small_frame)`.
   - For every detected face, calculates $L_2$ distance across all candidate vectors.
   - Matches if `min_dist < 0.85`.
4. **Attendance Recording:**
   - Deduplicates locally within the session using a Python set `seen_names`.
   - Appends record to `attendance_from_video.csv` or semester-partitioned CSVs in `attendance_logs/{branch}/{semester}/...csv`.
   - Overlays bounding boxes and name labels on frame using OpenCV GUI or Streamlit image containers.
   - Breaks loop once 5 unique students are recorded (`if len(seen_names) >= 5:`).

---

## 5. Storage Mechanism

| Data Element | Storage Technology | Location | Format | Risks |
|--------------|-------------------|----------|--------|-------|
| Biometric Encodings | Python `pickle` | `encodings/face_encodings.pickle`, `split_encodings/*.pickle` | Serialized Python dictionary (`{"encodings": [...], "metadata": [...]}`) | Insecure deserialization (`RCE` risk), unindexed search, no atomic updates |
| Student Records | Flat CSV / Excel | `dataset/students_fixed.csv`, `.xlsx` | Comma-Separated Values | No referential integrity, plain text storage |
| Attendance Logs | Flat CSVs | `attendance_logs/**/*.csv`, `attendance_from_video.csv` | Comma-Separated Values | Concurrency lock issues, unbounded directory sprawl |
| Faculty Users | Flat CSV | `faculty_users.csv` | Plain text (`username,password`) | Plaintext password storage |
| Raw Face Photos | Filesystem | `dataset/*.jpg` | JPEG image files | Biometric privacy violation, GDPR/compliance liability |

---

## 6. Authentication & Security Findings

1. **Unsafe Object Serialization (`pickle`):**
   - The entire biometric store relies on `pickle.load()` and `pickle.dump()`. In Python, unpickling untrusted data allows arbitrary code execution (ACE/RCE).
2. **Hardcoded Administrative Credentials:**
   - `admin_login.py` lines 8-11:
     ```python
     VALID_ADMINS = {
         "admin": "admin123",
         "teacher": "teachme"
     }
     ```
   - Cleartext credentials committed directly in version control.
3. **Hardcoded Flask Secret Key:**
   - `app.py` line 6:
     ```python
     app.secret_key = 'your_secret_key'
     ```
   - Invalidates session signature security.
4. **Plaintext Password Storage:**
   - `faculty_users.csv` stores user credentials in unhashed plaintext:
     ```csv
     username,password
     umang,1234
     anita,abcd
     ravi,pass123
     ```
5. **Raw Biometric Image Retention:**
   - The system stores unencrypted raw face photographs (`dataset/*.jpg`) alongside metadata. Best-practice biometric systems should retain only one-way feature embeddings and discard raw images unless explicit enrollment audit policies mandate secure, encrypted archiving.
6. **Subprocess Injection Risks:**
   - Multiple files (`launcher.py`, `admin_login.py`, `register_student.py`) execute `subprocess.Popen` or `subprocess.run` to invoke other Python scripts using hardcoded shell commands.

---

## 7. Problems That Must Be Removed / Refactored

1. **Tight Coupling to Attendance Domain:**
   - Attendance logic (classrooms, timetables, branches, semesters, CSV log generation) is directly entangled with face detection and feature extraction.
2. **Scattered InsightFace Initialization:**
   - InsightFace model initialization (`FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])`) is duplicated across 6+ separate files without encapsulation or centralized lifecycle management.
3. **Hardcoded Thresholds:**
   - Distance tolerance `0.85` is hardcoded as magic numbers inside procedural loops.
4. **Silent Single-Face Assumption:**
   - `faces[0]` is accessed directly without verifying whether multiple individuals are in the frame, creating biometric ambiguity.
5. **No Modular Interface:**
   - Functions are procedural scripts with inline UI rendering (`st.*` or `cv2.imshow`), preventing reuse in API or headless server environments.

---

## 8. Components Worth Reusing

1. **InsightFace Inference Pipeline:**
   - The `FaceAnalysis(name="buffalo_l")` setup and `normed_embedding` extraction are proven, fast, and produce high-quality 512-dimensional embeddings.
2. **Normalized Distance Mathematics:**
   - Euclidean distance comparison against unit-normalized embeddings is mathematically sound and maps directly to vector cosine distance.
3. **Existing Stored Biometric Templates:**
   - The 5 enrolled students in `encodings/face_encodings.pickle` provide verified ground truth for regression testing without needing to re-enroll sample users.

---

## 9. Components That Should Be Replaced

1. **Direct `pickle` Storage:**
   - Replace with a storage abstraction layer (`BiometricRepository`) with an initial `LocalBiometricRepository` (using JSON/NumPy serialization) that can seamlessly transition to PostgreSQL + `pgvector` in Stage 2.
2. **Script-based Enrollment and Verification:**
   - Replace procedural scripts with a unified `BiometricService` that exposes clean `verify()`, `identify()`, and `enroll()` methods.
3. **Hardcoded Credentials:**
   - Replace hardcoded secrets and paths with a centralized configuration system (`settings.py`) driven by environment variables (`.env`).
4. **Procedural UI Loops:**
   - Extract the computer vision and matching logic into pure functions/classes that return structured domain data models (`AuthenticationResult`, `BiometricVerification`).

---

## 10. Proposed Stage 1 Architecture

```
                               ┌────────────────────────────────┐
                               │  Client Input (Image / Stream) │
                               └───────────────┬────────────────┘
                                               │
                                               ▼
                               ┌────────────────────────────────┐
                               │   FaceEngine (InsightFace)     │
                               │  - Model initialization        │
                               │  - Multi-face validation       │
                               │  - 512-d normalized embedding  │
                               └───────────────┬────────────────┘
                                               │
                                               ▼
                               ┌────────────────────────────────┐
                               │     FaceMatcher                │
                               │  - L2 & Cosine calculations    │
                               │  - Configurable threshold      │
                               │  - Nearest neighbor selection  │
                               └───────────────┬────────────────┘
                                               │
                                               ▼
                               ┌────────────────────────────────┐
                               │     BiometricService           │
                               │  - Business logic orchestration│
                               │  - Structured result generation│
                               │  - Status & Error handling     │
                               └───────┬────────────────┬───────┘
                                       │                │
            ┌──────────────────────────┘                └──────────────────────────┐
            ▼                                                                      ▼
┌───────────────────────────────┐                                  ┌───────────────────────────────┐
│     Domain Models             │                                  │   BiometricRepository (Store) │
│ - User                        │                                  │ - LocalBiometricRepository    │
│ - BiometricTemplate (512-d)   │                                  │   (Stage 1: Local Storage)    │
│ - AuthenticationAttempt       │                                  │ - Cloud / pgvector Adapter    │
│ - AuthenticationResult        │                                  │   (Stage 2: PostgreSQL)       │
└───────────────────────────────┘                                  └───────────────────────────────┘
```

### Module Responsibilities:
- `app/config/settings.py`: Central configuration loaded via `pydantic-settings` or `python-dotenv`.
- `app/utils/logging.py`: Structured, sanitized logging ensuring zero leakage of raw images or biometric vectors.
- `app/models/biometric.py`: Strict domain dataclasses representing entities and verification results.
- `app/biometric/face_engine.py`: Encapsulated wrapper around InsightFace/RetinaFace detection and embedding generation.
- `app/biometric/matching.py`: Pure mathematical matcher with threshold evaluation.
- `app/storage/base.py` & `local_repository.py`: Storage interfaces insulating the core from the underlying persistence layer.
- `app/services/biometric_service.py`: High-level orchestration for enrollment, verification, and identification.
- `scripts/verify.py` & `scripts/enroll.py`: Clean CLI verification and enrollment tools.

---

## 11. Stage 2 Preparation

Stage 1 strictly establishes a decoupled, robust local biometric core. In Stage 2, the following migrations will be performed seamlessly without touching the biometric engine:
1. **Replace `LocalBiometricRepository`** with `PostgresBiometricRepository` using SQLAlchemy and `pgvector` for ANN vector indexing (`ivfflat` or `hnsw`).
2. **Introduce FastAPI Cloud API Layer** exposing `/api/v1/biometrics/enroll`, `/api/v1/biometrics/verify`, and `/api/v1/biometrics/identify`.
3. **Add Cloud Storage Adapter** (AWS S3 or equivalent) for secure, encrypted temporary capture caching.
4. **Issue JWT / Session Tokens** upon successful biometric authentication.
