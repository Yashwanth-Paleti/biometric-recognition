# Repository Cleanup Audit & Plan (Pre-Stage 2)

**Project Title:** Cloud-Based Biometric Authentication System  
**Stage:** Pre-Stage 2 Cleanup  
**Date:** September 2026  
**Auditor:** Senior Software Architect & Computer Vision Engineer  

---

## 1. Overview & Objective

Prior to commencing Stage 2 (FastAPI, PostgreSQL, `pgvector`, and Cloud Infrastructure), this audit establishes a strict inventory of all repository assets. The goal is to:
1. Isolate legacy student attendance scripts and data into an archived namespace (`legacy/`).
2. Eliminate generated caches, IDE artifacts, and temporary runtime output.
3. Protect sensitive biometric data and isolate legacy plaintext credentials.
4. Verify all import paths and test suites to guarantee zero breakage of the Stage 1 Biometric Core.

---

## 2. File and Directory Inventory

| File / Folder | Purpose | Used By | Status | Action | Reason |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `app/biometric/face_engine.py` | Encapsulated InsightFace inference engine | Stage 1 Core, `BiometricService` | **REQUIRED** | KEEP | Core detection & feature extraction engine |
| `app/biometric/matching.py` | Vector metric calculation (L2, Cosine) | Stage 1 Core, `BiometricService` | **REQUIRED** | KEEP | Mathematical matching abstraction |
| `app/biometric/embedding.py` | Vector normalization & dimension validation | Stage 1 Core | **REQUIRED** | KEEP | 512-d validation rules |
| `app/biometric/exceptions.py` | Domain-specific biometric exceptions | Stage 1 Core | **REQUIRED** | KEEP | Structured error handling |
| `app/biometric/__init__.py` | Biometric module exports | Stage 1 Core | **REQUIRED** | KEEP | Module interface |
| `app/models/biometric.py` | Domain dataclasses (`User`, `Template`, etc.) | Stage 1 Core, Services, Storage | **REQUIRED** | KEEP | Core domain entities |
| `app/models/__init__.py` | Model module exports | Stage 1 Core | **REQUIRED** | KEEP | Module interface |
| `app/services/biometric_service.py` | High-level authentication orchestrator | Stage 1 Core, CLI scripts | **REQUIRED** | KEEP | Main service interface for enroll/verify/identify |
| `app/services/__init__.py` | Service module exports | Stage 1 Core | **REQUIRED** | KEEP | Module interface |
| `app/storage/base.py` | `BiometricRepository` abstract interface | Stage 1 Core, Stage 2 PostgreSQL | **REQUIRED** | KEEP | Persistence abstraction |
| `app/storage/local_repository.py` | JSON-based template storage | Stage 1 Core | **REQUIRED** | KEEP | Local dev/testing repository |
| `app/storage/__init__.py` | Storage module exports | Stage 1 Core | **REQUIRED** | KEEP | Module interface |
| `app/config/settings.py` | Central Pydantic environment configuration | Stage 1 Core, Services, Storage | **REQUIRED** | KEEP | Centralized configuration |
| `app/config/__init__.py` | Config module exports | Stage 1 Core | **REQUIRED** | KEEP | Module interface |
| `app/utils/logging.py` | Sanitized structured logger | Stage 1 Core, Services, Scripts | **REQUIRED** | KEEP | Logging without vector/image leakage |
| `app/utils/__init__.py` | Utils module exports | Stage 1 Core | **REQUIRED** | KEEP | Module interface |
| `app/__init__.py` | Root app package init | Stage 1 Core | **REQUIRED** | KEEP | Package marker |
| `scripts/enroll.py` | CLI enrollment tool (image / webcam) | Developers, Demo | **REQUIRED** | KEEP | Stage 1 enrollment interface |
| `scripts/verify.py` | CLI 1:1 and 1:N verification tool | Developers, Demo | **REQUIRED** | KEEP | Stage 1 verification interface |
| `tests/test_biometric_service.py` | End-to-end service tests (7 core scenarios) | Test Suite | **REQUIRED** | KEEP | Core regression prevention |
| `tests/test_embedding.py` | Embedding generation & validation tests | Test Suite | **REQUIRED** | KEEP | Feature extraction testing |
| `tests/test_matching.py` | Vector metric & threshold tests | Test Suite | **REQUIRED** | KEEP | Math & matching testing |
| `data/.gitkeep` | Data directory placeholder | Git | **REQUIRED** | KEEP | Keeps data directory structure |
| `data/biometric_templates.json` | Active local template store (6 templates) | `LocalBiometricRepository` | **SENSITIVE / GENERATED** | KEEP LOCALLY / IGNORE | Active local template database; excluded from Git |
| `dataset/1_Malhar.jpg` | Enrolled sample face photo | `tests/test_biometric_service.py`, `tests/test_embedding.py` | **SENSITIVE / REQUIRED FOR TESTS** | KEEP LOCALLY | Required for model-dependent tests |
| `dataset/2_Harsh.jpg` | Enrolled sample face photo | `tests/test_biometric_service.py` | **SENSITIVE / REQUIRED FOR TESTS** | KEEP LOCALLY | Required for negative matching tests |
| `dataset/3_Meet.jpg` | Enrolled sample face photo | Local Demo | **SENSITIVE** | KEEP LOCALLY | Retained locally for multi-user demo |
| `dataset/4_Umang.jpg` | Enrolled sample face photo | Local Demo | **SENSITIVE** | KEEP LOCALLY | Retained locally for multi-user demo |
| `dataset/5_Sumeet.jpg` | Enrolled sample face photo | Local Demo | **SENSITIVE** | KEEP LOCALLY | Retained locally for multi-user demo |
| `dataset/4_Umang/` | Video-extracted burst face crops | Legacy demo | **SENSITIVE / LEGACY** | KEEP LOCALLY | Legacy frame samples |
| `dataset/students_fixed.csv` | Student roster & photo mappings | Legacy scripts (`student_dashboard.py`) | **LEGACY** | MOVE TO `legacy/` | Attendance domain object |
| `dataset/students_fixed.csv.xlsx`| Excel duplicate of student roster | Legacy reference | **LEGACY** | MOVE TO `legacy/` | Attendance domain object |
| `encodings/face_encodings.pickle`| Legacy binary pickle template store | Legacy scripts; already migrated to JSON | **LEGACY / SENSITIVE** | MOVE TO `legacy/encodings/` | Superseded by `data/biometric_templates.json` |
| `split_encodings/` | Pickles partitioned by branch/semester | Legacy scripts (`controller.py`) | **LEGACY** | MOVE TO `legacy/` | Attendance-specific partitions |
| `facial_gui_attendance.py` | Streamlit attendance tracking GUI | Legacy prototype | **LEGACY** | MOVE TO `legacy/` | Coupled to attendance domain |
| `controller.py` | Timetable-driven IP camera attendance | Legacy prototype | **LEGACY** | MOVE TO `legacy/` | Coupled to timetable & attendance CSVs |
| `recognize_and_mark_attendance.py` | Webcam attendance script | Legacy prototype | **LEGACY** | MOVE TO `legacy/` | Coupled to CSV attendance writing |
| `student_dashboard.py` | Streamlit attendance log viewer | Legacy prototype | **LEGACY** | MOVE TO `legacy/` | Coupled to attendance CSV log viewing |
| `app.py` | Flask schedule viewing portal | Legacy prototype | **LEGACY** | MOVE TO `legacy/` | Coupled to timetable viewing |
| `admin_login.py` | Streamlit admin login (hardcoded creds) | Legacy prototype | **LEGACY / SENSITIVE** | MOVE TO `legacy/` | Contains legacy credentials; isolated |
| `faculty_users.csv` | Unhashed faculty passwords | Legacy reference | **LEGACY / SENSITIVE** | MOVE TO `legacy/` | Contains legacy plaintext credentials |
| `launcher.py` | Role launcher subprocess spawner | Legacy prototype | **LEGACY** | MOVE TO `legacy/` | Launches old Streamlit interfaces |
| `register_student.py` | Procedural student enrollment script | Legacy prototype | **LEGACY** | MOVE TO `legacy/` | Superseded by `scripts/enroll.py` |
| `register_student_image.py` | Streamlit image enrollment script | Legacy prototype | **LEGACY** | MOVE TO `legacy/` | Superseded by `scripts/enroll.py` |
| `register_student_live.py` | Streamlit webcam enrollment script | Legacy prototype | **LEGACY** | MOVE TO `legacy/` | Superseded by `scripts/enroll.py` |
| `split_encodings.py` | Script splitting encodings by branch/semester | Legacy prototype | **LEGACY** | MOVE TO `legacy/` | Superseded by `LocalBiometricRepository` |
| `encode_faces.py` | Batch face encoding script | Legacy prototype | **LEGACY** | MOVE TO `legacy/` | Superseded by `BiometricService.enroll()` |
| `extract_faces_from_video.py` | Haar-cascade frame capture script | Legacy prototype | **LEGACY** | MOVE TO `legacy/` | Superseded by `FaceEngine` |
| `timetable.csv` | College class timetable | Legacy `app.py`, `controller.py` | **LEGACY** | MOVE TO `legacy/` | Pure attendance data |
| `camera_mapping.csv` | Class-to-camera RTSP/HTTP mapping | Legacy `controller.py` | **LEGACY** | MOVE TO `legacy/` | Attendance hardware config |
| `attendance_from_video.csv` | Output attendance CSV log | Legacy `recognize_and_mark_attendance.py` | **LEGACY / GENERATED** | MOVE TO `legacy/` | Attendance log output |
| `attendance_logs/` | Hierarchical attendance CSV log folder | Legacy `controller.py`, `student_dashboard.py` | **LEGACY / GENERATED** | MOVE TO `legacy/` | Attendance log output |
| `test_clip.mp4` | 2.4 MB sample video for attendance test | Legacy `controller.py` | **LEGACY** | MOVE TO `legacy/` | Not needed for biometric core |
| `templates/` | HTML templates for Flask schedule portal | Legacy `app.py` | **LEGACY** | MOVE TO `legacy/` | Web frontend for timetable |
| `static/` | CSS / JS assets for Flask portal | Legacy `app.py` | **LEGACY** | MOVE TO `legacy/` | Web frontend assets |
| `.idea/` | JetBrains / PyCharm project configuration | IDE | **GENERATED** | DELETE & IGNORE | Development tool cache |
| `__pycache__/` | Python bytecode cache folders | Python runtime | **GENERATED** | DELETE & IGNORE | Temporary build artifacts |
| `.pytest_cache/` | Pytest runtime cache | Pytest | **GENERATED** | DELETE & IGNORE | Temporary test artifacts |
| `.env.example` | Environment configuration template | All environments | **REQUIRED** | KEEP | Configuration template |
| `requirements.txt` | Project dependencies manifest | Package installer | **REQUIRED** | KEEP & RESTRUCTURE | Pinned dependencies |
| `README.md` | Primary project documentation | Developers, Evaluators | **REQUIRED** | KEEP | Project documentation |
| `docs/STAGE_1_AUDIT.md` | Stage 1 architecture and biometric audit | Documentation | **REQUIRED** | KEEP | Engineering audit document |
| `docs/REPOSITORY_CLEANUP.md` | Repository cleanup plan and report | Documentation | **REQUIRED** | KEEP | Pre-Stage 2 cleanup report |

