"""HTML templates for PutPlace web pages.

This module contains all HTML templates extracted from the main application
to improve code organization and maintainability.
"""


def get_base_styles() -> str:
    """Return common CSS styles used across all pages."""
    return """
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .container {
            max-width: 900px;
            margin: 0 auto;
            background: white;
            border-radius: 10px;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
            overflow: hidden;
        }
        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 40px;
            text-align: center;
        }
        .header h1 {
            font-size: 2.5rem;
            margin-bottom: 10px;
        }
        .header p {
            font-size: 1.2rem;
            opacity: 0.9;
        }
        .content {
            padding: 40px;
        }
        .section {
            margin-bottom: 30px;
        }
        .section h2 {
            color: #667eea;
            margin-bottom: 15px;
            font-size: 1.5rem;
            border-bottom: 2px solid #667eea;
            padding-bottom: 5px;
        }
        .card {
            background: #f8f9fa;
            border-left: 4px solid #667eea;
            padding: 15px;
            margin-bottom: 15px;
            border-radius: 4px;
        }
        .card h3 {
            color: #667eea;
            margin-bottom: 8px;
        }
        .card code {
            background: #e9ecef;
            padding: 2px 6px;
            border-radius: 3px;
            font-family: 'Courier New', monospace;
            font-size: 0.9rem;
        }
        .btn-group {
            display: flex;
            gap: 15px;
            flex-wrap: wrap;
            margin-top: 20px;
        }
        .btn {
            display: inline-block;
            padding: 12px 24px;
            background: #667eea;
            color: white;
            text-decoration: none;
            border-radius: 5px;
            font-weight: 500;
            transition: all 0.3s ease;
            border: none;
            cursor: pointer;
        }
        .btn:hover {
            background: #764ba2;
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(102, 126, 234, 0.4);
        }
        .btn-secondary {
            background: #6c757d;
        }
        .btn-secondary:hover {
            background: #5a6268;
        }
        .btn-danger {
            background: #dc3545;
        }
        .btn-danger:hover {
            background: #c82333;
        }
        .btn-success {
            background: #28a745;
        }
        .btn-success:hover {
            background: #218838;
        }
        .footer {
            background: #f8f9fa;
            padding: 20px 40px;
            text-align: center;
            color: #6c757d;
            border-top: 1px solid #dee2e6;
        }
        .auth-buttons {
            display: flex;
            gap: 10px;
            justify-content: center;
            margin-top: 20px;
        }
        .auth-btn {
            display: inline-block;
            padding: 10px 20px;
            background: rgba(255, 255, 255, 0.2);
            color: white;
            text-decoration: none;
            border-radius: 5px;
            font-weight: 500;
            transition: all 0.3s ease;
            border: 2px solid white;
        }
        .auth-btn:hover {
            background: white;
            color: #667eea;
            transform: translateY(-2px);
        }
        .method {
            display: inline-block;
            padding: 4px 8px;
            border-radius: 3px;
            font-weight: 600;
            font-size: 0.85rem;
            margin-right: 10px;
            min-width: 60px;
            text-align: center;
        }
        .method-get { background: #61affe; color: white; }
        .method-post { background: #49cc90; color: white; }
        .method-put { background: #fca130; color: white; }
        .method-delete { background: #f93e3e; color: white; }
        .status-badge {
            display: inline-block;
            padding: 5px 12px;
            background: #28a745;
            color: white;
            border-radius: 20px;
            font-size: 0.9rem;
            font-weight: 500;
        }
        pre {
            background: #2d2d2d;
            color: #f8f8f2;
            padding: 15px;
            border-radius: 5px;
            overflow-x: auto;
            font-size: 0.9rem;
        }
        .endpoint-list {
            list-style: none;
        }
        .endpoint-list li {
            padding: 10px;
            margin-bottom: 8px;
            background: #f8f9fa;
            border-radius: 4px;
            display: flex;
            align-items: center;
        }
        .form-group {
            margin-bottom: 20px;
        }
        .form-group label {
            display: block;
            margin-bottom: 8px;
            font-weight: 500;
            color: #333;
        }
        .form-group input {
            width: 100%;
            padding: 12px;
            border: 2px solid #e9ecef;
            border-radius: 5px;
            font-size: 1rem;
            transition: border-color 0.3s ease;
        }
        .form-group input:focus {
            outline: none;
            border-color: #667eea;
        }
        .error-message {
            background: #f8d7da;
            color: #721c24;
            padding: 15px;
            border-radius: 5px;
            margin-bottom: 20px;
            display: none;
        }
        .success-message {
            background: #d4edda;
            color: #155724;
            padding: 15px;
            border-radius: 5px;
            margin-bottom: 20px;
            display: none;
        }
        .link {
            color: #667eea;
            text-decoration: none;
        }
        .link:hover {
            text-decoration: underline;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
        }
        th, td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #dee2e6;
        }
        th {
            background: #f8f9fa;
            font-weight: 600;
            color: #333;
        }
        tr:hover {
            background: #f8f9fa;
        }
    """


