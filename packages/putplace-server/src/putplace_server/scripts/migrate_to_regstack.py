"""Migrate putplace users into regstack's collections (Phase 2).

Reads every document from putplace's `users` collection and writes it into
`regstack_users`, preserving `_id` so that `api_keys.user_id` foreign keys
keep resolving. OAuth users have their provider/subject split out into a
row in `regstack_oauth_identities`. Pending users are left to expire on
their own TTL — putplace stored raw confirmation tokens but regstack stores
sha256 hashes, so we cannot regenerate them.

Idempotent: re-running the script over an already-migrated database is a
no-op (it skips users whose `_id` already exists in `regstack_users`).

Usage:
    pp_migrate_users [--dry-run] [--verbose] \\
        [--mongodb-url URL] [--mongodb-database NAME] \\
        [--source-collection users] \\
        [--target-collection regstack_users] \\
        [--oauth-collection regstack_oauth_identities]

The defaults match putplace's standard config and Phase 1 of the regstack
migration. A --dry-run pass is recommended on a copy of production data
before the real run.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from datetime import UTC, datetime
from typing import Any

from pymongo import AsyncMongoClient

from putplace_server.config import settings

logger = logging.getLogger(__name__)

_BATCH_SIZE = 100


def _ensure_utc(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return datetime.now(UTC)


def _to_regstack_user(doc: dict[str, Any]) -> dict[str, Any]:
    """Translate a putplace user doc into the regstack BaseUser shape."""
    created_at = _ensure_utc(doc.get("created_at"))
    hashed_password = doc.get("hashed_password") or None
    out: dict[str, Any] = {
        "_id": doc["_id"],
        "email": doc["email"],
        "hashed_password": hashed_password,
        "is_active": bool(doc.get("is_active", True)),
        "is_verified": True,
        "is_superuser": bool(doc.get("is_admin", False)),
        "is_mfa_enabled": False,
        "created_at": created_at,
        "updated_at": _ensure_utc(doc.get("updated_at", created_at)),
    }
    if doc.get("full_name") is not None:
        out["full_name"] = doc["full_name"]
    return out


def _to_oauth_identity(doc: dict[str, Any]) -> dict[str, Any] | None:
    """Return an oauth_identity row for `doc` if it has provider+subject set."""
    provider = doc.get("auth_provider")
    subject = doc.get("oauth_id")
    if not provider or not subject or provider == "local":
        return None
    return {
        "user_id": doc["_id"],
        "provider": provider,
        "subject_id": subject,
        "email": doc.get("email"),
        "linked_at": _ensure_utc(doc.get("created_at")),
    }


async def _migrate(
    *,
    mongodb_url: str,
    database: str,
    source: str,
    target: str,
    oauth_target: str,
    dry_run: bool,
) -> int:
    """Run the migration. Returns the process exit code (0 = success)."""
    use_tls = "mongodb+srv://" in mongodb_url or "mongodb.net" in mongodb_url
    client_kwargs: dict[str, Any] = {"serverSelectionTimeoutMS": 5000}
    if use_tls:
        import certifi

        client_kwargs["tlsCAFile"] = certifi.where()
    client = AsyncMongoClient(mongodb_url, **client_kwargs)
    try:
        db = client[database]
        source_coll = db[source]
        target_coll = db[target]
        oauth_coll = db[oauth_target]
        pending_coll = db["pending_users"]

        total = await source_coll.estimated_document_count()
        pending = await pending_coll.estimated_document_count()
        logger.info(
            "Source `%s.%s` has ~%d users; pending_users has ~%d entries "
            "(left alone, will expire on TTL).",
            database,
            source,
            total,
            pending,
        )

        migrated = 0
        skipped = 0
        oauth_emitted = 0
        oauth_skipped = 0
        last_id = None

        while True:
            query: dict[str, Any] = {} if last_id is None else {"_id": {"$gt": last_id}}
            cursor = source_coll.find(query).sort("_id", 1).limit(_BATCH_SIZE)
            batch = [doc async for doc in cursor]
            if not batch:
                break
            for doc in batch:
                last_id = doc["_id"]
                existing = await target_coll.find_one({"_id": doc["_id"]}, {"_id": 1})
                if existing is not None:
                    skipped += 1
                    logger.debug("skip user %s (already in target)", doc["_id"])
                    continue

                regstack_doc = _to_regstack_user(doc)
                identity = _to_oauth_identity(doc)

                if dry_run:
                    migrated += 1
                    if identity is not None:
                        oauth_emitted += 1
                    logger.info(
                        "[dry-run] would migrate %s (%s)%s",
                        doc["_id"],
                        doc.get("email", "?"),
                        " + oauth_identity" if identity else "",
                    )
                    continue

                await target_coll.insert_one(regstack_doc)
                migrated += 1
                if identity is not None:
                    oauth_existing = await oauth_coll.find_one(
                        {"provider": identity["provider"], "subject_id": identity["subject_id"]},
                        {"_id": 1},
                    )
                    if oauth_existing is None:
                        await oauth_coll.insert_one(identity)
                        oauth_emitted += 1
                    else:
                        oauth_skipped += 1
                logger.info(
                    "migrated %s (%s)%s",
                    doc["_id"],
                    doc.get("email", "?"),
                    " + oauth_identity" if identity else "",
                )

        logger.info(
            "Done. migrated=%d skipped=%d oauth_identities_emitted=%d "
            "oauth_identities_skipped=%d dry_run=%s",
            migrated,
            skipped,
            oauth_emitted,
            oauth_skipped,
            dry_run,
        )
        return 0
    finally:
        await client.aclose()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Read but do not write. Reports what would change.",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Per-user log lines.",
    )
    parser.add_argument(
        "--mongodb-url",
        default=os.environ.get("MONGODB_URL", settings.mongodb_url),
        help="Mongo connection string (default: putplace settings).",
    )
    parser.add_argument(
        "--mongodb-database",
        default=os.environ.get("MONGODB_DATABASE", settings.mongodb_database),
        help="Database name (default: putplace settings).",
    )
    parser.add_argument(
        "--source-collection",
        default="users",
        help="Putplace users collection (default: users).",
    )
    parser.add_argument(
        "--target-collection",
        default="regstack_users",
        help="regstack user collection (default: regstack_users).",
    )
    parser.add_argument(
        "--oauth-collection",
        default="regstack_oauth_identities",
        help="regstack oauth identity collection (default: regstack_oauth_identities).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    try:
        return asyncio.run(
            _migrate(
                mongodb_url=args.mongodb_url,
                database=args.mongodb_database,
                source=args.source_collection,
                target=args.target_collection,
                oauth_target=args.oauth_collection,
                dry_run=args.dry_run,
            )
        )
    except KeyboardInterrupt:
        logger.warning("interrupted")
        return 130


if __name__ == "__main__":
    sys.exit(main())