---

## 3. Dependency Trace Summary

Before scheduling any moves or deletions, cross-module import tracing was performed:
1. **Core Package (`app/`):**
   - Zero imports from root or legacy files.
   - Depends only on standard libraries, `numpy`, `cv2`, `pydantic`, `insightface`, and `onnxruntime`.
2. **CLI Scripts (`scripts/`):**
   - Depends only on `app.services.biometric_service` and standard libraries.
   - Zero dependencies on legacy attendance scripts.
3. **Automated Tests (`tests/`):**
   - Depends on `app.biometric`, `app.models`, `app.services`, `app.storage`, and sample test images (`dataset/1_Malhar.jpg`, `dataset/2_Harsh.jpg`).
   - Zero dependencies on legacy attendance scripts or legacy CSV logs.
4. **Legacy Attendance System:**
   - Files like `facial_gui_attendance.py`, `controller.py`, `recognize_and_mark_attendance.py`, and `app.py` form an interconnected cluster that depends on `timetable.csv`, `camera_mapping.csv`, `attendance_logs/`, and `split_encodings/`.
   - Moving this entire cluster into `legacy/` cleanly preserves their internal relationships while isolating them completely from the active `app/` architecture.

---

## 4. Sensitive Data & Security Handling

1. **Legacy Plaintext Passwords (`faculty_users.csv`):**
   - Contains unhashed user credentials from the legacy prototype.
   - Moved into `legacy/` and removed from the active system path. Passwords are never logged or displayed.