def get_home_page(api_version: str) -> str:
    """Return the home page HTML."""
    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>PutPlace - File Metadata Storage</title>
        <link rel="icon" type="image/svg+xml" href="/static/images/favicon.svg">
        <style>
            {get_base_styles()}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>PutPlace</h1>
                <p>File Metadata Storage Service</p>
                <div style="margin-top: 15px;">
                    <span class="status-badge">Running</span>
                </div>
                <div class="auth-buttons" id="authButtons">
                    <a href="/login" class="auth-btn">Login</a>
                    <a href="/register" class="auth-btn">Register</a>
                </div>
            </div>

            <div class="content">
                <div class="section">
                    <h2>Welcome</h2>
                    <p>PutPlace is a FastAPI-based service for storing and retrieving file metadata with MongoDB backend. Track file locations, SHA256 hashes, and metadata across your infrastructure.</p>
                </div>

                <div class="section">
                    <h2>Quick Start</h2>
                    <div class="btn-group">
                        <a href="https://putplace.org/downloads.html" class="btn">Download Client</a>
                        <a href="/docs" class="btn btn-secondary">API Docs (Swagger)</a>
                        <a href="/redoc" class="btn btn-secondary">Alternative Docs</a>
                    </div>
                </div>

                <div class="section">
                    <h2>API Endpoints</h2>
                    <ul class="endpoint-list">
                        <li>
                            <span class="method method-get">GET</span>
                            <code>/health</code> - Health check with database status
                        </li>
                        <li>
                            <span class="method method-post">POST</span>
                            <code>/put_file</code> - Store file metadata
                        </li>
                        <li>
                            <span class="method method-get">GET</span>
                            <code>/get_file/{{sha256}}</code> - Retrieve file by SHA256 hash
                        </li>
                        <li>
                            <span class="method method-post">POST</span>
                            <code>/upload_file/{{sha256}}</code> - Upload file content
                        </li>
                        <li>
                            <span class="method method-post">POST</span>
                            <code>/api_keys</code> - Create new API key
                        </li>
                        <li>
                            <span class="method method-get">GET</span>
                            <code>/api_keys</code> - List all API keys
                        </li>
                        <li>
                            <span class="method method-delete">DELETE</span>
                            <code>/api_keys/{{key_id}}</code> - Delete API key
                        </li>
                        <li>
                            <span class="method method-put">PUT</span>
                            <code>/api_keys/{{key_id}}/revoke</code> - Revoke API key
                        </li>
                    </ul>
                </div>

                <div class="section">
                    <h2>Example Usage</h2>
                    <div class="card">
                        <h3>Store File Metadata</h3>
                        <pre>curl -X POST http://localhost:8000/put_file \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer your-jwt-token" \\
  -d '{{
    "filepath": "/var/log/app.log",
    "hostname": "server01",
    "ip_address": "192.168.1.100",
    "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
  }}'</pre>
                    </div>

                    <div class="card">
                        <h3>Retrieve File Metadata</h3>
                        <pre>curl -H "Authorization: Bearer your-jwt-token" \\
  http://localhost:8000/get_file/e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855</pre>
                    </div>

                    <div class="card">
                        <h3>Using the Client Tool</h3>
                        <pre># Scan a directory and send metadata to server
