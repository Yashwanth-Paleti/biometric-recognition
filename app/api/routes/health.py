from fastapi import APIRouter
from app.api.schemas.biometric import HealthResponse
from app.config.settings import settings
from app.database.connection import check_database_health

router = APIRouter(tags=["Health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Service Health Check",
    description="Returns current service operational status, storage backend, and database health.",
)
async def health_check() -> HealthResponse:
    db_connected = None
    if settings.biometric_storage == "postgres" and settings.database_url:
        db_connected = check_database_health()

    return HealthResponse(
        status="healthy",
        version="2.0.0",
        storage_backend=settings.biometric_storage,
        database_connected=db_connected,
    )
