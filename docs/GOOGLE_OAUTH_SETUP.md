# Google OAuth Setup for PutPlace

This guide will walk you through setting up Google Sign-In for your PutPlace server and Electron client.

## Prerequisites

- A Google account
- PutPlace server running (v0.5.1 or later)
- Access to [Google Cloud Console](https://console.cloud.google.com/)

## Step 1: Create Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Click **Select a project** dropdown at the top
3. Click **New Project**
4. Enter project name (e.g., "PutPlace")
5. Click **Create**
6. Wait for project creation, then select your new project

## Step 2: Enable Google Sign-In API

1. In the left sidebar, go to **APIs & Services** > **Library**
2. Search for "Google Sign-In API" or "Google Identity"
3. Click **Google+ API** (contains Sign-In functionality)
4. Click **Enable**
5. Wait for the API to be enabled

## Step 3: Create OAuth 2.0 Credentials

### Configure OAuth Consent Screen

1. Go to **APIs & Services** > **OAuth consent screen**
2. Select **External** (unless you have Google Workspace)
3. Click **Create**
4. Fill in required fields:
   - **App name**: `PutPlace`
   - **User support email**: Your email
   - **Developer contact**: Your email
5. Click **Save and Continue**
6. **Scopes**: Click **Save and Continue** (default scopes are fine)
7. **Test users**: Add your email address
8. Click **Save and Continue**
9. Review and click **Back to Dashboard**

### Create OAuth Client ID

1. Go to **APIs & Services** > **Credentials**
2. Click **+ Create Credentials** > **OAuth client ID**
3. Select **Application type**: **Web application**
4. Enter name: `PutPlace Web Client`
5. Under **Authorized JavaScript origins**, click **+ Add URI**:
   - For local development: `http://localhost:8000`
   - For production: `https://your-domain.com`
6. Under **Authorized redirect URIs**:
   - Leave empty (not needed for ID token flow)
7. Click **Create**
8. **Important**: Copy your **Client ID**
   - Format: `123456789-abcdefghijklmnop.apps.googleusercontent.com`
   - You'll need this in the next step
9. Click **OK** (you don't need the Client Secret)

## Step 4: Configure PutPlace Server

You have two options to configure the server:

### Option A: Using ppserver.toml (Recommended)

1. Open `ppserver.toml` in your PutPlace directory
2. Find the `[oauth]` section
3. Paste your Client ID:

```toml
[oauth]
google_client_id = "123456789-abcdefghijklmnop.apps.googleusercontent.com"
```

4. Save the file
5. Restart the server:

```bash
invoke quickstart
```

### Option B: Using Environment Variable

Set the environment variable before starting the server:

```bash
export GOOGLE_CLIENT_ID="123456789-abcdefghijklmnop.apps.googleusercontent.com"
invoke quickstart
```

Or add to your `.env` file:

```env
GOOGLE_CLIENT_ID=123456789-abcdefghijklmnop.apps.googleusercontent.com
```

**Note**: Environment variables take precedence over ppserver.toml (as of v0.5.1).

## Step 5: Verify Configuration

1. Check that the server is running:

```bash
curl http://localhost:8000/api/oauth/config
```

Expected response:
```json
{
  "google_client_id": "123456789-abcdefghijklmnop.apps.googleusercontent.com",
  "google_enabled": true
}
```

2. If you see `"google_client_id": ""` or `"google_enabled": false`, the configuration didn't load correctly. Check:
   - ppserver.toml has correct format
   - Environment variable is set (if using that method)
   - Server was restarted after configuration

## Step 6: Test Google Sign-In

### Using Electron Client

1. Launch the Electron client:

```bash
invoke gui-electron
```

2. You should see:
   - Login form with username/password fields
   - **OR** separator with horizontal lines
   - Blue **Sign in with Google** button

3. Click **Sign in with Google**:
   - Google popup appears
   - Select your Google account
   - Authorize the app (first time only)
   - You should be logged in automatically

### Using Web Browser

1. Open your browser to `http://localhost:8000/docs`
2. Find the `POST /api/auth/google` endpoint
3. Click **Try it out**
4. You'll need a Google ID token (get from a test client)

## Troubleshooting

### Button Not Appearing

**Check browser/Electron DevTools console:**

```bash
# Launch Electron with DevTools
invoke gui-electron --dev
```

Look for messages:
- ✅ `"Google Sign-In initialized successfully"` - Good!
- ⚠️ `"Google OAuth not configured on server"` - Check ppserver.toml
- ❌ `"Could not initialize Google Sign-In: ..."` - Configuration error

**Verify server endpoint:**

```bash
curl http://localhost:8000/api/oauth/config
```

Should return your Client ID, not empty string.

### "Invalid ID Token" Error

**Causes:**
1. Client ID mismatch (frontend vs backend)
2. Authorized origins not configured in Google Console
3. Token expired or malformed

**Solutions:**
1. Verify Client ID in ppserver.toml matches Google Console
2. Check **Authorized JavaScript origins** includes `http://localhost:8000`
3. Try signing in again (tokens expire after 1 hour)

### "Popup Blocked" Error

**For Electron:**
- Should not happen (Electron allows popups by default)
- Check DevTools console for Google library loading errors

**For Web Browser:**
- Check browser popup blocker settings
- Allow popups for localhost:8000

### "OAuth Not Configured" Server Error

**Check ppserver.toml:**

```bash
cat ppserver.toml | grep -A 2 "\[oauth\]"
```

Should show:
```toml
[oauth]
google_client_id = "YOUR_CLIENT_ID"
```

Not empty string `""`.

**Check environment variables:**

```bash
echo $GOOGLE_CLIENT_ID
```

Should print your Client ID, not empty.

**Restart server:**

```bash
invoke quickstart
```

## Security Notes

- **ID Token Flow**: This implementation uses Google's ID token flow, which is secure for public clients (Electron apps)
- **No Client Secret**: You don't need a client secret for ID token verification
- **Server-Side Verification**: The server verifies the token with Google's servers before issuing a JWT
- **Token Storage**: JWT tokens are stored in Electron's localStorage (standard practice)
- **HTTPS in Production**: Always use HTTPS in production environments

## Testing Guide

See [GOOGLE_SIGNIN_TESTING.md](ppgui-electron/GOOGLE_SIGNIN_TESTING.md) for comprehensive testing instructions.

## API Endpoints

### Get OAuth Configuration
```http
GET /api/oauth/config
```

Response:
```json
{
  "google_client_id": "string",
  "google_enabled": true
}
```

### Google Sign-In Authentication
```http
POST /api/auth/google
Content-Type: application/json

{
  "id_token": "string"
}
```

Response:
```json
{
  "access_token": "string",
  "token_type": "bearer"
}
```

## Additional Resources

- [Google Sign-In for Web](https://developers.google.com/identity/gsi/web)
- [Google OAuth 2.0 Documentation](https://developers.google.com/identity/protocols/oauth2)
- [PutPlace Authentication Docs](https://putplace.readthedocs.io/en/latest/authentication.html)

## Need Help?

If you encounter issues:
1. Check the troubleshooting section above
2. Review server logs for error messages
3. Open DevTools console for frontend errors
4. Verify Google Cloud Console configuration
5. Ensure you're using PutPlace v0.5.1 or later
