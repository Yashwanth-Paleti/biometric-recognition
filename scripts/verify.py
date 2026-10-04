#!/usr/bin/env python
"""
Biometric Authentication & Verification CLI Script
Performs 1:1 verification or 1:N identification against enrolled templates.
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


def capture_from_camera() -> any:
    """Captures a single frame from webcam after user confirmation."""
    import cv2
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("❌ Error: Unable to access webcam.")
        return None

    print("\n📷 Webcam active. Position face in frame.")
    print("👉 Press 's' to authenticate. Press 'q' to cancel.\n")

    captured_frame = None
    while True:
        ret, frame = cap.read()
        if not ret:
            print("❌ Failed to grab frame from camera.")
            break

        cv2.imshow("Authentication: Press 's' to authenticate, 'q' to quit", frame)
        key = cv2.waitKey(1) & 0xFF
        if key == ord('s'):
            captured_frame = frame
            break
        elif key == ord('q'):
            print("Authentication cancelled.")
            break

    cap.release()
    cv2.destroyAllWindows()
    return captured_frame


def main():
    parser = argparse.ArgumentParser(description="Authenticate or verify face against biometric templates.")
    parser.add_argument("--image", type=str, default=None, help="Path to probe image file")
    parser.add_argument("--user-id", type=str, default=None, help="Optional user ID for 1:1 verification. If omitted, runs 1:N identification.")
    parser.add_argument("--threshold", type=float, default=None, help="Custom matching distance threshold (default from settings)")
    parser.add_argument("--camera", action="store_true", help="Authenticate using connected webcam")

    args = parser.parse_args()

    service = BiometricService()

    image_input = None
    if args.camera:
        image_input = capture_from_camera()
        if image_input is None:
            sys.exit(1)
    elif args.image:
        image_path = Path(args.image)
        if not image_path.exists():
            print(f"❌ Error: Image file not found: {args.image}")
            sys.exit(1)
        image_input = str(image_path)
    else:
        print("❌ Error: Must specify --image <path> or --camera")
        parser.print_help()
        sys.exit(1)

    print("\n" + "=" * 55)
    if args.user_id:
        print("      BIOMETRIC 1:1 VERIFICATION")
        print(f"Claimed Identity: {args.user_id}")
    else:
        print("      BIOMETRIC 1:N IDENTIFICATION")
        print("Mode: Search across all active enrolled templates")
    print("=" * 55)

    print("⚙️  Extracting probe embedding and performing vector comparison...")
    if args.user_id:
        result = service.verify(
            user_id=args.user_id,
            image_input=image_input,
            threshold=args.threshold,
        )
    else:
        result = service.identify(
            image_input=image_input,
            threshold=args.threshold,
        )

    print("\n" + "-" * 55)
    print("DECISION SUMMARY:")
    print(f"  Authentication Succeeded: {'✅ YES' if result.matched else '❌ NO'}")
    print(f"  Matched User ID:          {result.user_id if result.user_id else 'None (Unknown)'}")
    if result.similarity is not None:
        print(f"  Cosine Similarity:        {result.similarity:.4f} (Higher is closer, max 1.0)")
    if result.distance is not None:
        print(f"  Euclidean L2 Distance:    {result.distance:.4f} (Lower is closer, min 0.0)")
    if result.threshold is not None:
        print(f"  Decision Threshold:       {result.threshold:.4f}")
    print(f"  Status Message:           {result.message}")
    if result.metadata:
        name = result.metadata.get("name")
        if name:
            print(f"  Enrolled Name:            {name}")
    print("-" * 55 + "\n")

    if not result.matched:
        sys.exit(1)


if __name__ == "__main__":
    main()