ppclient /var/log --token your-jwt-token

# With exclude patterns
ppclient /home/user --exclude .git --exclude "*.log"

# Dry run mode
ppclient /var/log --dry-run</pre>
                    </div>
                </div>

                <div class="section">
                    <h2>Getting Started</h2>
                    <div class="card">
                        <h3>1. Register an Account</h3>
                        <p>Click the Register button above to create your account.</p>
                    </div>

                    <div class="card">
                        <h3>2. Install the Client</h3>
                        <pre>pip install putplace-client
ppclient --help</pre>
                    </div>

                    <div class="card">
                        <h3>3. Start Scanning</h3>
                        <p>Use the <code>ppclient</code> command to scan directories and send metadata to the server.</p>
                    </div>
                </div>
            </div>

            <div class="footer">
                <p>PutPlace v{api_version} | Built with FastAPI & MongoDB</p>
                <p style="margin-top: 5px; font-size: 0.9rem;">
                    <a href="https://putplace.org/downloads.html" class="link">Downloads</a> |
                    <a href="/docs" class="link">API Documentation</a> |
                    <a href="/health" class="link">Health Status</a>
                </p>
            </div>
        </div>
        <script>
            // Check if user is logged in and update buttons
            (function() {{
                const token = localStorage.getItem('access_token');
                const authButtons = document.getElementById('authButtons');

                if (token && authButtons) {{
                    // User is logged in - show My Files, API Keys and Logout buttons
                    authButtons.innerHTML = `
                        <a href="/my_files" class="auth-btn">My Files</a>
                        <a href="/api_keys_page" class="auth-btn">My API Keys</a>
                        <button onclick="logout()" class="auth-btn" style="cursor: pointer;">Logout</button>
                    `;
                }}
            }})();

            function logout() {{
                localStorage.removeItem('access_token');
                window.location.reload();
            }}
        </script>
    </body>
    </html>
    """


def get_login_page() -> str:
    """Return the login page HTML."""
    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Login - PutPlace</title>
        <link rel="icon" type="image/svg+xml" href="/static/images/favicon.svg">
        <style>
            {get_base_styles()}
            .login-container {{
                max-width: 450px;
            }}
            .divider {{
                display: flex;
                align-items: center;
                margin: 20px 0;
            }}
            .divider::before,
            .divider::after {{
                content: "";
                flex: 1;
                border-bottom: 1px solid #dee2e6;
            }}
            .divider span {{
                padding: 0 10px;
                color: #6c757d;
                font-size: 0.9rem;
            }}
            .google-btn {{
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 10px;
                width: 100%;
                padding: 12px;
                background: white;
                border: 2px solid #dee2e6;
                border-radius: 5px;
                font-size: 1rem;
                cursor: pointer;
                transition: all 0.3s ease;
            }}
            .google-btn:hover {{
                background: #f8f9fa;
                border-color: #667eea;
            }}
            .google-btn img {{
                width: 20px;
                height: 20px;
            }}
        </style>
    </head>
    <body>
        <div class="container login-container">
            <div class="header">
                <h1>Login</h1>
                <p>Sign in to your account</p>
            </div>

            <div class="content">
                <div id="errorMessage" class="error-message"></div>
                <div id="successMessage" class="success-message"></div>

                <form id="loginForm">
                    <div class="form-group">
                        <label for="email">Email</label>
                        <input type="email" id="email" name="email" required placeholder="Enter your email">
                    </div>

                    <div class="form-group">
                        <label for="password">Password</label>
                        <input type="password" id="password" name="password" required placeholder="Enter your password">
                    </div>

                    <button type="submit" class="btn" style="width: 100%;">Login</button>
                </form>

                <div class="divider">
                    <span>OR</span>
                </div>

                <div id="googleSignInContainer">
                    <div id="g_id_onload"
                         data-client_id=""
                         data-context="signin"
                         data-ux_mode="popup"
                         data-callback="handleGoogleSignIn"
                         data-auto_prompt="false">
                    </div>
                    <div class="g_id_signin"
                         data-type="standard"
                         data-shape="rectangular"
                         data-theme="outline"
                         data-text="signin_with"
                         data-size="large"
                         data-logo_alignment="left"
                         style="width: 100%;">
                    </div>
                </div>

                <p style="text-align: center; margin-top: 20px;">
                    Don't have an account? <a href="/register" class="link">Register here</a>
                </p>
                <p style="text-align: center; margin-top: 10px;">
                    <a href="/" class="link">Back to Home</a>
                </p>
            </div>
        </div>

        <script src="https://accounts.google.com/gsi/client" async defer></script>
        <script>
            // Load OAuth config and initialize Google Sign-In
            fetch('/api/oauth/config')
                .then(response => response.json())
                .then(config => {{
                    if (config.google_client_id) {{
                        document.getElementById('g_id_onload').setAttribute('data-client_id', config.google_client_id);
                        // Re-render Google button
                        if (window.google) {{
                            google.accounts.id.initialize({{
                                client_id: config.google_client_id,
                                callback: handleGoogleSignIn
                            }});
                            google.accounts.id.renderButton(
                                document.querySelector('.g_id_signin'),
                                {{ theme: 'outline', size: 'large', width: '100%' }}
                            );
                        }}
                    }} else {{
                        document.getElementById('googleSignInContainer').style.display = 'none';
                        document.querySelector('.divider').style.display = 'none';
                    }}
                }})
                .catch(() => {{
                    document.getElementById('googleSignInContainer').style.display = 'none';
                    document.querySelector('.divider').style.display = 'none';
                }});

            function handleGoogleSignIn(response) {{
                fetch('/api/auth/google', {{
                    method: 'POST',
                    headers: {{
                        'Content-Type': 'application/json',
                    }},
                    body: JSON.stringify({{
                        credential: response.credential
                    }})
                }})
                .then(response => response.json())
                .then(data => {{
                    if (data.access_token) {{
                        localStorage.setItem('access_token', data.access_token);
                        window.location.href = '/my_files';
                    }} else {{
                        showError(data.detail || 'Google sign-in failed');
                    }}
                }})
                .catch(error => {{
                    showError('Google sign-in failed: ' + error.message);
                }});
            }}

            document.getElementById('loginForm').addEventListener('submit', async function(e) {{
                e.preventDefault();

                const email = document.getElementById('email').value;
                const password = document.getElementById('password').value;

                try {{
                    const response = await fetch('/api/login', {{
                        method: 'POST',
                        headers: {{
                            'Content-Type': 'application/json',
                        }},
                        body: JSON.stringify({{ email, password }})
                    }});

                    const data = await response.json();

                    if (response.ok) {{
                        localStorage.setItem('access_token', data.access_token);
                        window.location.href = '/my_files';
                    }} else {{
                        showError(data.detail || 'Login failed');
                    }}
                }} catch (error) {{
                    showError('Login failed: ' + error.message);
                }}
            }});

            function showError(message) {{
                const errorDiv = document.getElementById('errorMessage');
                errorDiv.textContent = message;
                errorDiv.style.display = 'block';
                document.getElementById('successMessage').style.display = 'none';
            }}

            function showSuccess(message) {{
                const successDiv = document.getElementById('successMessage');
                successDiv.textContent = message;
                successDiv.style.display = 'block';
                document.getElementById('errorMessage').style.display = 'none';
            }}
        </script>
    </body>
    </html>
    """


