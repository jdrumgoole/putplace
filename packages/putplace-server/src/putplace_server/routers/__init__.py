"""Router modules for PutPlace API endpoints."""

from .files import router as files_router
from .users import router as users_router
from .api_keys import router as api_keys_router
from .pages import router as pages_router
from .admin import router as admin_router
from .uploads import deletion_router

__all__ = [
    "files_router",
    "users_router",
    "api_keys_router",
    "pages_router",
    "admin_router",
    "deletion_router",
]
