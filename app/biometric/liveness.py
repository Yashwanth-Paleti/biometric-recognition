"""
Biometric Liveness Detection & Presentation Attack Detection (PAD) Module.

CRITICAL ARCHITECTURAL CONTEXT & DISCLAIMER:
In compliance with biometric security guidelines (ISO/IEC 30107-3) and Stage 3 requirements:
Single-frame passive liveness heuristics analyze texture granularity (Laplacian variance),
Fourier spatial frequency energy distribution (2D FFT), and chrominance diversity (YCrCb/HSV).
While effective at rejecting coarse presentation attacks (printed photographs, blurred replays,
and low-resolution screen replays), single-frame passive analysis DOES NOT substitute for
active challenge-response protocols (e.g. randomized blink, 3D depth sensors, or motion parallax).
This module is structured modularly so stronger deep-learning anti-spoofing models (e.g., MiniFASNet)
can be swapped in seamlessly.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional
import cv2
import numpy as np

from app.biometric.exceptions import LivenessCheckFailedError
from app.config.settings import settings
from app.utils.logging import logger


@dataclass
class LivenessResult:
    """Internal evaluation record for presentation attack detection."""
    passed: bool
    score: float  # Normalized score in [0.0, 1.0] where >= threshold indicates live human
    method: str
    details: dict[str, Any] = field(default_factory=dict)
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "liveness_passed": self.passed,
            "liveness_score": round(self.score, 4),
            "liveness_method": self.method,
            "details": self.details,
            "message": self.message,
        }


class BaseLivenessDetector(ABC):
    """Abstract contract for presentation attack / liveness detection implementations."""

    @abstractmethod
    def evaluate(self, image_rgb: np.ndarray, face: Optional[Any] = None) -> LivenessResult:
        """
        Evaluates facial presentation liveness.
        
        Args:
            image_rgb: Full RGB image as a numpy array.
            face: Optional InsightFace detected Face object with bbox coordinates.
            
        Returns:
            LivenessResult detailing decision, score, and diagnostic metrics.
        """
        pass


class PassiveTextureFrequencyLivenessDetector(BaseLivenessDetector):
    """
    Modular MVP Passive Anti-Spoofing Detector.
    
    Combines three orthogonal biometric signal evaluations on the facial ROI:
    1. Micro-texture & Sharpness Analysis (Laplacian Variance):
       Detects extreme blur (printed copies, re-captured screens) or unnatural flat gradients.
    2. Fourier Spatial Frequency Spectrum (2D FFT):
       Screen recaptures and digital displays produce distinctive pixel-grid aliasing
       and high-frequency periodic attenuation.
    3. Chrominance & Color Distribution (YCrCb & HSV Analysis):
       Human facial tissue under natural illumination exhibits rich, continuous
       chrominance dispersion in Cr and Cb channels, whereas paper prints and LCD
       panels exhibit gamut clipping.
    """

    def __init__(self, threshold: Optional[float] = None):
        self.threshold = threshold if threshold is not None else settings.liveness_threshold
        self.method_name = "passive_texture_frequency_v1"

    def _extract_face_roi(self, image_rgb: np.ndarray, face: Optional[Any] = None) -> np.ndarray:
        """Extracts and pads face bounding box from image."""
        h, w = image_rgb.shape[:2]
        if face is not None and hasattr(face, "bbox"):
            bbox = face.bbox.astype(int)
            x1, y1, x2, y2 = bbox[0], bbox[1], bbox[2], bbox[3]
            # Add 10% padding
            pad_w = int((x2 - x1) * 0.10)
            pad_h = int((y2 - y1) * 0.10)
            x1 = max(0, x1 - pad_w)
            y1 = max(0, y1 - pad_h)
            x2 = min(w, x2 + pad_w)
            y2 = min(h, y2 + pad_h)
            roi = image_rgb[y1:y2, x1:x2]
            if roi.size > 0:
                return roi

        # Fallback to center 60% crop if no bbox
        cy1, cy2 = int(h * 0.2), int(h * 0.8)
        cx1, cx2 = int(w * 0.2), int(w * 0.8)
        return image_rgb[cy1:cy2, cx1:cx2]

    def _eval_texture_laplacian(self, gray_roi: np.ndarray) -> tuple[float, float]:
        """
        Calculates Laplacian variance to assess micro-texture sharpness.
        Returns: (normalized_score [0,1], raw_variance)
        """
        lap = cv2.Laplacian(gray_roi, cv2.CV_64F)
        var = float(lap.var())

        # Realistic focused human face typically exhibits variance between 30 and 1500.
        # < 20: blurred presentation attack (e.g. out of focus print / replay)
        # > 3000: unnatural high-frequency moire pattern / sensor noise
        if var < 15.0:
            score = max(0.05, var / 30.0)
        elif 15.0 <= var <= 1500.0:
            # Map smoothly into [0.65, 1.0]
            score = 0.65 + 0.35 * min(1.0, (var - 15.0) / 300.0)
        else:
            # High frequency noise penalty
            score = max(0.2, 1.0 - (var - 1500.0) / 2500.0)

        return float(np.clip(score, 0.0, 1.0)), var

    def _eval_fourier_spectrum(self, gray_roi: np.ndarray) -> tuple[float, float]:
        """
        Calculates 2D FFT spatial frequency distribution.
        Measures ratio of high-to-low spatial frequencies.
        Returns: (normalized_score [0,1], high_freq_ratio)
        """
        resized = cv2.resize(gray_roi, (128, 128))
        f = np.fft.fft2(resized.astype(np.float32))
        fshift = np.fft.fftshift(f)
        magnitude = np.abs(fshift)

        h, w = magnitude.shape
        cy, cx = h // 2, w // 2
        r_inner = 16
        r_outer = 48

        # Create radial masks
        y, x = np.ogrid[:h, :w]
        dist_from_center = np.sqrt((x - cx) ** 2 + (y - cy) ** 2)

        low_mask = dist_from_center <= r_inner
        mid_high_mask = (dist_from_center > r_inner) & (dist_from_center <= r_outer)

        low_energy = np.sum(magnitude[low_mask]) + 1e-6
        mid_high_energy = np.sum(magnitude[mid_high_mask])

        ratio = float(mid_high_energy / low_energy)

        # Natural faces have balanced mid-high frequency energy (ratio approx 0.08 to 0.40)
        # Flat prints have ratio < 0.04; Screen pixel grids produce distinct spikes > 0.60
        if ratio < 0.03:
            score = max(0.1, ratio / 0.06)
        elif 0.03 <= ratio <= 0.45:
            score = 0.70 + 0.30 * min(1.0, (ratio - 0.03) / 0.15)
        else:
            score = max(0.2, 1.0 - (ratio - 0.45) / 0.40)

        return float(np.clip(score, 0.0, 1.0)), ratio

    def _eval_color_diversity(self, roi_rgb: np.ndarray) -> tuple[float, float, float]:
        """
        Calculates chrominance standard deviation in YCrCb color space.
        Returns: (normalized_score [0,1], cr_std, cb_std)
        """
        ycrcb = cv2.cvtColor(roi_rgb, cv2.COLOR_RGB2YCrCb)
        cr = ycrcb[:, :, 1]
        cb = ycrcb[:, :, 2]

        cr_std = float(np.std(cr))
        cb_std = float(np.std(cb))

        # Real facial skin exhibits continuous chrominance variation (cr_std > 3.0, cb_std > 3.0)
        # Greyscale prints or compressed screen images show cr_std / cb_std < 2.0
        avg_std = (cr_std + cb_std) / 2.0
        if avg_std < 2.0:
            score = max(0.05, avg_std / 4.0)
        else:
            score = min(1.0, 0.50 + 0.50 * (avg_std - 2.0) / 6.0)

        return float(np.clip(score, 0.0, 1.0)), cr_std, cb_std

    def evaluate(self, image_rgb: np.ndarray, face: Optional[Any] = None) -> LivenessResult:
        """
        Executes modular passive liveness evaluation across texture, Fourier, and color domains.
        """
        try:
            roi_rgb = self._extract_face_roi(image_rgb, face)
            if roi_rgb.size == 0 or roi_rgb.shape[0] < 20 or roi_rgb.shape[1] < 20:
                logger.warning("Liveness evaluation received degenerate face ROI.")
                return LivenessResult(
                    passed=False,
                    score=0.0,
                    method=self.method_name,
                    details={"error": "ROI too small or degenerate"},
                    message="Degenerate face ROI for liveness evaluation.",
                )

            roi_gray = cv2.cvtColor(roi_rgb, cv2.COLOR_RGB2GRAY)

            # Evaluate components
            tex_score, lap_var = self._eval_texture_laplacian(roi_gray)
            fourier_score, fourier_ratio = self._eval_fourier_spectrum(roi_gray)
            color_score, cr_std, cb_std = self._eval_color_diversity(roi_rgb)

            # Weighted combination
            composite_score = float(
                0.40 * tex_score + 0.35 * fourier_score + 0.25 * color_score
            )
            composite_score = float(np.clip(composite_score, 0.0, 1.0))

            passed = bool(composite_score >= self.threshold)

            msg = (
                "Liveness verified"
                if passed
                else f"Liveness check failed (score {composite_score:.3f} < threshold {self.threshold:.3f})"
            )

            logger.info(
                f"Liveness evaluated: passed={passed}, score={composite_score:.4f}, "
                f"tex={tex_score:.3f} (var={lap_var:.1f}), "
                f"fft={fourier_score:.3f} (ratio={fourier_ratio:.3f}), "
                f"color={color_score:.3f} (cr_std={cr_std:.1f}, cb_std={cb_std:.1f})"
            )

            return LivenessResult(
                passed=passed,
                score=composite_score,
                method=self.method_name,
                details={
                    "texture_score": round(tex_score, 4),
                    "laplacian_variance": round(lap_var, 2),
                    "fourier_score": round(fourier_score, 4),
                    "fourier_ratio": round(fourier_ratio, 4),
                    "color_score": round(color_score, 4),
                    "cr_std": round(cr_std, 2),
                    "cb_std": round(cb_std, 2),
                    "threshold": self.threshold,
                },
                message=msg,
            )

        except Exception as e:
            logger.error(f"Error during liveness evaluation: {e}")
            # Fail closed on unexpected exception for security
            return LivenessResult(
                passed=False,
                score=0.0,
                method=self.method_name,
                details={"error": str(e)},
                message=f"Liveness processing error: {e}",
            )


class PassThroughLivenessDetector(BaseLivenessDetector):
    """Fallback detector used when liveness is disabled in development/testing."""

    def evaluate(self, image_rgb: np.ndarray, face: Optional[Any] = None) -> LivenessResult:
        return LivenessResult(
            passed=True,
            score=1.0,
            method="passthrough",
            details={"mode": "disabled"},
            message="Liveness evaluation bypassed (passthrough mode).",
        )


def get_liveness_detector() -> BaseLivenessDetector:
    """Factory creating the active liveness detector based on system configuration."""
    if not settings.liveness_enabled:
        logger.info("Liveness detection is disabled via configuration. Using PassThroughLivenessDetector.")
        return PassThroughLivenessDetector()
    return PassiveTextureFrequencyLivenessDetector(threshold=settings.liveness_threshold)
