# PutPlace → regstack migration

Migrate PutPlace's user-account stack (register, login, email verification,
password reset, Google OAuth, admin bootstrap, account HTML pages) onto the
external `regstack` package, while keeping PutPlace-specific concerns
(API keys, file-metadata ownership, admin dashboard) in PutPlace.

Working branch: `regstack-migration` (worktree at `../putplace-regstack-migration`).

## Scope

**Replaced by regstack** (delete after cutover):
- `user_auth.py` — Argon2 + JWT
- `routers/users.py` — register / login / confirm-email / OAuth Google
- `email_tokens.py` + (most of) `email_service.py`
- `templates.py` login / register / await-confirmation templates
- `routers/pages.py` `/login`, `/register`, `/awaiting-confirmation` routes
- `main.py::ensure_admin_exists()`
- `database.py` user + pending_user collection setup
- Auth tests: `test_auth.py`, `test_admin_creation.py`, `test_email_confirmation.py`, `test_registration_control.py`

**Stays in PutPlace** (not in regstack):
- `auth.py::APIKeyAuth` + `routers/api_keys.py` + `api_keys` collection
- `routers/admin.py` admin dashboard (shows file counts + user stats)
- `is_admin` flag (via regstack user-model extension, TBD)
- File-metadata `user_id` FKs
- `pp_assist::uploader.py` JWT consumption — repoint, don't replace

## Open questions (resolve in Phase 0)

- [ ] Does regstack's user model expose `is_admin` or admin role? If not, how do we extend the schema (regstack embedding-guide extension hook, or a parallel PutPlace collection keyed by user `_id`)?
- [ ] Does regstack own the SES/email sender, or do we keep `email_service.py` for non-auth mail? (Are there any non-auth emails today?)
- [ ] Keep `JWT_SECRET_KEY` as `REGSTACK_JWT_SECRET` (preserves live tokens) or rotate (everyone re-logs in)?
- [ ] Reuse current Google OAuth client id, or new one?
- [ ] Are any external scripts beyond `pp_assist` hitting `/api/login` today?

## Phases

### Phase 0 — Spike (1 day)

- [ ] Read `regstack` Mongo backend; confirm it works against current PutPlace Mongo deployment without conflict on collection names.
- [ ] Read `regstack` user model + embedding/extension hooks; pick the strategy for `is_admin` and any other PutPlace-only fields.
- [ ] Stand up regstack alongside PutPlace on a throwaway DB locally; register a user, log in, verify email, reset password end-to-end.
- [ ] Answer every open question above.
- [ ] Write findings into this file under a "Phase 0 results" section.

### Phase 1 — Add regstack, no replacement yet (1–2 days)

- [ ] Add `regstack` to `packages/putplace-server` deps.
- [ ] Wire `RegStack(config=...)` + `install_schema()` in `main.py` lifespan.
- [ ] Mount `regstack.router` at `/api/v2/auth/*` and `ui_router` at `/account/*` (new prefixes, do not replace existing routes).
- [ ] Map `PUTPLACE_ADMIN_*` env vars to `REGSTACK_*` equivalents in config.
- [ ] Both stacks run side-by-side; full test suite still green.

### Phase 2 — Data migration (1 day)

- [ ] Write `pp_migrate_users` invoke task / script: copy `users` → regstack user collection preserving `_id`; copy/expire `pending_users`.
- [ ] Argon2 hashes are portable — verify by logging in a migrated user via regstack.
- [ ] Dry-run mode; run on a copy first.
- [ ] Confirm `api_keys.user_id` FKs still resolve (no-op if `_id` preserved).

### Phase 3 — Cut over endpoints (1 day)

- [ ] Repoint `pp_assist::uploader.py` from `/api/login` to regstack's login endpoint; adjust payload/response shape.
- [ ] Update `dependencies.py::get_current_user()` to validate JWTs via regstack's verifier instead of `user_auth.decode_token`.
- [ ] Repoint `routers/pages.py` redirects (`/login`, `/register`) at regstack's UI router or delete them.
- [ ] Update Google OAuth links / `/api/oauth/config` consumers — or use regstack's bundled login page directly.

### Phase 4 — Delete (0.5 day)