def get_register_page() -> str:
    """Return the registration page HTML."""
    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Register - PutPlace</title>
        <link rel="icon" type="image/svg+xml" href="/static/images/favicon.svg">
        <style>
            {get_base_styles()}
            .register-container {{
                max-width: 450px;
            }}
        </style>
    </head>
    <body>
        <div class="container register-container">
            <div class="header">
                <h1>Register</h1>
                <p>Create your account</p>
            </div>

            <div class="content">
                <div id="errorMessage" class="error-message"></div>
                <div id="successMessage" class="success-message"></div>

                <form id="registerForm">
                    <div class="form-group">
                        <label for="email">Email</label>
                        <input type="email" id="email" name="email" required placeholder="Enter your email">
                    </div>

                    <div class="form-group">
                        <label for="password">Password</label>
                        <input type="password" id="password" name="password" required placeholder="Choose a password (min 8 characters)" minlength="8">
                    </div>

                    <button type="submit" class="btn" style="width: 100%;">Register</button>
                </form>

                <p style="text-align: center; margin-top: 20px;">
                    Already have an account? <a href="/login" class="link">Login here</a>
                </p>
                <p style="text-align: center; margin-top: 10px;">
                    <a href="/" class="link">Back to Home</a>
                </p>
            </div>
        </div>

        <script>
            document.getElementById('registerForm').addEventListener('submit', async function(e) {{
                e.preventDefault();

                const email = document.getElementById('email').value;
                const password = document.getElementById('password').value;

                try {{
                    const response = await fetch('/api/register', {{
                        method: 'POST',
                        headers: {{
                            'Content-Type': 'application/json',
                        }},
                        body: JSON.stringify({{
                            email,
                            password
                        }})
                    }});

                    const data = await response.json();

                    if (response.ok) {{
                        // Redirect to awaiting confirmation page
                        window.location.href = '/awaiting-confirmation?email=' + encodeURIComponent(email);
                    }} else {{
                        showError(data.detail || 'Registration failed');
                    }}
                }} catch (error) {{
                    showError('Registration failed: ' + error.message);
                }}
            }});

            function showError(message) {{
                const errorDiv = document.getElementById('errorMessage');
                errorDiv.textContent = message;
                errorDiv.style.display = 'block';
                document.getElementById('successMessage').style.display = 'none';
            }}

            function showSuccess(message) {{
                const successDiv = document.getElementById('successMessage');
                successDiv.textContent = message;
                successDiv.style.display = 'block';
                document.getElementById('errorMessage').style.display = 'none';
            }}
        </script>
    </body>
    </html>
    """


def get_awaiting_confirmation_page(email: str = "") -> str:
    """Return the email confirmation waiting page HTML."""
    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Confirm Your Email - PutPlace</title>
        <link rel="icon" type="image/svg+xml" href="/static/images/favicon.svg">
        <style>
            {get_base_styles()}
            .confirm-container {{
                max-width: 500px;
            }}
            .email-icon {{
                font-size: 4rem;
                margin-bottom: 20px;
            }}
            .checking {{
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 10px;
                color: #667eea;
            }}
            .spinner {{
                width: 20px;
                height: 20px;
                border: 2px solid #f3f3f3;
                border-top: 2px solid #667eea;
                border-radius: 50%;
                animation: spin 1s linear infinite;
            }}
            @keyframes spin {{
                0% {{ transform: rotate(0deg); }}
                100% {{ transform: rotate(360deg); }}
            }}
        </style>
    </head>
    <body>
        <div class="container confirm-container">
            <div class="header">
                <div class="email-icon">&#9993;</div>
                <h1>Check Your Email</h1>
                <p>We've sent a confirmation link</p>
            </div>

            <div class="content" style="text-align: center;">
                <p style="font-size: 1.1rem; margin-bottom: 20px;">
                    We've sent a confirmation email to:
                </p>
                <p style="font-size: 1.2rem; font-weight: bold; color: #667eea; margin-bottom: 30px;">
                    {email if email else "your email address"}
                </p>

                <div class="card">
                    <h3>What to do next:</h3>
                    <ol style="text-align: left; padding-left: 20px;">
                        <li>Check your inbox for an email from PutPlace</li>
                        <li>Click the confirmation link in the email</li>
                        <li>You'll be redirected to log in</li>
                    </ol>
                </div>

                <div id="statusCheck" class="checking" style="margin: 30px 0;">
                    <div class="spinner"></div>
                    <span>Checking confirmation status...</span>
                </div>

                <p style="color: #6c757d; font-size: 0.9rem;">
                    Didn't receive the email? Check your spam folder or
                    <a href="/register" class="link">try registering again</a>.
                </p>

                <p style="margin-top: 20px;">
                    <a href="/" class="link">Back to Home</a>
                </p>
            </div>
        </div>

        <script>
            const email = "{email}";

            // Poll for confirmation status
            async function checkStatus() {{
                if (!email) return;

                try {{
                    const response = await fetch('/api/check-confirmation-status?email=' + encodeURIComponent(email));
                    const data = await response.json();

                    if (data.confirmed) {{
                        document.getElementById('statusCheck').innerHTML = `
                            <span style="color: #28a745; font-weight: bold;">
                                Email confirmed! Redirecting to login...
                            </span>
                        `;
                        setTimeout(() => {{
                            window.location.href = '/login';
                        }}, 2000);
                    }} else {{
                        // Check again in 5 seconds
                        setTimeout(checkStatus, 5000);
                    }}
                }} catch (error) {{
                    console.error('Error checking status:', error);
                    setTimeout(checkStatus, 10000);
                }}
            }}

            // Start polling
            if (email) {{
                checkStatus();
            }} else {{
                document.getElementById('statusCheck').style.display = 'none';
            }}
        </script>
    </body>
    </html>
    """

