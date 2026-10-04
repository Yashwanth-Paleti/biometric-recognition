# Legacy Attendance Prototype Archive

> **Notice:** These files belong to the original facial-recognition attendance prototype and are retained for historical and reference purposes. They are **not** part of the new Cloud-Based Biometric Authentication System architecture.

---

## 📜 Contents of This Archive

This directory isolates the legacy, attendance-specific implementation:

### 1. Attendance Web & GUI Interfaces
- `facial_gui_attendance.py`: Streamlit-based attendance tracking dashboard.
- `app.py`: Flask-based timetable schedule visualizer.
- `admin_login.py`: Legacy admin portal script.
- `launcher.py`: Subprocess spawner for selecting user roles.
- `student_dashboard.py`: Streamlit student attendance log viewer.

### 2. Timetable & Video Capture Scripts
- `controller.py`: Timetable-driven IP camera automation script.
- `recognize_and_mark_attendance.py`: Standalone webcam attendance logger.
- `extract_faces_from_video.py`: OpenCV Haar-cascade frame capture utility.

### 3. Student Registration Scripts
- `register_student.py`: Terminal-based student enrollment script.
- `register_student_image.py`: Image upload registration script.
- `register_student_live.py`: Webcam registration script.

### 4. Legacy Encodings & Split Scripts
- `encode_faces.py`: Batch encoding script generating `encodings/face_encodings.pickle`.
- `split_encodings.py`: Script partitioning encodings into branch/semester pickle files.
- `encodings/`: Binary pickle file with legacy face encodings (migrated to `data/biometric_templates.json`).
- `split_encodings/`: Branch and semester partitioned pickle files.

### 5. Attendance Schedules, Logs & Assets
- `timetable.csv`: Academic class timetable.
- `camera_mapping.csv`: Classroom-to-camera RTSP/HTTP map.
- `attendance_from_video.csv`: Video attendance output log.
- `attendance_logs/`: Hierarchical CSV logs organized by branch and semester.
- `faculty_users.csv`: Contains legacy plaintext credentials — isolated from active codebase.
- `students_fixed.csv` & `.xlsx`: Legacy student enrollment roster.
- `test_clip.mp4`: Sample video file used for attendance simulation.
- `templates/`: Flask HTML templates for the timetable portal.
- `static/`: CSS and client-side JavaScript for the timetable portal.

---

## 🚫 Relationship to New Architecture

None of the components in this `legacy/` directory are imported, executed, or required by the active `app/`, `scripts/`, or `tests/` directories.

For the active biometric core, refer to:
- `app/biometric/`
- `app/models/`
- `app/services/`
- `app/storage/`
- `scripts/verify.py` & `scripts/enroll.py`
