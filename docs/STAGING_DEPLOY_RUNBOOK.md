# Staging deploy + regstack migration runbook

Procedure for deploying pp_server 0.11.0 / pp_assist 0.3.0 to a staging
environment, migrating any existing user data, exercising it for a week,
then promoting to production. This is decision E from the migration plan
("stagger by environment first") — do NOT skip the staging soak.

## What's changing

- All user-account endpoints move from putplace to regstack, served at
  `/api/v2/auth/*` (JSON) and `/account/*` (themed HTML).
- The old `/api/login`, `/api/register`, `/api/confirm-email`,
  `/api/auth/google`, `/api/oauth/config`, `/api/check-confirmation-status`
  endpoints **stop existing**. Anything pointing at them gets a 404.
- Every JWT issued by pp_server ≤ 0.10 stops validating — different
  signing secret + incompatible token shape. Users log in once.
- pp_assist 0.2.x is incompatible. Old daemons calling `/api/login` get
  a 404 from pp_server 0.11.

## Prerequisites

- pp_server 0.11.0 + pp_assist 0.3.0 wheels built and available
  (`invoke build` produces them in `dist/`).
- A staging environment with its own MongoDB instance — DO NOT run this
  procedure against the production database.
- A point-in-time dump of production MongoDB to copy into staging.
- Operator access to staging env vars (App Runner / docker-compose /
  whatever the staging stack uses).

## Step 1 — Configure regstack environment

Set these in the staging environment:

```bash
# REQUIRED: 64-byte signing secret for JWTs.
export REGSTACK_JWT_SECRET=$(python -c 'import secrets; print(secrets.token_urlsafe(64))')

# Email — same SES region you used before (or smtp/console for dev).
export REGSTACK_EMAIL__BACKEND=ses
export REGSTACK_EMAIL__FROM_ADDRESS=noreply@putplace.example.com
export REGSTACK_EMAIL__SES_REGION=eu-west-1

# Optional: Google OAuth (uses the same Google Cloud client as before).
export REGSTACK_OAUTH__GOOGLE_CLIENT_ID=<existing-google-client-id>
export REGSTACK_OAUTH__GOOGLE_CLIENT_SECRET=<existing-google-client-secret>

# Optional: disable self-service registration.
# export REGSTACK_ALLOW_REGISTRATION=false

# Admin user (only used if no regstack user exists yet).
export PUTPLACE_ADMIN_EMAIL=admin@putplace.example.com
export PUTPLACE_ADMIN_PASSWORD=<strong-password-here>
```

Stash `REGSTACK_JWT_SECRET` in your secret manager. Rotating it logs
every user out.

## Step 2 — Restore prod data into staging

Standard procedure — load the prod dump into staging's MongoDB. After
the restore, staging has putplace's legacy `users` and `pending_users`
collections plus the rest. The regstack collections do not exist yet.

## Step 3 — Dry-run the user migration

```bash
invoke migrate-to-regstack --dry-run --verbose --mongodb-database putplace_staging
```

Inspect the log lines. For every active user you should see one
`would migrate <_id> (<email>)` line; for OAuth users an extra
`+ oauth_identity` suffix. If pending users exist, the script reports
the count but skips them (they expire on TTL).

If the dry-run looks wrong, **stop here** and debug. Do not proceed.

## Step 4 — Real migration

```bash
invoke migrate-to-regstack --verbose --mongodb-database putplace_staging
```

This writes into:

| Collection | Source | Notes |
|---|---|---|
| `regstack_users` | `users` (putplace) | `_id` preserved; `hashed_password=""` converted to `null`; `is_admin` mapped to `is_superuser`. |
| `regstack_oauth_identities` | `users.auth_provider+oauth_id` | One row per OAuth user. |
| `regstack_pending_registrations` | (none) | Empty — putplace's `pending_users` are skipped (raw token vs hashed token incompatibility). |

The script is idempotent. Re-running is a no-op (users already in
`regstack_users` are skipped).

Verify the counts match:

