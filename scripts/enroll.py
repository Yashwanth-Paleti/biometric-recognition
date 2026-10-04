#!/usr/bin/env python
"""
Biometric Enrollment CLI Script
Enrolls a new biometric template from an image file or live camera capture.
"""
import argparse
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Ensure Windows PowerShell stdout handles Unicode cleanly
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.services.biometric_service import BiometricService
from app.utils.logging import logger


def capture_from_camera() -> any:
    """Captures a single frame from webcam after user confirmation."""
    import cv2
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("❌ Error: Unable to access webcam.")
        return None

    print("\n📷 Webcam opened. Position face in frame.")
    print("👉 Press 's' to capture photo. Press 'q' to cancel.\n")

    captured_frame = None
    while True:
        ret, frame = cap.read()
        if not ret:
            print("❌ Failed to grab frame from camera.")
            break

        cv2.imshow("Enrollment: Press 's' to capture, 'q' to cancel", frame)
        key = cv2.waitKey(1) & 0xFF
        if key == ord('s'):
            captured_frame = frame
            break
        elif key == ord('q'):
            print("Registration cancelled by user.")
            break

    cap.release()
    cv2.destroyAllWindows()
    return captured_frame


def main():
    parser = argparse.ArgumentParser(description="Enroll a new biometric template.")
    parser.add_argument("--user-id", type=str, required=True, help="Unique identifier for the user (e.g. roll_no or employee_id)")
    parser.add_argument("--name", type=str, default="User", help="Display name of the user")
    parser.add_argument("--image", type=str, default=None, help="Path to image file containing the user's face")
    parser.add_argument("--camera", action="store_true", help="Capture face directly from connected webcam")

    args = parser.parse_args()

    service = BiometricService()
    user_id = args.user_id.strip()
    name = args.name.strip()

    print("\n" + "=" * 50)
    print("      BIOMETRIC AUTHENTICATION: ENROLLMENT")
    print("=" * 50)
    print(f"Target User ID: {user_id}")
    print(f"Name:           {name}")

    image_input = None
    if args.camera:
        image_input = capture_from_camera()
        if image_input is None:
            print("❌ Enrollment cancelled.")
            sys.exit(1)
    elif args.image:
        image_path = Path(args.image)
        if not image_path.exists():
            print(f"❌ Error: Image file does not exist: {args.image}")
            sys.exit(1)
        image_input = str(image_path)
    else:
        print("❌ Error: Either --image <path> or --camera must be specified.")
        parser.print_help()
        sys.exit(1)

    print("⚙️  Processing face detection and generating biometric template...")
    result = service.enroll(
        user_id=user_id,
        image_input=image_input,
        metadata={"name": name, "source": "cli_enrollment"}
    )

    print("\n" + "-" * 50)
    print("RESULT:")
    print(f"  Success:      {result.success}")
    print(f"  Enrolled:     {result.matched}")
    print(f"  User ID:      {result.user_id}")
    print(f"  Message:      {result.message}")
    if result.metadata:
        print(f"  Template ID:  {result.metadata.get('template_id', 'N/A')}")
    print("-" * 50 + "\n")

    if not result.success:
        sys.exit(1)


if __name__ == "__main__":
    main()
