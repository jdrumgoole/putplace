"""HTML page routes for PutPlace web interface."""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, RedirectResponse

from ..config import settings
from ..templates import get_home_page, get_my_files_page

router = APIRouter(tags=["pages"])


@router.get("/", response_class=HTMLResponse)
async def root() -> str:
    """Root endpoint - Home page."""
    return get_home_page(settings.api_version)


@router.get("/downloads")
async def downloads_page() -> RedirectResponse:
    """Redirect to the main website downloads page."""
    return RedirectResponse(url="https://putplace.org/downloads.html", status_code=301)


@router.get("/login")
async def login_page() -> RedirectResponse:
    """Auth UI is owned by regstack — bounce to its login page."""
    return RedirectResponse(url="/account/login", status_code=307)


@router.get("/register")
async def register_page() -> RedirectResponse:
    """Auth UI is owned by regstack — bounce to its registration page."""
    return RedirectResponse(url="/account/register", status_code=307)


@router.get("/my_files", response_class=HTMLResponse)
async def my_files_page() -> str:
    """Display the user's uploaded files."""
    return get_my_files_page()