- [ ] Remove `user_auth.py`, `email_tokens.py`, auth-only parts of `email_service.py`, login/register/await templates, `routers/users.py` auth routes, user/pending_users collection setup in `database.py`.
- [ ] Drop obsolete env vars: `JWT_*`, `GOOGLE_CLIENT_*`, `REGISTRATION_ENABLED`, `PUTPLACE_ADMIN_*`, `SENDER_EMAIL` (if regstack owns sending). Replace with `REGSTACK_*`.
- [ ] Update `ppserver.toml.example` and `CLAUDE.md`.

### Phase 5 — Tests (0.5–1 day)

- [ ] Delete the four auth test files listed above.
- [ ] Keep `test_auth_api_keys.py` and update it to bind keys to regstack users.
- [ ] Add integration tests proving a regstack-issued JWT is accepted by PutPlace's `get_current_user` dependency on file-upload endpoints.
- [ ] Run `invoke test-all` ×5 with no flakes.

## Risks & Issues (full review)

### Hard incompatibilities

1. **JWT claim shape is incompatible.** PutPlace tokens contain only `sub`
   (email) + `exp`. regstack `decode()` requires `["sub", "exp", "iat",
   "jti", "purpose"]` and rejects anything missing them, with `purpose`
   enforced (session vs password-reset vs verify-email use different keys
   derived from the secret). **Carrying forward `JWT_SECRET_KEY` does not
   help — putplace-issued tokens cannot be decoded by regstack.**
   Mitigation: hard JWT rotation at cutover; every live session dies once.
   Communicate downtime to users. Make pp_assist re-login automatically on
   401.

2. **`sub` semantics change: email → user id.** PutPlace puts the email in
   `sub`; `get_current_user` decodes the email, then queries
   `users.find({email: ...})`. regstack puts the user id in `sub`.
   `dependencies.get_current_user` must be rewritten to look up by id.
   Anywhere code assumes `current_user["email"]` is the JWT subject must
   be re-audited.

3. **Pending users are not migratable.** regstack stores `token_hash`
   (SHA256 of the raw token) — putplace stores the **raw** token. Without
   the raw plaintext we cannot regenerate the hash. Mitigation: do not
   migrate `pending_users`; let them expire (24h TTL). Users mid-flight
   re-register. Acceptable because the window is small and pending users
   are by definition transient.

4. **OAuth user records have empty-string passwords.** PutPlace OAuth users
   are created with `hashed_password=""`. regstack expects `None` for
   OAuth-only users. Migration script must convert `"" → None`. Otherwise
   regstack will try to verify a plaintext password against an empty hash
   and crash.

5. **OAuth identity moves from user-doc fields to separate collection.**
   PutPlace stores `auth_provider` + `oauth_id` on the user doc. regstack
   stores OAuth links in `oauth_identities` keyed by (provider, sub).
   Migration script must split each OAuth user into a user doc + an
   `oauth_identities` row.

### Soft incompatibilities / data quality

6. **`AuthResponse.user_id: Optional[int]`** in `putplace_assist/models.py`
   is mistyped — putplace user ids are ObjectId strings, not ints. Field
   is probably never populated. Fix during Phase 3 or it'll silently keep
   not working.

7. **Argon2 hash format is portable.** PutPlace uses `argon2-cffi`
   directly; regstack uses `pwdlib` which wraps `argon2-cffi`. Both emit
   PHC `$argon2id$...` strings — cross-verifiable. regstack's
   `needs_rehash()` may report True on every migrated hash if parameter
   defaults differ; regstack will silently re-hash on next successful
   login. No action required.

8. **`registration_enabled` → `allow_registration`.** Clean rename in
   config + env var. `REGISTRATION_ENABLED=false` becomes
   `REGSTACK_ALLOW_REGISTRATION=false` (or via toml).

9. **`check-confirmation-status` polling endpoint.** PutPlace's
   await-confirmation page polls `/api/check-confirmation-status?email=...`
   to learn when the user clicked the link. regstack does not appear to
   ship an equivalent. Two options: (a) keep this endpoint as a putplace
   shim that queries regstack's `pending_registrations` collection
   directly (low effort, leaks an internal schema); (b) drop the poll
   and let the user navigate manually after clicking the link.
   **Decision pending — flag for user.**

