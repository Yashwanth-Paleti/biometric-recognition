/**
 * Cloud Biometric Attendance Portal — Frontend Utilities
 */

const STORAGE_KEY_TOKEN = "attendance_student_token";
const STORAGE_KEY_STUDENT = "attendance_student_info";

// Token Helpers
function getAuthToken() {
  return localStorage.getItem(STORAGE_KEY_TOKEN);
}

function setAuthToken(token, studentInfo) {
  localStorage.setItem(STORAGE_KEY_TOKEN, token);
  localStorage.setItem(STORAGE_KEY_STUDENT, JSON.stringify(studentInfo || {}));
}

function getStoredStudent() {
  const data = localStorage.getItem(STORAGE_KEY_STUDENT);
  try {
    return data ? JSON.parse(data) : null;
  } catch (e) {
    return null;
  }
}

function logoutStudent() {
  localStorage.removeItem(STORAGE_KEY_TOKEN);
  localStorage.removeItem(STORAGE_KEY_STUDENT);
  window.location.href = "/login";
}

// Authenticated fetch wrapper
async function apiFetch(url, options = {}) {
  const token = getAuthToken();
  const headers = options.headers || {};
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  options.headers = headers;
  return fetch(url, options);
}

// Camera Management Helper
class CameraManager {
  constructor(videoElement, canvasElement) {
    this.video = videoElement;
    this.canvas = canvasElement;
    this.stream = null;
  }

  async start() {
    try {
      this.stream = await navigator.mediaDevices.getUserMedia({
        video: {
          width: { ideal: 1280 },
          height: { ideal: 720 },
          facingMode: "user"
        },
        audio: false
      });
      this.video.srcObject = this.stream;
      await this.video.play();
      return true;
    } catch (err) {
      console.warn("Webcam access unavailable or denied:", err);
      return false;
    }
  }

  stop() {
    if (this.stream) {
      this.stream.getTracks().forEach(track => track.stop());
      this.stream = null;
    }
  }

  captureBlob() {
    return new Promise((resolve) => {
      const width = this.video.videoWidth || 640;
      const height = this.video.videoHeight || 480;
      this.canvas.width = width;
      this.canvas.height = height;
      const ctx = this.canvas.getContext("2d");
      // Un-mirror image when drawing to canvas for facial recognition
      ctx.translate(width, 0);
      ctx.scale(-1, 1);
      ctx.drawImage(this.video, 0, 0, width, height);
      this.canvas.toBlob((blob) => {
        resolve(blob);
      }, "image/jpeg", 0.95);
    });
  }
}
