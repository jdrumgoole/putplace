# Authentication

PutPlace has two authentication paths:

| For | Mechanism | Lives in |
|---|---|---|
| Web sign-in, JWT sessions, registration, password reset, OAuth | [regstack](https://regstack.readthedocs.io), embedded | `/api/v2/auth/*` (JSON) + `/account/*` (SSR HTML) |
| Programmatic / long-lived service tokens | PutPlace API keys | `/api_keys` |

## User accounts (regstack)

regstack owns the entire user-account surface: register, log in, log out,
verify email, change password, reset password, change email, delete account,
Google Sign-In, optional SMS MFA, and admin endpoints. All of it speaks JSON
at `/api/v2/auth/*` and serves HTML at `/account/*`.

### Minimal flow

1. **Register** — `POST /api/v2/auth/register` with `{email, password}`. A
   verification email goes out (regstack uses putplace's branded templates
   from `regstack_email_templates/`).
2. **Verify** — the link in the email lands on `POST /api/v2/auth/verify`.
3. **Log in** — `POST /api/v2/auth/login` returns `{access_token, expires_in}`.
4. **Authenticated requests** — send `Authorization: Bearer <access_token>`
   to any putplace endpoint that requires auth.

### Configuration (env vars)

| Var | Purpose |
|---|---|
| `REGSTACK_JWT_SECRET` | Required in production — signing secret for JWTs. |
| `REGSTACK_EMAIL__BACKEND` | `ses`, `smtp`, or `console`. |
| `REGSTACK_EMAIL__FROM_ADDRESS` | From-address for auth emails. |
| `REGSTACK_EMAIL__SES_REGION` | AWS region when backend=ses. |
| `REGSTACK_OAUTH__GOOGLE_CLIENT_ID` | Google OAuth client id (turns on the Google Sign-In button). |
| `REGSTACK_OAUTH__GOOGLE_CLIENT_SECRET` | Matching secret. |
| `REGSTACK_ALLOW_REGISTRATION` | `false` to disable self-service registration. |

See the full list in the
[regstack configuration docs](https://regstack.readthedocs.io/en/latest/configuration.html).

### Admin user (bootstrap)

On the first server startup, putplace creates an admin user via regstack's
`bootstrap_admin()`:

- If `PUTPLACE_ADMIN_EMAIL` + `PUTPLACE_ADMIN_PASSWORD` are set, those
  credentials are used.
- Otherwise putplace generates a random password and writes the credentials
  once to `/tmp/putplace_initial_creds.txt`. Read it, save the password,
  then delete the file.

## API keys (putplace)

PutPlace mints long-lived API keys for service-to-service calls. These are
putplace's own machinery — they do **not** flow through regstack.

### Create a key

You must be logged in (i.e. hold a regstack-issued JWT):

```bash
curl -X POST http://localhost:8000/api_keys \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{"name": "my-uploader"}'
```

The response includes the raw key string; it is shown **once**. PutPlace
stores only its SHA-256 hash (`key_hash`).

### Use a key

```bash
curl -X POST http://localhost:8000/put_file \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{...}'
```

Either `Authorization: Bearer <jwt>` or `X-API-Key: <api-key>` is accepted
on any of putplace's `put_file` / `get_file` / `upload_file` /
`/api/my_files` / `/api/clones/...` endpoints.

### Manage keys

| Operation | Endpoint |
|---|---|
| List your keys | `GET /api_keys` |
| Get one | `GET /api_keys/{key_id}` |
| Revoke | `POST /api_keys/{key_id}/revoke` |
| Delete | `DELETE /api_keys/{key_id}` |

All four require a valid JWT (Bearer auth).