10. **Branded confirmation result page.** PutPlace's `/api/confirm-email`
    returns a custom putplace-gradient HTML page. regstack's
    `ui_router` ships its own confirmation page, themable via one CSS
    file. Accept regstack's themed page (drop ~100 lines of inline HTML)
    or override templates (more work). **Default: accept regstack.**

11. **Branded auth emails.** PutPlace's `email_service.py` sends
    branded confirmation emails. regstack ships its own templates. Same
    decision — accept regstack's themable templates by default.

### Operational risks

12. **API key foreign keys.** `api_keys.user_id` is a string-typed
    ObjectId. Migration script MUST preserve the `_id` of every user
    when copying into regstack's user collection. A botched migration
    silently breaks every existing API key. Mitigation: dry-run on a
    copy of the DB; spot-check by issuing a key, migrating, then using
    that key; only then run on prod.

13. **Live session loss at cutover.** Combined with risk #1: every user
    is logged out and must re-log in once. Note in release notes.

14. **`pp_client` in the field.** `pp_client` calls `pp_assist`'s
    `/login` (not the server). As long as `pp_assist /login` keeps its
    public `AuthResponse` contract, old `pp_client`s continue working.
    The contract is `{success, token, error, user_id}` — preserve it.

15. **Old `pp_assist` versions in the field.** Multiple sites in
    `pp_assist` call the server's `/api/login` directly. To avoid
    forcing pp_assist users to upgrade in lockstep with the server:
    keep a one-release server-side shim at `/api/login` that proxies
    the call to regstack's login endpoint and transforms the response
    back to putplace's `Token{access_token}` shape.

16. **`scripts/create_api_key.py` and `scripts/pp_manage_users.py`.**
    Both bypass the API and write directly to the users / api_keys
    collections. After migration they must read the regstack-managed
    user collection. The api_key script keeps working if the collection
    name and id-format stay the same; `pp_manage_users.py` needs a port
    or a delete.

17. **`pp_configure` wizard creates admin users** — needs porting to
    use regstack's `create-admin` mechanism instead of writing directly.

18. **Deployment configs reference env vars that change.**
    `apprunner.yaml`, `docker-compose.yml`, `deploy/app_runner_deploy.py`,
    `tasks-apprunner.py`, and the deploy docs (`AWS_APPRUNNER_*.md`,
    `DIGITALOCEAN_DEPLOYMENT.md`, `OAUTH_SETUP.md`, `GOOGLE_OAUTH_SETUP.md`)
    all reference `PUTPLACE_ADMIN_*`, `JWT_*`, `GOOGLE_CLIENT_*`. All must
    be updated in Phase 4. Easy to miss; add a grep checklist.

19. **`ppserver.toml` schema.** Add a `[regstack]` section, drop the
    `[oauth]`, `[email]`, `[jwt]` sections (or rename them under
    `[regstack]`). Update `ppserver.toml.example`.

20. **Tests bypass the API and call `db.create_user()` directly.**
    After Phase 2 the user collection is owned by regstack. Tests that
    create users directly must either use regstack's APIs or call into
    regstack's backend directly. Add a `make_user` test helper.

21. **pytest-xdist isolation.** PutPlace tests use per-worker databases
    (`putplace_test_gw0`, etc.). regstack's `mongodb_database` config
    must accept the same per-worker value. Conftest needs to pass the
    per-worker DB name through to RegStackConfig.

22. **Static file mount collision.** regstack mounts a `/static/*` path
    for its UI assets; putplace already has `static/` for favicon and
    images. Use a distinct `static_prefix` like `/regstack-static/` to
    avoid colliding.

23. **Pin regstack version.** regstack is v0.5.0 (alpha). Pin to an
    exact version in `pyproject.toml` (`regstack==0.5.0`), not a range.
    Bump explicitly when ready.

24. **Concurrent worktree coordination.** User runs multiple worktrees
    in parallel. This branch touches `pyproject.toml`, `main.py`,
    `models.py`, `database.py`, `dependencies.py`, `config.py` — all
    high-traffic files. Heads-up before merging; coordinate with any
    parallel session.

