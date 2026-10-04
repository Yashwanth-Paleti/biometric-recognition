from pathlib import Path
from typing import Any, Optional, Union
import numpy as np

from app.biometric.exceptions import (
    BiometricError,
    EmbeddingExtractionError,
    InvalidImageError,
    LivenessCheckFailedError,
    MultipleFacesDetectedError,
    NoFaceDetectedError,
)
from app.biometric.face_engine import FaceEngine
from app.biometric.liveness import BaseLivenessDetector, get_liveness_detector
from app.biometric.matching import FaceMatcher
from app.config.settings import settings
from app.models.biometric import AuthenticationResult, BiometricTemplate, User
from app.storage.base import BiometricRepository
from app.storage.factory import get_biometric_repository
from app.utils.logging import logger


class BiometricService:
    """
    Core Domain Service for Biometric Authentication.
    Orchestrates FaceEngine, FaceMatcher, LivenessDetector, and BiometricRepository
    to provide structured, high-level verification, identification, and enrollment workflows.
    """

    def __init__(
        self,
        engine: Optional[FaceEngine] = None,
        matcher: Optional[FaceMatcher] = None,
        repository: Optional[BiometricRepository] = None,
        liveness_detector: Optional[BaseLivenessDetector] = None,
    ):
        self.engine = engine or FaceEngine()
        self.matcher = matcher or FaceMatcher()
        self.repository = repository or get_biometric_repository()
        self.liveness_detector = liveness_detector or get_liveness_detector()

    def extract_embedding(
        self,
        image_input: Union[str, Path, bytes, np.ndarray],
        require_single_face: bool = True,
    ) -> np.ndarray:
        """
        Extracts a normalized 512-dimensional embedding from image input.
        Propagates domain exceptions for specific error handling.
        """
        return self.engine.generate_embedding_from_image(
            image_input, require_single_face=require_single_face
        )

    def enroll(
        self,
        user_id: str,
        image_input: Union[str, Path, bytes, np.ndarray],
        metadata: Optional[dict[str, Any]] = None,
    ) -> AuthenticationResult:
        """
        Enrolls a new biometric template for the specified user_id.
        Enforces single-face validation.
        """
        if not user_id or not str(user_id).strip():
            logger.warning("Enrollment attempted without a valid user_id.")
            return AuthenticationResult(
                success=False,
                matched=False,
                error_code="INVALID_USER_ID",
                message="A valid, non-empty user_id is required for enrollment.",
            )

        user_id = str(user_id).strip()
        logger.info(f"Enrollment initiated for user: {user_id}")

        try:
            rgb_image = self.engine.process_image(image_input)
            faces = self.engine.detect_faces(rgb_image)

            if len(faces) == 0:
                raise NoFaceDetectedError()

            if settings.enforce_single_face_enrollment and len(faces) > 1:
                raise MultipleFacesDetectedError(
                    f"Detected {len(faces)} faces. Exactly 1 face is required for this operation."
                )

            primary_face = faces[0]
            liveness = self.liveness_detector.evaluate(rgb_image, primary_face)
            if not liveness.passed:
                logger.warning(
                    f"Enrollment rejected for user {user_id}: Liveness check failed "
                    f"(score={liveness.score:.4f}, method={liveness.method})"
                )
                return AuthenticationResult(
                    success=False,
                    matched=False,
                    user_id=user_id,
                    error_code="LIVENESS_CHECK_FAILED",
                    message="Biometric enrollment rejected: Presentation attack detected (liveness check failed).",
                    metadata={
                        "liveness_passed": False,
                        "liveness_score": round(liveness.score, 4),
                        "liveness_method": liveness.method,
                    },
                )

            embedding = self.engine.generate_embedding(primary_face)

            meta = dict(metadata or {})
            meta.update({
                "liveness_passed": True,
                "liveness_score": round(liveness.score, 4),
                "liveness_method": liveness.method,
            })

            template = BiometricTemplate(
                user_id=user_id,
                embedding=embedding,
                model_name=settings.model_name,
                model_version=settings.model_version,
                metadata=meta,
            )

            self.repository.save_template(template)
            logger.info(f"Enrollment succeeded for user: {user_id} (template_id: {template.template_id})")

            return AuthenticationResult(
                success=True,
                matched=True,
                user_id=user_id,
                message=f"Biometric template successfully enrolled for user '{user_id}'.",
                metadata={"template_id": template.template_id, **meta},
            )

        except NoFaceDetectedError:
            logger.warning(f"Enrollment failed for user {user_id}: No face detected.")
            return AuthenticationResult(
                success=False,
                matched=False,
                user_id=user_id,
                error_code="NO_FACE_DETECTED",
                message="Enrollment failed: No face detected in the provided image.",
            )

        except MultipleFacesDetectedError as e:
            logger.warning(f"Enrollment failed for user {user_id}: Multiple faces detected.")
            return AuthenticationResult(
                success=False,
                matched=False,
                user_id=user_id,
                error_code="MULTIPLE_FACES_DETECTED",
                message=str(e),
            )

        except InvalidImageError as e:
            logger.warning(f"Enrollment failed for user {user_id}: Invalid image. {e}")
            return AuthenticationResult(
                success=False,
                matched=False,
                user_id=user_id,
                error_code="INVALID_IMAGE",
                message=f"Enrollment failed: {e}",
            )

        except BiometricError as e:
            logger.error(f"Enrollment failed for user {user_id}: Biometric engine error: {e}")
            return AuthenticationResult(
                success=False,
                matched=False,
                user_id=user_id,
                error_code=e.error_code,
                message=e.message,
            )

        except Exception as e:
            logger.error(f"Unexpected error during enrollment for user {user_id}: {e}")
            return AuthenticationResult(
                success=False,
                matched=False,
                user_id=user_id,
                error_code="INTERNAL_ERROR",
                message=f"Internal enrollment error: {e}",
            )

    def _log_auth(
        self,
        user_id: Optional[str],
        verification_type: str,
        result: str,
        threshold: float,
        similarity: Optional[float] = None,
        distance: Optional[float] = None,
        error_code: Optional[str] = None,
        device_id: Optional[str] = None,
    ) -> None:
        """Audits biometric authentication events using repository logging interface."""
        if hasattr(self.repository, "log_authentication"):
            try:
                self.repository.log_authentication(
                    user_id=user_id,
                    verification_type=verification_type,
                    result=result,
                    threshold=threshold,
                    similarity=similarity,
                    distance=distance,
                    error_code=error_code,
                    device_id=device_id,
                )
            except Exception as e:
                logger.error(f"Failed to record audit log: {e}")

    def verify(
        self,
        user_id: str,
        image_input: Union[str, Path, bytes, np.ndarray],
        threshold: Optional[float] = None,
        device_id: Optional[str] = None,
    ) -> AuthenticationResult:
        """
        1:1 Verification: Compares probe image against enrolled templates for user_id.
        """
        user_id = str(user_id).strip()
        t = threshold if threshold is not None else self.matcher.default_threshold
        logger.info(f"Verification attempted for claimed user: {user_id} (threshold={t})")

        stored_templates = self.repository.get_templates(user_id)
        if not stored_templates:
            logger.warning(f"Verification failed: User '{user_id}' has no enrolled biometric templates.")
            self._log_auth(
                user_id=user_id,
                verification_type="1:1_VERIFICATION",
                result="FAILURE",
                threshold=t,
                error_code="USER_NOT_ENROLLED",
                device_id=device_id,
            )
            return AuthenticationResult(
                success=False,
                matched=False,
                user_id=user_id,
                threshold=t,
                error_code="USER_NOT_ENROLLED",
                message=f"No enrolled biometric templates found for user '{user_id}'.",
            )

        try:
            rgb_image = self.engine.process_image(image_input)
            faces = self.engine.detect_faces(rgb_image)

            if len(faces) == 0:
                raise NoFaceDetectedError()

            primary_face = faces[0]
            if len(faces) > 1:
                def box_area(f: Any) -> float:
                    bbox = getattr(f, "bbox", [0, 0, 0, 0])
                    return (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
                primary_face = max(faces, key=box_area)

            # Liveness evaluation BEFORE final biometric verification
            liveness = self.liveness_detector.evaluate(rgb_image, primary_face)
            if not liveness.passed:
                logger.warning(
                    f"Verification rejected for user '{user_id}': Liveness check failed "
                    f"(score={liveness.score:.4f}, method={liveness.method})"
                )
                self._log_auth(
                    user_id=user_id,
                    verification_type="1:1_VERIFICATION",
                    result="FAILURE",
                    threshold=t,
                    error_code="LIVENESS_CHECK_FAILED",
                    device_id=device_id,
                )
                return AuthenticationResult(
                    success=False,
                    matched=False,
                    user_id=user_id,
                    threshold=t,
                    error_code="LIVENESS_CHECK_FAILED",
                    message="Biometric authentication rejected: Presentation attack detected (liveness check failed).",
                    metadata={
                        "liveness_passed": False,
                        "liveness_score": round(liveness.score, 4),
                        "liveness_method": liveness.method,
                    },
                )

            query_embedding = self.engine.generate_embedding(primary_face)

            # Compare probe against all enrolled templates for this user; pick closest
            best_match, best_sim, best_dist = self.matcher.find_best_match(
                query_embedding, stored_templates, threshold=t
            )

            auth_meta = {
                "liveness_passed": True,
                "liveness_score": round(liveness.score, 4),
                "liveness_method": liveness.method,
            }

            if best_match is not None:
                logger.info(
                    f"Verification succeeded: Claimed user '{user_id}' verified "
                    f"(distance={best_dist:.4f}, similarity={best_sim:.4f})"
                )
                self._log_auth(
                    user_id=user_id,
                    verification_type="1:1_VERIFICATION",
                    result="SUCCESS",
                    threshold=t,
                    similarity=best_sim,
                    distance=best_dist,
                    device_id=device_id,
                )
                return AuthenticationResult(
                    success=True,
                    matched=True,
                    user_id=user_id,
                    similarity=best_sim,
                    distance=best_dist,
                    threshold=t,
                    message=f"Identity verified for user '{user_id}'.",
                    metadata={**best_match.metadata, **auth_meta},
                )
            else:
                logger.info(
                    f"Verification failed: Face does not match enrolled template for '{user_id}' "
                    f"(distance={best_dist:.4f} >= threshold={t})"
                )
                self._log_auth(
                    user_id=user_id,
                    verification_type="1:1_VERIFICATION",
                    result="FAILURE",
                    threshold=t,
                    similarity=best_sim,
                    distance=best_dist,
                    error_code="BIOMETRIC_MISMATCH",
                    device_id=device_id,
                )
                return AuthenticationResult(
                    success=True,
                    matched=False,
                    user_id=user_id,
                    similarity=best_sim,
                    distance=best_dist,
                    threshold=t,
                    error_code="BIOMETRIC_MISMATCH",
                    message=f"Face does not match enrolled template for user '{user_id}'.",
                )

        except NoFaceDetectedError:
            logger.warning(f"Verification failed for user {user_id}: No face detected.")
            self._log_auth(
                user_id=user_id,
                verification_type="1:1_VERIFICATION",
                result="FAILURE",
                threshold=t,
                error_code="NO_FACE_DETECTED",
                device_id=device_id,
            )
            return AuthenticationResult(
                success=False,
                matched=False,
                user_id=user_id,
                threshold=t,
                error_code="NO_FACE_DETECTED",
                message="Verification failed: No face detected in the image.",
            )

        except InvalidImageError as e:
            logger.warning(f"Verification failed for user {user_id}: Invalid image. {e}")
            self._log_auth(
                user_id=user_id,
                verification_type="1:1_VERIFICATION",
                result="FAILURE",
                threshold=t,
                error_code="INVALID_IMAGE",
                device_id=device_id,
            )
            return AuthenticationResult(
                success=False,
                matched=False,
                user_id=user_id,
                threshold=t,
                error_code="INVALID_IMAGE",
                message=f"Verification failed: {e}",
            )

        except BiometricError as e:
            logger.error(f"Verification biometric error for user {user_id}: {e}")
            self._log_auth(
                user_id=user_id,
                verification_type="1:1_VERIFICATION",
                result="FAILURE",
                threshold=t,
                error_code=e.error_code,
                device_id=device_id,
            )
            return AuthenticationResult(
                success=False,
                matched=False,
                user_id=user_id,
                threshold=t,
                error_code=e.error_code,
                message=e.message,
            )

        except Exception as e:
            logger.error(f"Unexpected error during verification for user {user_id}: {e}")
            self._log_auth(
                user_id=user_id,
                verification_type="1:1_VERIFICATION",
                result="FAILURE",
                threshold=t,
                error_code="INTERNAL_ERROR",
                device_id=device_id,
            )
            return AuthenticationResult(
                success=False,
                matched=False,
                user_id=user_id,
                threshold=t,
                error_code="INTERNAL_ERROR",
                message=f"Internal verification error: {e}",
            )

    def identify(
        self,
        image_input: Union[str, Path, bytes, np.ndarray],
        threshold: Optional[float] = None,
        device_id: Optional[str] = None,
    ) -> AuthenticationResult:
        """
        1:N Identification: Searches all enrolled templates for an identity matching probe image.
        Uses database-native pgvector similarity search when backed by PostgresBiometricRepository.
        """
        t = threshold if threshold is not None else self.matcher.default_threshold
        logger.info(f"1:N Identification attempted (threshold={t})")

        try:
            rgb_image = self.engine.process_image(image_input)
            faces = self.engine.detect_faces(rgb_image)

            if len(faces) == 0:
                raise NoFaceDetectedError()

            primary_face = faces[0]
            if len(faces) > 1:
                def box_area(f: Any) -> float:
                    bbox = getattr(f, "bbox", [0, 0, 0, 0])
                    return (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
                primary_face = max(faces, key=box_area)

            # Liveness evaluation BEFORE 1:N biometric search
            liveness = self.liveness_detector.evaluate(rgb_image, primary_face)
            if not liveness.passed:
                logger.warning(
                    f"Identification rejected: Liveness check failed "
                    f"(score={liveness.score:.4f}, method={liveness.method})"
                )
                self._log_auth(
                    user_id=None,
                    verification_type="1:N_IDENTIFICATION",
                    result="FAILURE",
                    threshold=t,
                    error_code="LIVENESS_CHECK_FAILED",
                    device_id=device_id,
                )
                return AuthenticationResult(
                    success=False,
                    matched=False,
                    user_id=None,
                    threshold=t,
                    error_code="LIVENESS_CHECK_FAILED",
                    message="Biometric identification rejected: Presentation attack detected (liveness check failed).",
                    metadata={
                        "liveness_passed": False,
                        "liveness_score": round(liveness.score, 4),
                        "liveness_method": liveness.method,
                    },
                )

            query_embedding = self.engine.generate_embedding(primary_face)

            # Use native pgvector similarity search if repository provides find_nearest_template
            if hasattr(self.repository, "find_nearest_template"):
                best_match, best_sim, best_dist = self.repository.find_nearest_template(
                    query_embedding, threshold=t
                )
            else:
                candidates = self.repository.get_all_templates()
                if not candidates:
                    logger.warning("Identification attempted but template repository is empty.")
                    self._log_auth(
                        user_id=None,
                        verification_type="1:N_IDENTIFICATION",
                        result="FAILURE",
                        threshold=t,
                        error_code="EMPTY_REPOSITORY",
                        device_id=device_id,
                    )
                    return AuthenticationResult(
                        success=False,
                        matched=False,
                        user_id=None,
                        threshold=t,
                        error_code="EMPTY_REPOSITORY",
                        message="No enrolled biometric templates exist in the database.",
                    )
                best_match, best_sim, best_dist = self.matcher.find_best_match(
                    query_embedding, candidates, threshold=t
                )

            if best_match is not None:
                logger.info(
                    f"Identification succeeded: Matched user '{best_match.user_id}' "
                    f"(distance={best_dist:.4f}, similarity={best_sim:.4f})"
                )
                self._log_auth(
                    user_id=best_match.user_id,
                    verification_type="1:N_IDENTIFICATION",
                    result="SUCCESS",
                    threshold=t,
                    similarity=best_sim,
                    distance=best_dist,
                    device_id=device_id,
                )
                return AuthenticationResult(
                    success=True,
                    matched=True,
                    user_id=best_match.user_id,
                    similarity=best_sim,
                    distance=best_dist,
                    threshold=t,
                    message=f"Identity confirmed as '{best_match.user_id}'.",
                    metadata=best_match.metadata,
                )
            else:
                logger.info(
                    f"Identification completed: No matching identity found within threshold: {t}"
                )
                self._log_auth(
                    user_id=None,
                    verification_type="1:N_IDENTIFICATION",
                    result="FAILURE",
                    threshold=t,
                    similarity=best_sim,
                    distance=best_dist,
                    error_code="NO_MATCH",
                    device_id=device_id,
                )
                return AuthenticationResult(
                    success=True,
                    matched=False,
                    user_id=None,
                    similarity=best_sim,
                    distance=best_dist,
                    threshold=t,
                    error_code="NO_MATCH",
                    message="No matching identity found for the provided face.",
                )

        except NoFaceDetectedError:
            logger.warning("Identification failed: No face detected in probe image.")
            self._log_auth(
                user_id=None,
                verification_type="1:N_IDENTIFICATION",
                result="FAILURE",
                threshold=t,
                error_code="NO_FACE_DETECTED",
                device_id=device_id,
            )
            return AuthenticationResult(
                success=False,
                matched=False,
                user_id=None,
                threshold=t,
                error_code="NO_FACE_DETECTED",
                message="Identification failed: No face detected in the image.",
            )

        except InvalidImageError as e:
            logger.warning(f"Identification failed: Invalid image: {e}")
            self._log_auth(
                user_id=None,
                verification_type="1:N_IDENTIFICATION",
                result="FAILURE",
                threshold=t,
                error_code="INVALID_IMAGE",
                device_id=device_id,
            )
            return AuthenticationResult(
                success=False,
                matched=False,
                user_id=None,
                threshold=t,
                error_code="INVALID_IMAGE",
                message=f"Identification failed: {e}",
            )

        except BiometricError as e:
            logger.error(f"Identification biometric error: {e}")
            self._log_auth(
                user_id=None,
                verification_type="1:N_IDENTIFICATION",
                result="FAILURE",
                threshold=t,
                error_code=e.error_code,
                device_id=device_id,
            )
            return AuthenticationResult(
                success=False,
                matched=False,
                user_id=None,
                threshold=t,
                error_code=e.error_code,
                message=e.message,
            )

        except Exception as e:
            logger.error(f"Unexpected error during identification: {e}")
            self._log_auth(
                user_id=None,
                verification_type="1:N_IDENTIFICATION",
                result="FAILURE",
                threshold=t,
                error_code="INTERNAL_ERROR",
                device_id=device_id,
            )
            return AuthenticationResult(
                success=False,
                matched=False,
                user_id=None,
                threshold=t,
                error_code="INTERNAL_ERROR",
                message=f"Internal identification error: {e}",
            )

