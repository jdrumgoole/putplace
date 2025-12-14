# Testing Google Sign-In in Electron GUI

This guide explains how to test the Google Sign-In feature in the PutPlace Electron client.

## Current Status

✅ **Google Sign-In is fully implemented** in the Electron client (v0.5.1)

The implementation includes:
- Automatic detection of Google OAuth configuration from server
- Dynamic button rendering based on server configuration
- Graceful fallback when OAuth is not configured
- Full OAuth flow with ID token verification

## How the Feature Works

1. **On App Launch**:
   - Electron client fetches OAuth config from server (`/api/oauth/config`)
   - If `google_client_id` is configured, the "Sign in with Google" button appears
   - If not configured, the button and "OR" separator are hidden

2. **User Clicks "Sign in with Google"**:
   - Google popup appears for account selection
   - User authorizes the app
   - Google returns ID token to client

3. **Token Verification**:
   - Client sends ID token to `/api/auth/google`
   - Server verifies token with Google
   - Server returns JWT access token
   - Client saves JWT and logs user in

## Testing Steps

### Option 1: Test Without Google OAuth (Default)

```bash
# 1. Start the server (without Google OAuth configured)
invoke quickstart

# 2. Launch Electron GUI
invoke gui-electron

# Expected Result:
# - Login form appears with username/password fields
# - NO "OR" separator visible
# - NO "Sign in with Google" button visible
# - Only traditional login is available
```

### Option 2: Test With Google OAuth Enabled

#### Step 1: Configure Google OAuth

Follow the [OAuth Setup Guide](../OAUTH_SETUP.md) to:
1. Create Google OAuth credentials in Google Cloud Console
2. Get your Client ID (format: `123456789-xxx.apps.googleusercontent.com`)
3. Add `http://localhost:8000` to authorized JavaScript origins

#### Step 2: Configure Server

Edit `ppserver.toml`:

```toml
[oauth]
google_client_id = "YOUR_CLIENT_ID.apps.googleusercontent.com"
```

Or set environment variable:

```bash
export GOOGLE_CLIENT_ID="YOUR_CLIENT_ID.apps.googleusercontent.com"
```

#### Step 3: Start Server and Client

```bash
# 1. Restart server to load new configuration
invoke quickstart

# 2. Verify OAuth endpoint returns client ID
curl http://localhost:8000/api/oauth/config
# Should return: {"google_client_id":"YOUR_CLIENT_ID","google_enabled":true}

# 3. Launch Electron GUI
invoke gui-electron
```

#### Step 4: Test Google Sign-In

**Expected UI:**
- Login form with username/password fields
- "OR" separator with horizontal lines
- Blue "Sign in with Google" button

**Test the flow:**
1. Click "Sign in with Google" button
2. Google popup opens
3. Select your Google account
4. Authorize the app (first time only)
5. You should be logged in automatically
6. Main app screen appears with file browser

## Troubleshooting

### Button Not Appearing

**Symptom**: No "Sign in with Google" button visible

**Check:**
1. Open browser DevTools (Ctrl+Shift+I or Cmd+Option+I)
2. Look in Console for messages:
   - `"Google Sign-In initialized successfully"` ✅ Good
   - `"Google OAuth not configured on server"` ⚠️ Config issue
   - `"Could not initialize Google Sign-In: ..."` ❌ Error

**Solution:**
```bash
# Verify server configuration
curl http://localhost:8000/api/oauth/config

# If returns {"google_client_id":"","google_enabled":false}:
# - Check ppserver.toml has [oauth] section
# - Check google_client_id is set
# - Restart server
```

### "Google OAuth not configured" Error

**Symptom**: Error message when trying to sign in

**Solution:**
1. Ensure `google_client_id` is set in `ppserver.toml`
2. Restart the server: `ppserver restart`
3. Refresh the Electron app

### Google Popup Blocked

**Symptom**: Popup doesn't appear or immediately closes

**Solution:**
- This is normal for Electron - the popup should work automatically
- If issues persist, check that Google library loaded:
  - DevTools Console should show no errors loading `https://accounts.google.com/gsi/client`

### Invalid ID Token Error

**Symptom**: "Invalid Google ID token" after authorization

**Causes:**
1. Client ID mismatch (frontend vs backend)
2. Authorized origins not configured correctly
3. Token expired

**Solution:**
1. Verify Client ID in `ppserver.toml` matches Google Cloud Console
2. Add `http://localhost:8000` to authorized origins in Google Console
3. Try signing in again (token may have expired)

## Implementation Details

### Frontend (Electron)

**Files:**
- `src/renderer/index.html` - Contains Google Sign-In button placeholder
- `src/renderer/renderer.ts` - Contains initialization logic (lines 506-583)
- `src/renderer/styles.css` - Button and separator styling (lines 424-467)

**Key Functions:**
- `initializeGoogleSignIn()` - Fetches config and initializes button
- `handleGoogleCallback()` - Processes Google's OAuth response
- `showGoogleSignIn()` / `hideGoogleSignIn()` - Toggle visibility

### Backend (FastAPI)

**Endpoints:**
- `GET /api/oauth/config` - Returns Google Client ID to frontend
- `POST /api/auth/google` - Verifies ID token and returns JWT

**Files:**
- `src/putplace/main.py` - OAuth endpoints (lines 2144-2268)
- `src/putplace/config.py` - Configuration loading
- `src/putplace/models.py` - GoogleOAuthLogin model

## Development Mode

For development with DevTools:

```bash
invoke gui-electron --dev
```

This opens DevTools automatically so you can:
- Monitor console logs
- Inspect network requests to `/api/oauth/config`
- Debug Google Sign-In initialization
- View any JavaScript errors

## Known Limitations

1. **First-time authorization**: Users must authorize the app once in Google
2. **Requires internet**: Google verification happens online
3. **Single sign-on**: Currently creates new users based on email (no linking)

## Security Notes

- ID token verification is done server-side (secure)
- Client secret is NOT needed (ID token flow)
- JWT token is stored in localStorage (standard for Electron apps)
- Token includes user claims from Google (email, name, picture)

## References

- [Google Sign-In for Web](https://developers.google.com/identity/gsi/web)
- [PutPlace OAuth Setup Guide](../OAUTH_SETUP.md)
- [PutPlace Authentication Docs](https://putplace.readthedocs.io/en/latest/authentication.html)
