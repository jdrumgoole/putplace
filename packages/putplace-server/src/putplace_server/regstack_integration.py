"""regstack integration for PutPlace (Phase 1: side-by-side).

Constructs the embedded regstack instance with putplace's MongoDB connection,
all regstack collections scoped under a ``regstack_*`` prefix so they cannot
collide with putplace's existing ``users`` and ``pending_users`` collections.

This module exists for the duration of the migration. Once Phase 2 renames
the collections and Phase 3 cuts over the endpoints, the scoping prefix is
removed and this module simplifies.

See ``tasks/todo.md`` for the migration plan.
"""

from __future__ import annotations

import asyncio
import atexit
import logging
import os
import secrets
from pathlib import Path

from pydantic import AnyHttpUrl, SecretStr
from regstack import RegStack, RegStackConfig
from regstack.config.schema import EmailConfig, OAuthConfig

from .config import settings

_BRANDED_TEMPLATES_DIR = Path(__file__).parent / "regstack_email_templates"

logger = logging.getLogger(__name__)


_PHASE1_COLLECTION_PREFIX = "regstack_"


def _resolve_mongodb_database() -> str:
    """Return the per-worker test database name when running under pytest-xdist.

    The conftest preamble sets ``MONGODB_DATABASE`` based on
    ``PYTEST_XDIST_WORKER``, but xdist exports that env var *after*
    ``conftest.py`` is imported in each worker subprocess, so the preamble
    always sees ``master`` and every worker ends up sharing one database.
    Resolving the worker id here — at the time the RegStack singleton is
    actually built (inside a test fixture) — picks up the real worker id.
    Production is unaffected because ``PYTEST_XDIST_WORKER`` is unset there.
    """
    db = settings.mongodb_database
    worker = os.getenv("PYTEST_XDIST_WORKER")
    if worker and db.startswith("putplace_test_"):
        return f"putplace_test_{worker}"
    return db


def _build_config() -> RegStackConfig:
    """Build the RegStackConfig from putplace's settings.

    All collection names are prefixed ``regstack_`` so that Phase 1 keeps
    regstack and putplace data isolated until the Phase 2 migration.
    """
    jwt_secret = os.getenv("REGSTACK_JWT_SECRET", "")
    if not jwt_secret:
        jwt_secret = secrets.token_urlsafe(64)
        logger.warning(
            "REGSTACK_JWT_SECRET not set; generated a session-local key. "
            "Set REGSTACK_JWT_SECRET in production."
        )

    google_client_secret: SecretStr | None = None
    if settings.google_client_secret:
        google_client_secret = SecretStr(settings.google_client_secret)

    email_cfg = EmailConfig(
        backend="ses",
        from_address=settings.sender_email,
        from_name="PutPlace",
        ses_region=settings.email_aws_region,
    )

    oauth_cfg = OAuthConfig(
        google_client_id=settings.google_client_id,
        google_client_secret=google_client_secret,
    )

    enable_oauth = bool(settings.google_client_id and settings.google_client_secret)

    return RegStackConfig(
        app_name="PutPlace",
        base_url=AnyHttpUrl(settings.base_url),
        database_url=SecretStr(settings.mongodb_url),
        mongodb_database=_resolve_mongodb_database(),
        user_collection=f"{_PHASE1_COLLECTION_PREFIX}users",
        pending_collection=f"{_PHASE1_COLLECTION_PREFIX}pending_registrations",
        blacklist_collection=f"{_PHASE1_COLLECTION_PREFIX}token_blacklist",
        login_attempt_collection=f"{_PHASE1_COLLECTION_PREFIX}login_attempts",
        mfa_code_collection=f"{_PHASE1_COLLECTION_PREFIX}mfa_codes",
        oauth_identity_collection=f"{_PHASE1_COLLECTION_PREFIX}oauth_identities",
        oauth_state_collection=f"{_PHASE1_COLLECTION_PREFIX}oauth_states",
        jwt_secret=SecretStr(jwt_secret),
        api_prefix="/api/v2/auth",
        ui_prefix="/account",
        allow_registration=settings.registration_enabled,
        enable_ui_router=True,
        enable_password_reset=True,
        enable_oauth=enable_oauth,
        email=email_cfg,
        oauth=oauth_cfg,
    )


_regstack: RegStack | None = None
_atexit_registered = False


def _backend_is_closed(rs: RegStack) -> bool:
    """Heuristic: regstack's mongo backend exposes the AsyncMongoClient via
    backend.client. PyMongo marks topology as closed after aclose() is called.
    Other backends don't have this attribute; treat them as never-closed.
    """
    client = getattr(rs.backend, "client", None)
    if client is None:
        return False
    try:
        topology = client._topology  # type: ignore[attr-defined]
    except AttributeError:
        return False
    return getattr(topology, "_closed", False)


def _atexit_close_regstack() -> None:
    # Production lifespan calls aclose(); under pytest the ASGITransport-based
    # client does not run lifespan events. Close on interpreter exit so the
    # Mongo client's background thread does not leak.
    global _regstack
    if _regstack is None:
        return
    try:
        asyncio.run(_regstack.aclose())
    except RuntimeError:
        pass
    _regstack = None


async def reset_regstack() -> None:
    """Close the singleton so the next ``get_regstack()`` rebuilds.

    Called from the FastAPI lifespan teardown so any subsequent caller (notably
    tests that re-invoke the lifespan) gets a fresh, open client. Production
    only calls this once at shutdown — after which the process exits — so the
    rebuild path is exercised by tests.
    """
    global _regstack
    if _regstack is None:
        return
    try:
        await _regstack.aclose()
    except Exception:
        pass
    _regstack = None
    # Rebuild eagerly and reinstall the schema so any subsequent test that
    # touches regstack finds healthy indexes (the close()d topology can't be
    # reopened, and a fresh client without install_schema() has no unique-email
    # index — that's how the dropped-collection flake gets in).
    rs = get_regstack()
    try:
        await rs.install_schema()
    except Exception:
        pass


def get_regstack() -> RegStack:
    """Return the singleton RegStack instance, rebuilding if it was closed."""
    global _regstack, _atexit_registered
    if _regstack is not None and _backend_is_closed(_regstack):
        _regstack = None
    if _regstack is None:
        _regstack = RegStack(config=_build_config())
        if _BRANDED_TEMPLATES_DIR.exists():
            _regstack.add_template_dir(_BRANDED_TEMPLATES_DIR)
        if not _atexit_registered:
            atexit.register(_atexit_close_regstack)
            _atexit_registered = True
    return _regstack