2. **Hardcoded Administrative Credentials (`admin_login.py`):**
   - Contained hardcoded admin credentials in script source.
   - Moved into `legacy/` and completely decoupled from active biometric authentication.
3. **Biometric Encodings & Photos:**
   - Raw face photographs in `dataset/` are preserved locally for test execution (`1_Malhar.jpg`, `2_Harsh.jpg`) and local CLI verification demos.
   - Local JSON template store (`data/biometric_templates.json`) is maintained locally and strictly excluded from version control via `.gitignore`.
   - Legacy pickle file (`encodings/face_encodings.pickle`) is moved into `legacy/encodings/` as historical reference, since all templates have been successfully migrated to the new JSON structure.

---

## 5. Execution Plan

1. Create `legacy/` directory and `legacy/README.md`.
2. Move legacy attendance scripts, CSVs, logs, templates, static assets, and pickle files into `legacy/`.
3. Update `app/config/settings.py` default `LEGACY_PICKLE_PATH` to point to `legacy/encodings/face_encodings.pickle` if fallback import is ever triggered.
4. Remove IDE files (`.idea/`) and Python runtime caches (`__pycache__/`).
5. Update `.gitignore` with comprehensive rules.
6. Restructure `requirements.txt` to clearly distinguish core biometric dependencies from legacy dependencies.
7. Run the full test suite (`python -m pytest tests/ -v`) to confirm 19/19 tests pass.
8. Execute verification and enrollment CLI sanity checks.
