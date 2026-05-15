"""HTML page routes for PutPlace web interface."""

from fastapi import APIRouter, Request
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


# regstack composes the email-link URLs as ``{base_url}/verify?token=…``,
# ``{base_url}/reset-password?token=…``, and ``{base_url}/confirm-email-change?token=…``
# with no UI prefix. Our regstack UI router is mounted at ``/account/*``, so
# bare paths would 404. Forward them on (preserving the query string).
@router.get("/verify")
async def verify_redirect(request: Request) -> RedirectResponse:
    target = "/account/verify"
    if request.url.query:
        target = f"{target}?{request.url.query}"
    return RedirectResponse(url=target, status_code=307)


@router.get("/reset-password")
async def reset_password_redirect(request: Request) -> RedirectResponse:
    target = "/account/reset"
    if request.url.query:
        target = f"{target}?{request.url.query}"
    return RedirectResponse(url=target, status_code=307)


@router.get("/confirm-email-change")
async def confirm_email_change_redirect(request: Request) -> RedirectResponse:
    target = "/account/confirm-email-change"
    if request.url.query:
        target = f"{target}?{request.url.query}"
    return RedirectResponse(url=target, status_code=307)


@router.get("/my_files", response_class=HTMLResponse)
async def my_files_page() -> str:
    """Display the user's uploaded files."""
    return get_my_files_page()
