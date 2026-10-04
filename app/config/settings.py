import os
from pathlib import Path
from dotenv import load_dotenv
from typing import Optional
from pydantic import BaseModel, Field


# Base Directory of the Project
BASE_DIR = Path(__file__).resolve().parent.parent.parent

load_dotenv(BASE_DIR / ".env")

class Settings(BaseModel):
    """Application and Biometric Configuration Settings."""
    
    # Environment
    app_env: str = Field(default_factory=lambda: os.getenv("APP_ENV", "development"))
    
    # Biometric Match Threshold
    # Default Euclidean (L2) distance threshold based on Buffalo_L embeddings.
    # L2 distance < 0.85 corresponds to Cosine Similarity > ~0.64.
    # Note: Production calibration will establish rigorous FAR/FRR metrics in future stages.
    biometric_match_threshold: float = Field(
        default_factory=lambda: float(os.getenv("BIOMETRIC_MATCH_THRESHOLD", "0.85"))
    )
    
    # Model Configuration
    model_name: str = Field(default_factory=lambda: os.getenv("MODEL_NAME", "buffalo_l"))
    model_version: str = Field(default_factory=lambda: os.getenv("MODEL_VERSION", "1.0.0"))
    execution_provider: str = Field(
        default_factory=lambda: os.getenv("EXECUTION_PROVIDER", "CPUExecutionProvider")
    )
    
    # Face Detection & Quality Validation
    det_thresh: float = Field(default_factory=lambda: float(os.getenv("DETECTION_THRESHOLD", "0.5")))
    det_size: tuple[int, int] = (640, 640)
    enforce_single_face_enrollment: bool = Field(
        default_factory=lambda: os.getenv("ENFORCE_SINGLE_FACE_ENROLLMENT", "true").lower() in ("true", "1")
    )
    
    # Storage Configuration (Supports 'local' or 'postgres')
    biometric_storage: str = Field(
        default_factory=lambda: os.getenv("BIOMETRIC_STORAGE", os.getenv("STORAGE_TYPE", "local")).lower()
    )
    storage_type: str = Field(
        default_factory=lambda: os.getenv("BIOMETRIC_STORAGE", os.getenv("STORAGE_TYPE", "local")).lower()
    )
    database_url: Optional[str] = Field(
        default_factory=lambda: os.getenv("DATABASE_URL")
    )
    db_pool_size: int = Field(
        default_factory=lambda: int(os.getenv("DB_POOL_SIZE", "10"))
    )
    db_max_overflow: int = Field(
        default_factory=lambda: int(os.getenv("DB_MAX_OVERFLOW", "20"))
    )
    db_pool_timeout: int = Field(
        default_factory=lambda: int(os.getenv("DB_POOL_TIMEOUT", "30"))
    )
    local_storage_path: Path = Field(
        default_factory=lambda: BASE_DIR / os.getenv("LOCAL_STORAGE_PATH", "data/biometric_templates.json")
    )
    legacy_pickle_path: Path = Field(
        default_factory=lambda: BASE_DIR / os.getenv("LEGACY_PICKLE_PATH", "legacy/encodings/face_encodings.pickle")
    )
    
    # API & CORS Configuration
    api_host: str = Field(default_factory=lambda: os.getenv("API_HOST", "0.0.0.0"))
    api_port: int = Field(default_factory=lambda: int(os.getenv("API_PORT", "8000")))
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            origin.strip()
            for origin in os.getenv("CORS_ORIGINS", "*").split(",")
            if origin.strip()
        ]
    )
    
    # Logging Configuration
    log_level: str = Field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))


# Singleton settings instance
settings = Settings()