25. **Rollback story.** Phase 2 renames `users` → `users_legacy` and
    `regstack_users` → `users`. Rollback within 1 release = rename
    back + revert code + redeploy. After 1 release `users_legacy` can
    be dropped, and rollback gets harder. **Keep `users_legacy` for at
    least one release.**

26. **Schema-install ordering.** Putplace's `database.py` creates
    indexes on collections it owns. regstack's `install_schema()`
    creates indexes on its own. Both run in the lifespan startup hook.
    Order: regstack first (it owns the user collection post-Phase 2),
    putplace second (api_keys, file_metadata). Verify no race on a
    cold-start parallel test.

27. **Documentation drift.** Sphinx docs in `docs/`, README sections
    on auth, and three project-level `CLAUDE.md` files all reference
    the current auth model. Allocate ~half a day for doc rewrite at
    Phase 4. The `documentation` skill auto-fires for these.

### Migration plan updates (consolidating Phase 0 findings + risks)

- **Phase 1** now also sets `oauth_state_collection="regstack_oauth_states"`,
  `oauth_identity_collection="regstack_oauth_identities"`, etc. — every
  regstack collection gets a `regstack_*` prefix to avoid any chance of
  collision until Phase 2.
- **Phase 1** also: pin `regstack==0.5.0` in pyproject.toml.
- **Phase 1** also: configure `static_prefix="/regstack-static"`.
- **Phase 2** migration script does five things, in this order:
  1. Copy each `users` doc → `regstack_users`, preserving `_id`,
     converting `hashed_password=""` → `None`.
  2. For each OAuth user, emit a row in `regstack_oauth_identities`
     keyed by `(provider="google", sub=oauth_id)` → `user_id`.
  3. Drop `pending_users` (expire all).
  4. Rename `users` → `users_legacy` and `regstack_users` → `users`
     (and same for the other collections).
  5. Reconfigure regstack at startup to use the unprefixed names.
- **Phase 3** also: rewrite `dependencies.get_current_user` to decode
  via regstack's JWT verifier (`regstack.auth.jwt`), extract `sub` as
  user id, look up by id.
- **Phase 3** also: keep a shim at server `/api/login` that calls
  regstack internally and returns `Token{access_token=...}` for old
  pp_assist clients. Drop the shim in the release after.
- **Phase 3** also: pp_assist's public `/login` keeps its `AuthResponse`
  contract; internal callers (`uploader.py`, `uploader_v3.py`, `main.py`
  line 237) repoint at regstack's login URL.
- **Phase 3** also: decide on `/api/check-confirmation-status` (drop or
  shim). Drop the await-confirmation polling UX or keep with a shim.
- **Phase 4** also: update `apprunner.yaml`, `docker-compose.yml`,
  `deploy/`, `tasks-apprunner.py`, every `*_DEPLOYMENT.md`,
  `OAUTH_SETUP.md`, `GOOGLE_OAUTH_SETUP.md`, project `CLAUDE.md`,
  README, `docs/`. Replace `pp_manage_users.py` or delete.
- **Phase 5** adds: `make_user` test helper; per-worker regstack DB
  wiring in conftest; an integration test that registers via regstack,
  receives an issued JWT, then uses it against putplace's `get_current_user`
  on a file-upload endpoint.

### Decisions confirmed

- **A. Auth HTML pages → accept regstack defaults.** Drop putplace's bespoke
  login / register / await-confirmation / confirmation-result pages. Theme
  with regstack's CSS override. Side effect: deletes a lot of inline HTML
  in `templates.py` and confirmation HTML in `routers/users.py`.
- **B. Auth emails → keep putplace's bespoke templates.** Subclass
  `regstack.email.base.EmailService`, register via
  `RegStack.set_email_backend()`. PutPlace's `email_service.py` becomes
  that subclass (not deleted, refactored). Templates and SES sender
  stay putplace's.
- **C. `/api/check-confirmation-status` polling endpoint → drop.** Since
  decision A drops the await-confirmation page, the poll is unused.
  Delete the endpoint at Phase 4.
- **D. `/api/login` shim → hard cut.** No server-side shim. Coordinate a
  pp_assist release that ships at the same time as the pp_server release.
  Old pp_assist daemons must upgrade in lockstep.
