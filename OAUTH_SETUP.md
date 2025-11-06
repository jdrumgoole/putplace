# Google OAuth Setup Guide

This guide explains how to set up Google Sign-In for PutPlace.

## Overview

PutPlace supports two authentication methods:
1. **Username/Password** - Traditional local authentication
2. **Google Sign-In** - OAuth 2.0 authentication using Google accounts

With Google Sign-In enabled, users can:
- Sign in with their existing Google account
- Skip the registration process
- Use a more secure authentication method (no password storage needed)

## Prerequisites

- A Google Account
- Access to [Google Cloud Console](https://console.cloud.google.com/)
- PutPlace server running (backend)

## Step 1: Create Google OAuth Credentials

### 1.1 Create a Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Click "Select a project" → "New Project"
3. Enter project name: `PutPlace` (or your preferred name)
4. Click "Create"
5. Wait for project creation to complete

### 1.2 Enable Google Sign-In API

1. In Google Cloud Console, ensure your new project is selected
2. Go to "APIs & Services" → "Library"
3. Search for "Google+ API" or "Google Identity"
4. Click "Enable"

### 1.3 Configure OAuth Consent Screen

1. Go to "APIs & Services" → "OAuth consent screen"
2. Select "External" user type (unless you have a Google Workspace account)
3. Click "Create"
4. Fill in required fields:
   - **App name**: PutPlace Client
   - **User support email**: Your email
   - **Developer contact information**: Your email
5. Click "Save and Continue"
6. Skip "Scopes" section (click "Save and Continue")
7. Add test users if needed (optional)
8. Click "Save and Continue"

### 1.4 Create OAuth 2.0 Credentials

1. Go to "APIs & Services" → "Credentials"
2. Click "Create Credentials" → "OAuth 2.0 Client ID"
3. Select "Web application" as application type
4. Enter name: `PutPlace Web Client`
5. Add **Authorized JavaScript origins**:
   ```
   http://localhost:8000
   http://127.0.0.1:8000
   ```
   If deploying to production, add your production URL:
   ```
   https://your-domain.com
   ```
6. Leave "Authorized redirect URIs" empty (not needed for ID token flow)
7. Click "Create"
8. **Save your Client ID** - it will look like:
   ```
   123456789-abcdefghijk.apps.googleusercontent.com
   ```

## Step 2: Configure PutPlace Server

### 2.1 Add OAuth Configuration to ppserver.toml

Edit your `ppserver.toml` file and add/update the `[oauth]` section:

```toml
[oauth]
google_client_id = "YOUR_CLIENT_ID.apps.googleusercontent.com"
```

Replace `YOUR_CLIENT_ID` with the actual Client ID from Google Cloud Console.

**Example ppserver.toml:**
```toml
# PutPlace Server Configuration

[database]
mongodb_url = "mongodb://localhost:27017"
mongodb_database = "putplace"
mongodb_collection = "file_metadata"

[api]
title = "PutPlace API"
description = "File metadata storage API"

[storage]
backend = "local"
path = "./storage/files"

[oauth]
google_client_id = "123456789-abcdefghijk.apps.googleusercontent.com"
```

### 2.2 Alternative: Environment Variable

You can also set the Client ID via environment variable:

```bash
export GOOGLE_CLIENT_ID="YOUR_CLIENT_ID.apps.googleusercontent.com"
```

### 2.3 Restart PutPlace Server

After configuration, restart the server:

```bash
invoke quickstart
# Or manually:
ppserver restart
```

## Step 3: Test Google Sign-In

### 3.1 Launch Electron GUI

```bash
invoke gui-electron
```

### 3.2 Sign In with Google

1. On the login page, you should see:
   - Username/Password fields
   - "OR" separator
   - "Sign in with Google" button

2. Click "Sign in with Google"
3. Google popup will appear
4. Select your Google account
5. Authorize the app (first time only)
6. You'll be automatically signed in to PutPlace

### 3.3 Verify Login

- Check that auth status shows your username
- You should be redirected to the main app screen
- Try uploading files to verify the JWT token works

## Troubleshooting

### Google Button Not Appearing

**Problem**: Google Sign-In button doesn't show up

**Possible causes**:
1. **OAuth not configured**: Check `ppserver.toml` has `google_client_id`
2. **Server not restarted**: Restart server after config changes
3. **Network error**: Check browser console for errors

**Solution**:
```bash
# Check server configuration endpoint
curl http://localhost:8000/api/oauth/config

# Should return:
# {"google_client_id":"your-client-id","google_enabled":true}
```

### "Google OAuth not configured" Error

**Problem**: Server returns error about OAuth not configured

**Solution**:
1. Verify `ppserver.toml` has `[oauth]` section with `google_client_id`
2. Verify Client ID format (should end with `.apps.googleusercontent.com`)
3. Restart server: `ppserver restart`

### "Invalid Google ID token" Error

**Problem**: Login fails with invalid token error

**Possible causes**:
1. **Wrong Client ID**: Frontend and backend Client IDs don't match
2. **Origin mismatch**: JavaScript origin not authorized in Google Console
3. **Expired credentials**: Token expired before verification

**Solution**:
1. Verify Client ID in Google Cloud Console matches `ppserver.toml`
2. Add `http://localhost:8000` to Authorized JavaScript origins
3. Clear browser cache and try again

### "Email not verified" Error

**Problem**: Google Sign-In fails with "Email not verified by Google"

**Solution**:
- Use a Google account with verified email
- Verify your email in Google Account settings

## Security Considerations

### What Gets Stored

When a user signs in with Google:
- **User email** (from Google)
- **Full name** (from Google)
- **Profile picture URL** (from Google)
- **OAuth provider** (`"google"`)
- **OAuth ID** (Google user ID - unique identifier)

**NOT stored**:
- Google password
- Google access tokens
- Any other Google account data

### Token Flow

1. User clicks "Sign in with Google"
2. Google popup appears (handled by Google)
3. User authorizes app
4. Google returns **ID token** to frontend
5. Frontend sends ID token to PutPlace backend
6. Backend verifies token with Google servers
7. Backend creates/updates user in database
8. Backend returns PutPlace JWT token
9. Client uses JWT for subsequent API calls

### Client Secret Not Needed

The ID token flow doesn't require a client secret because:
- Verification happens server-side using Google's public keys
- ID tokens are cryptographically signed by Google
- Backend validates signature and claims directly with Google

## Production Deployment

### Update Authorized Origins

When deploying to production:

1. Go to Google Cloud Console → Credentials
2. Edit your OAuth 2.0 Client ID
3. Add production URLs to "Authorized JavaScript origins":
   ```
   https://your-production-domain.com
   https://app.your-domain.com
   ```
4. Update `ppserver.toml` or environment variable on production server
5. No code changes needed!

### HTTPS Required

Google Sign-In requires HTTPS in production. Exceptions:
- `localhost` (development)
- `127.0.0.1` (development)

## Additional Resources

- [Google Sign-In Documentation](https://developers.google.com/identity/gsi/web)
- [OAuth 2.0 Overview](https://developers.google.com/identity/protocols/oauth2)
- [PutPlace Authentication Guide](https://putplace.readthedocs.io/en/latest/authentication.html)

## Support

If you encounter issues:
1. Check server logs: `ppserver logs --follow`
2. Check browser console for JavaScript errors
3. Verify MongoDB is running: `invoke mongo-status`
4. Test backend endpoint: `curl http://localhost:8000/api/oauth/config`

## Example: Testing with cURL

Test the Google OAuth flow manually:

```bash
# 1. Get OAuth config
curl http://localhost:8000/api/oauth/config

# 2. (After getting ID token from Google)
curl -X POST http://localhost:8000/api/auth/google \
  -H "Content-Type: application/json" \
  -d '{"id_token":"YOUR_GOOGLE_ID_TOKEN_HERE"}'

# Should return:
# {"access_token":"eyJ...","token_type":"bearer"}
```
