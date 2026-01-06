"""Admin routes for PutPlace."""

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse

from ..database import MongoDB
from ..dependencies import get_current_admin_user, get_db

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/dashboard", response_class=HTMLResponse)
async def admin_dashboard(
    current_admin: Annotated[dict, Depends(get_current_admin_user)],
    db: Annotated[MongoDB, Depends(get_db)],
):
    """Admin dashboard showing user and file statistics.

    Requires admin privileges.
    """
    # Get dashboard statistics
    stats = await db.get_dashboard_stats()

    # Get all users with file counts
    users = await db.get_all_users()
    file_counts = await db.get_user_file_counts()

    # Get pending users
    pending_users = await db.get_all_pending_users()

    # Build HTML
    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Admin Dashboard - PutPlace</title>
        <style>
            * {{
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }}

            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                padding: 20px;
            }}

            .container {{
                max-width: 1200px;
                margin: 0 auto;
            }}

            .header {{
                background: white;
                border-radius: 12px;
                padding: 30px;
                margin-bottom: 30px;
                box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            }}

            h1 {{
                color: #333;
                font-size: 32px;
                margin-bottom: 10px;
            }}

            .subtitle {{
                color: #666;
                font-size: 16px;
            }}

            .stats-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
                gap: 20px;
                margin-bottom: 30px;
            }}

            .stat-card {{
                background: white;
                border-radius: 12px;
                padding: 24px;
                box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
                transition: transform 0.2s;
            }}

            .stat-card:hover {{
                transform: translateY(-4px);
                box-shadow: 0 8px 12px rgba(0, 0, 0, 0.15);
            }}

            .stat-label {{
                color: #666;
                font-size: 14px;
                font-weight: 500;
                text-transform: uppercase;
                letter-spacing: 0.5px;
                margin-bottom: 8px;
            }}

            .stat-value {{
                color: #667eea;
                font-size: 36px;
                font-weight: 700;
            }}

            .section {{
                background: white;
                border-radius: 12px;
                padding: 30px;
                margin-bottom: 20px;
                box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            }}

            h2 {{
                color: #333;
                font-size: 24px;
                margin-bottom: 20px;
                border-bottom: 2px solid #667eea;
                padding-bottom: 10px;
            }}

            table {{
                width: 100%;
                border-collapse: collapse;
            }}

            th {{
                background: #f8f9fa;
                color: #333;
                font-weight: 600;
                text-align: left;
                padding: 12px;
                border-bottom: 2px solid #dee2e6;
            }}

            td {{
                padding: 12px;
                border-bottom: 1px solid #dee2e6;
                color: #495057;
            }}

            tr:hover {{
                background: #f8f9fa;
            }}

            .badge {{
                display: inline-block;
                padding: 4px 12px;
                border-radius: 12px;
                font-size: 12px;
                font-weight: 600;
            }}

            .badge-admin {{
                background: #667eea;
                color: white;
            }}

            .badge-active {{
                background: #51cf66;
                color: white;
            }}

            .badge-inactive {{
                background: #ff6b6b;
                color: white;
            }}

            .badge-pending {{
                background: #ffa94d;
                color: white;
            }}

            .empty-state {{
                text-align: center;
                padding: 40px;
                color: #868e96;
            }}

            .empty-state-icon {{
                font-size: 48px;
                margin-bottom: 16px;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>Admin Dashboard</h1>
                <p class="subtitle">System overview and user management</p>
            </div>

            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-label">Total Users</div>
                    <div class="stat-value">{stats['total_users']}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Active Users</div>
                    <div class="stat-value">{stats['active_users']}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Admin Users</div>
                    <div class="stat-value">{stats['admin_users']}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Pending Registrations</div>
                    <div class="stat-value">{stats['pending_users']}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Total Files</div>
                    <div class="stat-value">{stats['total_files']}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Files with Content</div>
                    <div class="stat-value">{stats['files_with_content']}</div>
                </div>
            </div>

            <div class="section">
                <h2>Registered Users</h2>
                {_render_users_table(users, file_counts)}
            </div>

            <div class="section">
                <h2>Pending Registrations</h2>
                {_render_pending_users_table(pending_users)}
            </div>
        </div>
    </body>
    </html>
    """

    return html


def _render_users_table(users: list[dict], file_counts: dict[str, int]) -> str:
    """Render the registered users table."""
    if not users:
        return """
        <div class="empty-state">
            <div class="empty-state-icon">👥</div>
            <p>No registered users yet</p>
        </div>
        """

    rows = []
    for user in users:
        user_id = user.get("_id", "")
        email = user.get("email", "N/A")
        full_name = user.get("full_name", "N/A")
        is_admin = user.get("is_admin", False)
        is_active = user.get("is_active", True)
        file_count = file_counts.get(user_id, 0)
        created_at = user.get("created_at", "N/A")

        # Format created_at
        if created_at != "N/A":
            try:
                # If it's a datetime object, format it
                if hasattr(created_at, 'strftime'):
                    created_at = created_at.strftime("%Y-%m-%d %H:%M")
                else:
                    created_at = str(created_at)[:19]  # Truncate to datetime portion
            except Exception:
                created_at = str(created_at)

        admin_badge = '<span class="badge badge-admin">Admin</span>' if is_admin else ''
        status_badge = '<span class="badge badge-active">Active</span>' if is_active else '<span class="badge badge-inactive">Inactive</span>'

        rows.append(f"""
        <tr>
            <td>{email}</td>
            <td>{full_name}</td>
            <td>{admin_badge} {status_badge}</td>
            <td>{file_count}</td>
            <td>{created_at}</td>
        </tr>
        """)

    return f"""
    <table>
        <thead>
            <tr>
                <th>Email</th>
                <th>Full Name</th>
                <th>Status</th>
                <th>Files Uploaded</th>
                <th>Created At</th>
            </tr>
        </thead>
        <tbody>
            {''.join(rows)}
        </tbody>
    </table>
    """


def _render_pending_users_table(pending_users: list[dict]) -> str:
    """Render the pending users table."""
    if not pending_users:
        return """
        <div class="empty-state">
            <div class="empty-state-icon">⏳</div>
            <p>No pending registrations</p>
        </div>
        """

    rows = []
    for user in pending_users:
        email = user.get("email", "N/A")
        full_name = user.get("full_name", "N/A")
        created_at = user.get("created_at", "N/A")

        # Format created_at
        if created_at != "N/A":
            try:
                if hasattr(created_at, 'strftime'):
                    created_at = created_at.strftime("%Y-%m-%d %H:%M")
                else:
                    created_at = str(created_at)[:19]
            except Exception:
                created_at = str(created_at)

        rows.append(f"""
        <tr>
            <td>{email}</td>
            <td>{full_name}</td>
            <td><span class="badge badge-pending">Pending Confirmation</span></td>
            <td>{created_at}</td>
        </tr>
        """)

    return f"""
    <table>
        <thead>
            <tr>
                <th>Email</th>
                <th>Full Name</th>
                <th>Status</th>
                <th>Registered At</th>
            </tr>
        </thead>
        <tbody>
            {''.join(rows)}
        </tbody>
    </table>
    """