```bash
# putplace users
mongosh "mongodb://staging/putplace_staging" --eval 'db.users.countDocuments({})'
# regstack users
mongosh "mongodb://staging/putplace_staging" --eval 'db.regstack_users.countDocuments({})'
```

They should be equal (or regstack count = putplace count − any deleted
users that the migration skipped). Cross-check a couple of API keys:

```bash
mongosh "mongodb://staging/putplace_staging" --eval '
  const k = db.api_keys.findOne({});
  const u = db.regstack_users.findOne({_id: ObjectId(k.user_id)});
  print("api_key.user_id =", k.user_id);
  print("regstack_users._id =", u && u._id);
  print("regstack_users.email =", u && u.email);
'
```

Both lookups should succeed.

## Step 5 — Deploy pp_server 0.11.0

Replace the running pp_server 0.10.x with the 0.11.0 wheel and restart.
On boot you should see in the logs:

```
INFO  putplace_server.main:lifespan ... regstack schema installed
INFO  putplace_server.main:ensure_admin_exists Users already exist, skipping admin bootstrap
```

Confirm the auth surface is alive:

```bash
curl -i https://staging.putplace.example.com/account/login
# 200 + HTML

curl -i https://staging.putplace.example.com/api/v2/auth/me
# 401 — expected without auth

curl -i -X POST https://staging.putplace.example.com/api/v2/auth/login \
  -H 'content-type: application/json' \
  -d '{"email":"<a-migrated-user>","password":"<known-pw>"}'
# 200 + {"access_token": ..., "expires_in": 7200}
```

The login proves the Argon2 hash portability: putplace's
`argon2-cffi` hashes verify under regstack's `pwdlib`.

## Step 6 — Deploy pp_assist 0.3.0

Coordinate the pp_assist rollout with pp_server's. Old pp_assist 0.2.x
daemons hitting `/api/login` get a 404 once pp_server 0.11 is up, so the
two releases ship together.

Confirm a fresh pp_assist login round-trips through pp_server 0.11's
new endpoint. If `pp_client` is in use, exercise its happy path too —
its public contract is preserved by pp_assist's `/login` adapter.

## Step 7 — Observability for the soak week

For seven days, monitor:

| Signal | What to watch for |
|---|---|
| 401s on `/api_keys`, `/put_file`, `/get_file/*`, `/api/my_files` | spikes mean JWTs aren't validating — investigate before going further |
| 404s on `/api/login`, `/api/register`, `/api/confirm-email` | indicates clients still pointing at the dead endpoints |
| Email-send failures | `regstack.email.console`/SMTP/SES errors in pp_server logs |
| `pending_registrations` row count | should drift upward as new users register and downward as they verify (TTL 24h) |
| `login_attempts` row count | regstack records failures; spikes hint at brute-force or breakage |
| Admin dashboard at `/admin/dashboard` | renders, user/file counts plausible |

If anything fires for more than an hour without an explanation, pause
and investigate.

## Rollback

If you have to roll back within the first week:

1. Re-deploy pp_server 0.10.x and pp_assist 0.2.x (the corresponding
   release tags).
2. The legacy `users` and `pending_users` collections are still in the
   database (we only added `regstack_*` collections, never renamed the
   originals). Pp_server 0.10 reads them directly — nothing else to do.
3. New users created against regstack while pp_server 0.11 was live
   exist only in `regstack_users`. They lose access on rollback. Their
   accounts can be reinstated by re-running the migration after a
   future cutover.
4. The `regstack_*` collections are dead weight after rollback but
   harmless — leave them in place so a future re-cutover is a no-op.

## Promotion to production

After the staging soak week passes cleanly:

1. Merge `regstack-migration` into `main`, tag pp_server 0.11.0 and
   pp_assist 0.3.0.
2. Repeat steps 1–6 against production.
3. Announce the breaking change to users (one forced re-login).
4. Keep the staging migration evidence around for at least one release
   cycle in case prod surfaces something staging missed.
