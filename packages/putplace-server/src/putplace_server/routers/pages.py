"""HTML page routes for PutPlace web interface."""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, RedirectResponse

from ..config import settings
from ..templates import (
    get_awaiting_confirmation_page,
    get_home_page,
    get_login_page,
    get_my_files_page,
    get_register_page,
)

router = APIRouter(tags=["pages"])


@router.get("/", response_class=HTMLResponse)
async def root() -> str:
    """Root endpoint - Home page."""
    return get_home_page(settings.api_version)


@router.get("/downloads")
async def downloads_page() -> RedirectResponse:
    """Redirect to the main website downloads page."""
    return RedirectResponse(url="https://putplace.org/downloads.html", status_code=301)


@router.get("/login", response_class=HTMLResponse)
async def login_page() -> str:
    """Login page."""
    return get_login_page()


@router.get("/register", response_class=HTMLResponse)
async def register_page() -> str:
    """Registration page."""
    return get_register_page()


@router.get("/awaiting-confirmation", response_class=HTMLResponse)
async def awaiting_confirmation_page(email: str = "") -> str:
    """Display the awaiting email confirmation page."""
    return get_awaiting_confirmation_page(email)


@router.get("/my_files", response_class=HTMLResponse)
async def my_files_page() -> str:
    """Display the user's uploaded files."""
    return get_my_files_page()