def get_my_files_page() -> str:
    """Generate the My Files page HTML."""
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>My Files - PutPlace</title>
        <link rel="icon" type="image/svg+xml" href="/static/images/favicon.svg">
        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
                line-height: 1.6;
                color: #333;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                padding: 20px;
            }
            .container {
                max-width: 1200px;
                margin: 0 auto;
                background: white;
                border-radius: 10px;
                box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
                overflow: hidden;
            }
            .header {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 30px 40px;
                display: flex;
                justify-content: space-between;
                align-items: center;
            }
            .header h1 {
                font-size: 2rem;
            }
            .header-buttons {
                display: flex;
                gap: 10px;
            }
            .btn {
                padding: 10px 20px;
                background: rgba(255, 255, 255, 0.2);
                color: white;
                border: 2px solid white;
                border-radius: 5px;
                cursor: pointer;
                font-weight: 500;
                text-decoration: none;
                transition: all 0.3s ease;
            }
            .btn:hover {
                background: white;
                color: #667eea;
            }
            .content {
                padding: 40px;
            }
            .loading {
                text-align: center;
                padding: 40px;
                color: #6c757d;
            }
            .error {
                background: #fee;
                color: #c33;
                border: 1px solid #fcc;
                padding: 15px;
                border-radius: 5px;
                margin-bottom: 20px;
            }
            .no-files {
                text-align: center;
                padding: 60px 20px;
                color: #6c757d;
            }
            .no-files h3 {
                color: #495057;
                margin-bottom: 15px;
                font-size: 1.5rem;
            }
            .no-files p {
                margin-bottom: 25px;
                font-size: 1.1rem;
            }
            .stats {
                display: flex;
                gap: 20px;
                margin-bottom: 30px;
                flex-wrap: wrap;
            }
            .stat-card {
                flex: 1;
                min-width: 200px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 20px;
                border-radius: 8px;
                text-align: center;
            }
            .stat-number {
                font-size: 2rem;
                font-weight: bold;
                margin-bottom: 5px;
            }
            .stat-label {
                font-size: 0.9rem;
                opacity: 0.9;
            }
            .files-list {
                margin-top: 20px;
            }
            .file-item {
                background: #f8f9fa;
                border-left: 4px solid #667eea;
                padding: 15px 20px;
                margin-bottom: 10px;
                border-radius: 5px;
                transition: all 0.2s;
            }
            .file-item:hover {
                background: #e9ecef;
                transform: translateX(5px);
            }
            .file-path {
                font-family: 'Courier New', monospace;
                font-size: 0.95rem;
                color: #495057;
                margin-bottom: 5px;
            }
            .file-meta {
                font-size: 0.85rem;
                color: #6c757d;
                display: flex;
                gap: 20px;
                flex-wrap: wrap;
            }
            .file-host {
                font-weight: 600;
                color: #667eea;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>📁 My Files</h1>
                <div class="header-buttons">
                    <a href="/" class="btn">Home</a>
                    <a href="/api_keys_page" class="btn">API Keys</a>
                    <button onclick="logout()" class="btn">Logout</button>
                </div>
            </div>

            <div class="content">
                <div id="loading" class="loading">
                    <p>Loading your files...</p>
                </div>
                <div id="error" class="error" style="display: none;"></div>
                <div id="stats" class="stats" style="display: none;"></div>
                <div id="filesList" class="files-list"></div>
            </div>
        </div>

        <script>
            async function loadFiles() {
                const token = localStorage.getItem('access_token');

                if (!token) {
                    window.location.href = '/login';
                    return;
                }

                try {
                    const response = await fetch('/api/my_files', {
                        headers: {
                            'Authorization': `Bearer ${token}`
                        }
                    });

                    if (response.status === 401) {
                        localStorage.removeItem('access_token');
                        window.location.href = '/login';
                        return;
                    }

                    if (!response.ok) {
                        throw new Error(`HTTP error! status: ${response.status}`);
                    }

                    const files = await response.json();

                    document.getElementById('loading').style.display = 'none';

                    if (files.length === 0) {
                        document.getElementById('filesList').innerHTML = `
                            <div class="no-files">
                                <h3>No files yet</h3>
                                <p>Upload some files to see them here!</p>
                                <p style="font-size: 0.9rem; color: #6c757d;">
                                    Use the PutPlace client or API to upload file metadata.
                                </p>
                            </div>
                        `;
                        return;
                    }

                    // Calculate stats
                    const totalSize = files.reduce((sum, f) => sum + (f.file_size || 0), 0);
                    const hosts = new Set(files.map(f => f.hostname)).size;

                    // Display stats
                    document.getElementById('stats').innerHTML = `
                        <div class="stat-card">
                            <div class="stat-number">${files.length}</div>
                            <div class="stat-label">Total Files</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-number">${formatBytes(totalSize)}</div>
                            <div class="stat-label">Total Size</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-number">${hosts}</div>
                            <div class="stat-label">Hosts</div>
                        </div>
                    `;
                    document.getElementById('stats').style.display = 'flex';

                    // Display files
                    const filesHtml = files.map(file => `
                        <div class="file-item">
                            <div class="file-path">${escapeHtml(file.filepath)}</div>
                            <div class="file-meta">
                                <span class="file-host">🖥️ ${escapeHtml(file.hostname)}</span>
                                <span>📦 ${formatBytes(file.file_size || 0)}</span>
                                <span>🔐 ${file.sha256.substring(0, 16)}...</span>
                            </div>
                        </div>
                    `).join('');

                    document.getElementById('filesList').innerHTML = filesHtml;

                } catch (error) {
                    console.error('Error loading files:', error);
                    document.getElementById('loading').style.display = 'none';
                    document.getElementById('error').textContent = 'Failed to load files. Please try again.';
                    document.getElementById('error').style.display = 'block';
                }
            }

            function formatBytes(bytes) {
                if (bytes === 0) return '0 B';
                const k = 1024;
                const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
                const i = Math.floor(Math.log(bytes) / Math.log(k));
                return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + ' ' + sizes[i];
            }

            function escapeHtml(text) {
                const div = document.createElement('div');
                div.textContent = text;
                return div.innerHTML;
            }

            function logout() {
                localStorage.removeItem('access_token');
                window.location.href = '/login';
            }

            // Load files on page load
            loadFiles();
        </script>
    </body>
    </html>
    """
