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

import logging
import os
import secrets

from pydantic import AnyHttpUrl, SecretStr
from regstack import RegStack, RegStackConfig
from regstack.config.schema import EmailConfig, OAuthConfig

from .config import settings

logger = logging.getLogger(__name__)


_PHASE1_COLLECTION_PREFIX = "regstack_"


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
        mongodb_database=settings.mongodb_database,
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


def get_regstack() -> RegStack:
    """Return the singleton RegStack instance, building it on first use."""
    global _regstack
    if _regstack is None:
        _regstack = RegStack(config=_build_config())
    return _regstack
