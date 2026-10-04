from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes.attendance import router as attendance_router
from app.api.routes.biometric import router as biometric_router
from app.api.routes.frontend import router as frontend_router
from app.api.routes.health import router as health_router
from app.api.routes.students import router as students_router
from app.api.schemas.biometric import ErrorResponse
from app.biometric.exceptions import BiometricError
from app.config.settings import settings
from app.utils.logging import logger

BASE_DIR = Path(__file__).resolve().parent.parent.parent
STATIC_DIR = BASE_DIR / "static"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifecycle events: startup and shutdown management."""
    logger.info("Starting Cloud-Based Biometric Authentication API...")
    logger.info(f"Active Storage Backend: {settings.biometric_storage}")
    logger.info(f"Biometric Match Threshold: {settings.biometric_match_threshold}")
    yield
    logger.info("Shutting down Biometric Authentication API.")


def create_app() -> FastAPI:
    """FastAPI application factory configuring middleware, routes, and error handlers."""
    app = FastAPI(
        title="Cloud-Based Biometric Authentication System",
        description=(
            "Production-ready biometric authentication service utilizing InsightFace Buffalo_L "
            "(512-dimensional normalized embeddings), PostgreSQL + pgvector vector persistence, "
            "and strict privacy-preserving architectural controls."
        ),
        version="2.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # CORS configuration (SEC-04: Disable credentials if wildcard origin is configured)
    allow_credentials = False if "*" in settings.cors_origins else True
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Centralized exception handlers preventing stack trace leakage
    @app.exception_handler(BiometricError)
    async def biometric_error_handler(request: Request, exc: BiometricError) -> JSONResponse:
        logger.warning(f"Biometric domain error: {exc.error_code} - {exc.message}")
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=ErrorResponse(
                detail=exc.message,
                error_code=exc.error_code,
            ).model_dump(),
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorResponse(
                detail=str(exc.detail),
                error_code=f"HTTP_{exc.status_code}",
            ).model_dump(),
            headers=exc.headers,
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.error(f"Unhandled server error: {exc}", exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(
                detail="An internal server error occurred. Please contact the administrator.",
                error_code="INTERNAL_SERVER_ERROR",
            ).model_dump(),
        )

    # Static files mounting
    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # Frontend UI routes
    app.include_router(frontend_router)

    # API v1 routes
    app.include_router(health_router, prefix="/api/v1")
    app.include_router(biometric_router, prefix="/api/v1")
    app.include_router(students_router, prefix="/api/v1")
    app.include_router(attendance_router, prefix="/api/v1")

    return app


app = create_app()
