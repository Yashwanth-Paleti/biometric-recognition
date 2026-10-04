from pathlib import Path
from fastapi import APIRouter
from fastapi.responses import FileResponse, RedirectResponse

router = APIRouter(tags=["Frontend"])

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
TEMPLATES_DIR = BASE_DIR / "templates"


@router.get("/", include_in_schema=False)
async def index():
    """Redirect root path to the attendance kiosk."""
    return RedirectResponse(url="/attendance")


@router.get("/register", include_in_schema=False)
async def register_page():
    """Serves the student registration and enrollment page."""
    return FileResponse(TEMPLATES_DIR / "register.html")


@router.get("/login", include_in_schema=False)
async def login_page():
    """Serves the student login page."""
    return FileResponse(TEMPLATES_DIR / "login.html")


@router.get("/dashboard", include_in_schema=False)
async def dashboard_page():
    """Serves the authenticated student attendance dashboard."""
    return FileResponse(TEMPLATES_DIR / "dashboard.html")


@router.get("/attendance", include_in_schema=False)
async def attendance_page():
    """Serves the common attendance recognition kiosk."""
    return FileResponse(TEMPLATES_DIR / "attendance.html")
