from typing import Optional
from app.config.settings import settings
from app.storage.base import BiometricRepository
from app.storage.local_repository import LocalBiometricRepository
from app.utils.logging import logger


def get_biometric_repository(
    storage_type: Optional[str] = None
) -> BiometricRepository:
    """
    Factory function providing repository abstraction based on configuration.
    Supports 'local' (JSON) and 'postgres' (PostgreSQL + pgvector).
    """
    backend = (
        storage_type or settings.biometric_storage or settings.storage_type
    ).strip().lower()

    if backend == "postgres":
        try:
            from app.storage.postgres_repository import PostgresBiometricRepository
            logger.info("Initializing PostgresBiometricRepository backend.")
            return PostgresBiometricRepository()
        except Exception as e:
            logger.error(
                f"Failed to initialize PostgresBiometricRepository: {e}. "
                "Falling back to LocalBiometricRepository."
            )
            return LocalBiometricRepository()

    logger.debug("Initializing LocalBiometricRepository backend.")
    return LocalBiometricRepository()