- **E. Cutover timing → stagger by environment.** Deploy to dev / staging
  first, run for a week against real-shaped data, then promote to prod.
  Add a Phase 6: staging soak.
- **F. Scope → approved at 5–7 days.** Proceed phases 0–6 as written.

### Plan changes from decisions

- **Phase 1 add:** subclass `EmailService` (putplace's SES sender) and
  register it via `RegStack.set_email_backend()` (decision B).
- **Phase 3 — remove the `/api/login` shim step (decision D).** Instead,
  cut pp_assist's three internal call sites (`uploader.py`,
  `uploader_v3.py`, `main.py`) over in lockstep. Plan a coordinated
  pp_assist release at the same time as pp_server.
- **Phase 3 — pp_assist version bump.** Treat this as a breaking change
  for pp_assist; bump minor. `pp_client` is unaffected (it talks to
  pp_assist's stable `/login`).
- **Phase 4 add:** delete `routers/users.py` register / confirm-email /
  oauth-google routes; delete `/api/check-confirmation-status`; delete
  putplace's login / register / await-confirmation routes in
  `routers/pages.py`; delete the relevant template functions.
- **Phase 4 do NOT delete `email_service.py`** — it's now the
  EmailService subclass. Trim it to just the SES + template-render code,
  drop the routes-side helpers.
- **Phase 6 (new): Staging soak (1–2 days).** Deploy the merged branch
  to the dev/staging environment. Migrate a copy of prod user data.
  Exercise register / login / OAuth / password-reset / change-email /
  pp_assist end-to-end. Watch logs for one week. Only then merge to a
  `main`-tracked release tag for prod.

### Revised total: 6–8 days (Phase 0 done + Phases 1–6).

## Review

### Phase 1 results

**Shipped:**
- `regstack[mongo]==0.5.0` pinned in `packages/putplace-server/pyproject.toml`.
- New module `putplace_server/regstack_integration.py` builds the singleton
  RegStack with every collection prefixed `regstack_` so it cannot touch
  putplace's existing `users` / `pending_users`.
- `main.py` lifespan installs the regstack schema on startup and closes the
  backend on shutdown. Routers mounted: JSON at `/api/v2/auth/*` (14 routes),
  SSR at `/account/*` (9 routes), static at `/regstack-static`.
- Both stacks coexist; putplace's bare `/login`, `/register`,
  `/awaiting-confirmation` routes untouched.

**Forced changes from adding regstack:**
- **Python minimum bumped 3.10 → 3.11** (regstack requirement). Dropped the
  3.10 classifier; updated `tool.ruff.target-version` and
  `tool.mypy.python_version`.
- **FastAPI 0.119 → 0.136** via dep resolution. Behaviour change: HTTPBearer
  now returns 401 (correct per RFC) instead of 403 for missing credentials.
  Two tests had wrong expectations and were corrected:
  `test_chunked_uploads.py::test_initiate_upload_unauthorized` and
  `test_api.py::test_admin_dashboard_denied_without_auth`.

**Pre-existing repo issues unblocked but unrelated to migration:**
- Top-level `pyproject.toml` declares a `putplace` package with no
  `src/putplace/` directory. Main repo only "works" because of untracked
  `src_old/putplace/` junk. Added `[tool.hatch.build.targets.wheel]
  bypass-selection = true` so fresh worktrees install cleanly. The
  top-level package now exposes nothing — the umbrella project should
  arguably stop declaring `[project]` entirely, but that is bigger scope.
- `pp_gui_client/node_modules` and the built Electron bundle were missing
  in the fresh worktree. `npm install` + `npm run package` brought them
  back. Worth a `setup` invoke task that does this automatically for
  fresh clones.

**Verification:**
- `uv run python -m invoke test-server --no-coverage` × 5 in a row:
  253 passed, 0 failed, 1 skipped each run. No flakes.

**Open items deferred to later phases:**
- Phase 3 task #11: port branded email templates into a putplace template
  dir and register with `regstack.add_template_dir()` before cutover, or
  users receive default regstack-branded emails.
- `JWT_SECRET_KEY not set` warning still appears (the putplace one, not
  regstack's). Will be retired at Phase 4 when putplace's JWT code is
  deleted.

## Review

### Phase 0 results (research, no code yet)

**Mongo coexistence.** regstack's collection names are all config-overridable
(`user_collection`, `pending_collection`, `blacklist_collection`,
`login_attempt_collection`, `mfa_code_collection`,
`oauth_identity_collection`, `oauth_state_collection`). Defaults:

| regstack default | PutPlace today | Action |
|---|---|---|
| `users` | `users` | **Collides.** For Phase 1, point regstack at `regstack_users` (or similar) so both stacks run on the same DB. Phase 2 migrates and renames. |
| `pending_registrations` | `pending_users` | No collision — drop putplace's collection at Phase 4. |
| `token_blacklist` | — | New, regstack only. |
| `login_attempts` | — | New, regstack only. |
| `mfa_codes` | — | New, opt-in (SMS MFA disabled by default). |
| `oauth_identities` | — | New — replaces putplace's `auth_provider` / `oauth_id` columns on the user doc. |
| `oauth_states` | — | New, regstack only. |
| — | `api_keys` | Stays in PutPlace. |
| — | `file_metadata` | Stays in PutPlace. |

**`is_admin` strategy.** regstack's `BaseUser` ships `is_superuser: bool` and
provides `is_admin` as an alias property (`@property def is_admin: return
self.is_superuser`). The docstring literally says "default field set covers
what both winebox and putplace need today." **No extension required.**
`PUTPLACE_ADMIN_*` env vars map to creating a regstack user with
`is_superuser=True` (regstack ships a `create-admin` CLI and an analogous
config flag).

The doc-mentioned `RegStack.extend_user_model` hook is not actually
implemented (only referenced in the BaseUser docstring) — but `BaseUser`
sets `extra="allow"`, so any PutPlace-only field could ride along untyped.
We don't need this for the migration: `auth_provider` + `oauth_id` are
obsolete (regstack tracks them in `oauth_identities`), and `picture` is a
non-critical UI avatar — fetch from the oauth_identity row on demand, or
drop until later.

**Email sender.** The only caller of `email_service.py` in PutPlace is
`routers/users.py` for confirmation emails. There is no non-auth mail. The
standalone `send_ses_email.py` script is unrelated. regstack ships
console / SMTP / SES backends. **regstack takes over email entirely;
delete `email_service.py` at Phase 4.**

**JWT secret.** Decision deferred to deploy time. Default plan: rotate
(set fresh `REGSTACK_JWT_SECRET`), accept one round of forced re-login.
If we instead carry forward `JWT_SECRET_KEY` into `REGSTACK_JWT_SECRET`,
existing tokens stay valid but the algorithm and claim layout must match
— needs verification against regstack's JWT format. **Cheaper to rotate.**

**Google OAuth client.** Reuse current `GOOGLE_CLIENT_ID`; regstack's
Google flow uses PKCE + ID-token verification (matches putplace's
approach). Existing OAuth users have `oauth_id` on their user doc — those
become rows in regstack's `oauth_identities` collection at Phase 2.

**`/api/login` consumers.** Three places call it directly:
- `pp_assist/src/putplace_assist/uploader.py` (line 424)
- `pp_assist/src/putplace_assist/uploader_v3.py` (line 205)
- `pp_assist/src/putplace_assist/main.py` (line 237) — proxied from pp_assist's own `/login` endpoint

`pp_client` calls `pp_assist`'s `/login`, not the server directly. So the
public-facing daemon contract (`pp_assist /login`) can stay stable while
its three internal call sites get repointed — `pp_client` users don't
need to upgrade in lockstep. **Add a one-release shim at the server's
`/api/login` that proxies to regstack** so any straggler clients still
work during rollout.

**Updates to original plan:**
1. Phase 1: configure regstack with `user_collection="regstack_users"` and other scoped names — do not let it write to PutPlace's `users` collection until Phase 2.
2. Phase 2 step "preserve `_id`" is critical because `api_keys.user_id` points at it. The migration script copies docs verbatim into `regstack_users`, then renames the collections (`users` → `users_legacy`, `regstack_users` → `users`) atomically.
3. Drop the `is_admin` extension question — it's already there.
4. Drop `email_service.py` cleanly at Phase 4 — no non-auth callers.

