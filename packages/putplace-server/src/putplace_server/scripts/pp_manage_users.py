#!/usr/bin/env python3
"""Manage users in the PutPlace database.

This script allows administrators to manage users directly in the MongoDB database.

Note: In PutPlace, email addresses serve as usernames. Users are identified and
      authenticated by their email address.

Usage:
    # List all users
    pp_manage_users list

    # Add a new user
    pp_manage_users add --email user@example.com --password secret123

    # Delete a user
    pp_manage_users delete --email user@example.com

    # Reset a user's password
    pp_manage_users reset-password --email user@example.com --password newpass123

    # Interactive mode (prompts for values)
    pp_manage_users add
    pp_manage_users reset-password
"""

import argparse
import asyncio
import getpass
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv
from pymongo import AsyncMongoClient
from pymongo.errors import ConnectionFailure, DuplicateKeyError, ServerSelectionTimeoutError
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# Import tomli for Python < 3.11, tomllib for Python >= 3.11
if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None  # type: ignore

# Load environment variables from .env file if it exists
# This allows using .env for local development configuration
load_dotenv()

DEFAULT_MONGODB_URL = "mongodb://localhost:27017"
DEFAULT_DATABASE = "putplace"
DEFAULT_CONFIG_FILE = "ppserver.toml"

# Rich console for colored output
console = Console()


def load_config_from_file(config_file: Optional[Path]) -> dict[str, Any]:
    """Load configuration from ppserver.toml file.

    Args:
        config_file: Path to config file, or None to search default locations

    Returns:
        Dictionary with mongodb_url and database, or empty dict if not found
    """
    if tomllib is None:
        return {}

    # If config_file is specified, use it directly
    if config_file:
        if not config_file.exists():
            print_warning(f"Config file not found: {config_file}")
            return {}
        target_file = config_file
    else:
        # Search default location (current directory)
        target_file = Path.cwd() / DEFAULT_CONFIG_FILE
        if not target_file.exists():
            return {}

    try:
        with open(target_file, "rb") as f:
            toml_data = tomllib.load(f)

        config = {}

        # Extract mongodb_url from [database] section
        if "database" in toml_data:
            db_config = toml_data["database"]
            if "mongodb_url" in db_config:
                config["mongodb_url"] = db_config["mongodb_url"]
            # Support both "database" and "mongodb_database" field names
            if "database" in db_config:
                config["database"] = db_config["database"]
            elif "mongodb_database" in db_config:
                config["database"] = db_config["mongodb_database"]

        return config
    except Exception as e:
        print_warning(f"Failed to load config file {target_file}: {e}")
        return {}


def print_success(message: str) -> None:
    """Print a success message in green."""
    console.print(f"[green]✓[/green] {message}")


def print_error(message: str) -> None:
    """Print an error message in red."""
    console.print(f"[red]✗[/red] {message}")


def print_warning(message: str) -> None:
    """Print a warning message in yellow."""
    console.print(f"[yellow]![/yellow] {message}")


def print_info(message: str) -> None:
    """Print an info message in blue."""
    console.print(f"[blue]→[/blue] {message}")


async def get_user_by_email(client: AsyncMongoClient, database: str, email: str) -> dict | None:
    """Find a user by email address.

    Args:
        client: MongoDB client
        database: Database name
        email: User's email address

    Returns:
        User document or None if not found
    """
    db = client[database]
    users_collection = db["users"]
    return await users_collection.find_one({"email": email})


async def list_users_detailed(client: AsyncMongoClient, database: str) -> list[dict]:
    """List all users with details.

    Args:
        client: MongoDB client
        database: Database name

    Returns:
        List of user documents
    """
    db = client[database]
    users_collection = db["users"]

    users = []
    async for user in users_collection.find(
        {},
        {"email": 1, "is_admin": 1, "is_active": 1, "created_at": 1}
    ):
        users.append(user)

    return users


async def list_pending_users(client: AsyncMongoClient, database: str) -> list[dict]:
    """List all pending users awaiting email confirmation.

    Args:
        client: MongoDB client
        database: Database name

    Returns:
        List of pending user documents
    """
    db = client[database]
    pending_collection = db["pending_users"]

    pending = []
    async for user in pending_collection.find(
        {},
        {"email": 1, "created_at": 1, "expires_at": 1}
    ):
        pending.append(user)

    return pending


async def get_pending_user_by_email(
    client: AsyncMongoClient, database: str, email: str
) -> dict | None:
    """Find a pending user by email address.

    Args:
        client: MongoDB client
        database: Database name
        email: User's email address

    Returns:
        Pending user document or None if not found
    """
    db = client[database]
    pending_collection = db["pending_users"]
    return await pending_collection.find_one({"email": email})


async def approve_pending_user(
    client: AsyncMongoClient, database: str, email: str, is_admin: bool = False
) -> tuple[bool, str]:
    """Approve a pending user by moving them to the users collection.

    Note: Email address is used as the username for authentication.

    Args:
        client: MongoDB client
        database: Database name
        email: User's email address (also used as username)
        is_admin: Whether to make the user an admin

    Returns:
        Tuple of (success, message)
    """
    db = client[database]
    pending_collection = db["pending_users"]
    users_collection = db["users"]

    # Get the pending user
    pending_user = await pending_collection.find_one({"email": email})
    if not pending_user:
        return False, f"Pending user with email '{email}' not found"

    # Check if user already exists in main collection
    existing = await users_collection.find_one({"email": email})
    if existing:
        return False, f"User with email '{email}' already exists in main users table"

    # Create user in main collection
    user_data = {
        "email": pending_user["email"],
        "username": pending_user["email"],  # Use email as username for uniqueness
        "hashed_password": pending_user["hashed_password"],
        "is_active": True,
        "is_admin": is_admin,
        "created_at": datetime.utcnow(),
    }

    await users_collection.insert_one(user_data)

    # Delete from pending collection
    await pending_collection.delete_one({"email": email})

    return True, f"User '{email}' approved and moved to users table"


async def create_user(
    client: AsyncMongoClient,
    database: str,
    email: str,
    hashed_password: str,
    is_admin: bool = False
) -> str:
    """Create a new user.

    Note: Email address is used as the username for authentication.

    Args:
        client: MongoDB client
        database: Database name
        email: User's email address (also used as username)
        hashed_password: Hashed password
        is_admin: Whether user is an admin

    Returns:
        Inserted user ID

    Raises:
        DuplicateKeyError: If email already exists
    """
    db = client[database]
    users_collection = db["users"]

    user_data = {
        "email": email,
        "username": email,  # Use email as username for uniqueness
        "hashed_password": hashed_password,
        "is_active": True,
        "is_admin": is_admin,
        "created_at": datetime.utcnow(),
    }

    result = await users_collection.insert_one(user_data)
    return str(result.inserted_id)


async def delete_user(client: AsyncMongoClient, database: str, email: str) -> bool:
    """Delete a user by email.

    Args:
        client: MongoDB client
        database: Database name
        email: User's email address

    Returns:
        True if user was deleted, False otherwise
    """
    db = client[database]
    users_collection = db["users"]

    result = await users_collection.delete_one({"email": email})
    return result.deleted_count > 0


async def update_password(
    client: AsyncMongoClient, database: str, email: str, hashed_password: str
) -> bool:
    """Update a user's password.

    Args:
        client: MongoDB client
        database: Database name
        email: User's email address
        hashed_password: New hashed password

    Returns:
        True if password was updated, False otherwise
    """
    db = client[database]
    users_collection = db["users"]

    result = await users_collection.update_one(
        {"email": email},
        {"$set": {"hashed_password": hashed_password}}
    )

    return result.modified_count > 0


async def update_admin_status(
    client: AsyncMongoClient, database: str, email: str, is_admin: bool
) -> bool:
    """Update a user's admin status.

    Args:
        client: MongoDB client
        database: Database name
        email: User's email address
        is_admin: Whether user should be admin

    Returns:
        True if status was updated, False otherwise
    """
    db = client[database]
    users_collection = db["users"]

    result = await users_collection.update_one(
        {"email": email},
        {"$set": {"is_admin": is_admin}}
    )

    return result.modified_count > 0


def prompt_for_password(prompt: str = "Password: ", confirm: bool = True) -> str:
    """Prompt for password with optional confirmation.

    Args:
        prompt: The prompt to display
        confirm: Whether to require confirmation

    Returns:
        The confirmed password

    Raises:
        SystemExit: If passwords don't match after 3 attempts
    """
    max_attempts = 3

    for attempt in range(max_attempts):
        password = getpass.getpass(prompt)

        if len(password) < 8:
            print_error("Password must be at least 8 characters long.")
            continue

        if not confirm:
            return password

        confirm_pass = getpass.getpass("Confirm password: ")

        if password == confirm_pass:
            return password
        else:
            remaining = max_attempts - attempt - 1
            if remaining > 0:
                print_error(f"Passwords do not match. {remaining} attempts remaining.")
            else:
                print_error("Passwords do not match. Exiting.")
                sys.exit(1)

    sys.exit(1)


async def connect_to_mongodb(mongodb_url: str) -> AsyncMongoClient:
    """Connect to MongoDB and verify connection.

    Args:
        mongodb_url: MongoDB connection URL

    Returns:
        Connected MongoDB client

    Raises:
        SystemExit: If connection fails
    """
    print_info(f"Connecting to MongoDB at [cyan]{mongodb_url}[/cyan]...")

    try:
        client = AsyncMongoClient(mongodb_url, serverSelectionTimeoutMS=5000)
        await client.admin.command("ping")
        print_success("Connected successfully.")
        console.print()
        return client
    except (ConnectionFailure, ServerSelectionTimeoutError) as e:
        print_error(f"Could not connect to MongoDB: {e}")
        sys.exit(1)


async def cmd_list(args: argparse.Namespace) -> int:
    """Handle the 'list' command."""
    client = await connect_to_mongodb(args.mongodb_url)

    try:
        users = await list_users_detailed(client, args.database)

        if not users:
            if args.no_table:
                print("No users found.")
            else:
                print_warning(f"No users found in database '[cyan]{args.database}[/cyan]'.")
            return 0

        if args.no_table:
            # Plain text output for scripting
            print(f"{'Email':<50} {'Admin':<7} {'Active':<7} {'Created'}")
            print("-" * 80)
            for user in sorted(users, key=lambda u: u.get("email", "")):
                email = user.get("email", "N/A")
                is_admin = "Yes" if user.get("is_admin") else "No"
                is_active = "Yes" if user.get("is_active", True) else "No"
                created = user.get("created_at")
                created_str = created.strftime("%Y-%m-%d %H:%M") if created else "N/A"
                print(f"{email:<50} {is_admin:<7} {is_active:<7} {created_str}")
            print(f"\nTotal: {len(users)} users")
        else:
            # Rich table output
            table = Table(title=f"Users in [cyan]{args.database}[/cyan]", show_header=True)
            table.add_column("Email", style="cyan", no_wrap=True)
            table.add_column("Admin", justify="center")
            table.add_column("Active", justify="center")
            table.add_column("Created", style="dim")

            for user in sorted(users, key=lambda u: u.get("email", "")):
                email = user.get("email", "N/A")
                is_admin = "[green]Yes[/green]" if user.get("is_admin") else "[dim]No[/dim]"
                is_active = "[green]Yes[/green]" if user.get("is_active", True) else "[red]No[/red]"
                created = user.get("created_at")
                created_str = created.strftime("%Y-%m-%d %H:%M") if created else "N/A"

                table.add_row(email, is_admin, is_active, created_str)

            console.print(table)
            console.print(f"\n[bold]Total:[/bold] {len(users)} users")
        return 0

    finally:
        await client.close()


async def cmd_pending(args: argparse.Namespace) -> int:
    """Handle the 'pending' command."""
    client = await connect_to_mongodb(args.mongodb_url)

    try:
        pending = await list_pending_users(client, args.database)

        if not pending:
            if args.no_table:
                print("No pending users found.")
            else:
                print_warning(f"No pending users in database '[cyan]{args.database}[/cyan]'.")
            return 0

        from datetime import datetime

        if args.no_table:
            # Plain text output for scripting
            print(f"{'Email':<50} {'Created':<18} {'Expires'}")
            print("-" * 80)
            for user in sorted(pending, key=lambda u: u.get("email", "")):
                email = user.get("email", "N/A")
                created = user.get("created_at")
                created_str = created.strftime("%Y-%m-%d %H:%M") if created else "N/A"
                expires = user.get("expires_at")
                if expires:
                    if expires < datetime.utcnow():
                        expires_str = expires.strftime("%Y-%m-%d %H:%M") + " (EXPIRED)"
                    else:
                        expires_str = expires.strftime("%Y-%m-%d %H:%M")
                else:
                    expires_str = "N/A"
                print(f"{email:<50} {created_str:<18} {expires_str}")
            print(f"\nTotal: {len(pending)} pending users")
        else:
            # Rich table output
            table = Table(
                title=f"Pending Users in [cyan]{args.database}[/cyan]",
                show_header=True
            )
            table.add_column("Email", style="cyan", no_wrap=True)
            table.add_column("Created", style="dim")
            table.add_column("Expires", style="yellow")

            for user in sorted(pending, key=lambda u: u.get("email", "")):
                email = user.get("email", "N/A")
                created = user.get("created_at")
                created_str = created.strftime("%Y-%m-%d %H:%M") if created else "N/A"
                expires = user.get("expires_at")
                if expires:
                    if expires < datetime.utcnow():
                        expires_str = f"[red]{expires.strftime('%Y-%m-%d %H:%M')} (EXPIRED)[/red]"
                    else:
                        expires_str = expires.strftime("%Y-%m-%d %H:%M")
                else:
                    expires_str = "N/A"

                table.add_row(email, created_str, expires_str)

            console.print(table)
            console.print(f"\n[bold]Total:[/bold] {len(pending)} pending users")
        return 0

    finally:
        await client.close()


async def cmd_approve(args: argparse.Namespace) -> int:
    """Handle the 'approve' command."""
    console.print(Panel("[bold]Approve Pending User[/bold]", style="green"))
    console.print()

    client = await connect_to_mongodb(args.mongodb_url)

    try:
        email = args.email
        if not email:
            # Show available pending users
            pending = await list_pending_users(client, args.database)
            if pending:
                console.print(f"[bold]Pending users in '[cyan]{args.database}[/cyan]':[/bold]")
                for user in sorted(pending, key=lambda u: u.get("email", "")):
                    console.print(f"  [dim]•[/dim] [cyan]{user.get('email')}[/cyan]")
                console.print()
            else:
                print_warning("No pending users found.")
                return 0

            email = console.input("[bold]Email:[/bold] ").strip()
            if not email:
                print_error("Email is required.")
                return 1

        # Get pending user details
        pending_user = await get_pending_user_by_email(client, args.database, email)
        if not pending_user:
            print_error(f"Pending user with email '[cyan]{email}[/cyan]' not found.")
            return 1

        console.print(f"Pending user: [cyan]{email}[/cyan]")

        # Approve the user
        success, message = await approve_pending_user(
            client, args.database, email, args.admin
        )

        console.print()
        if success:
            print_success(message)
            if args.admin:
                console.print("  [yellow]User granted admin privileges[/yellow]")
            return 0
        else:
            print_error(message)
            return 1

    finally:
        await client.close()


async def cmd_add(args: argparse.Namespace) -> int:
    """Handle the 'add' command."""
    console.print(Panel("[bold]Add New User[/bold]", style="blue"))
    console.print()

    client = await connect_to_mongodb(args.mongodb_url)

    try:
        # Get email
        email = args.email
        if not email:
            email = console.input("[bold]Email:[/bold] ").strip()
            if not email:
                print_error("Email is required.")
                return 1

        # Check if user already exists
        existing = await get_user_by_email(client, args.database, email)
        if existing:
            print_error(f"User with email '[cyan]{email}[/cyan]' already exists.")
            return 1

        # Get password
        password = args.password
        if not password:
            console.print()
            password = prompt_for_password("Password: ", confirm=True)

        # Validate password
        if len(password) < 8:
            print_error("Password must be at least 8 characters long.")
            return 1

        # Hash the password
        from putplace_server.user_auth import get_password_hash
        hashed_password = get_password_hash(password)

        # Confirm in interactive mode
        if not args.email:
            console.print()
            console.print("[bold]Create user:[/bold]")
            console.print(f"  Email: [cyan]{email}[/cyan]")
            admin_str = "[green]Yes[/green]" if args.admin else "[dim]No[/dim]"
            console.print(f"  Admin: {admin_str}")
            console.print()
            console.print(f"  [dim]Database: {args.database}[/dim]")
            if hasattr(args, '_config_file_used') and args._config_file_used:
                console.print(f"  [dim]Config:   {args._config_file_used}[/dim]")

            confirm = console.input("\n[bold]Proceed?[/bold] [dim][y/N][/dim]: ").strip().lower()
            if confirm != 'y':
                print_warning("Cancelled.")
                return 0

        # Create the user
        try:
            user_id = await create_user(
                client,
                args.database,
                email,
                hashed_password,
                args.admin
            )
            console.print()
            print_success(f"User '[cyan]{email}[/cyan]' created successfully.")
            console.print(f"  [dim]ID: {user_id}[/dim]")
            return 0

        except DuplicateKeyError:
            print_error(f"User with email '[cyan]{email}[/cyan]' already exists.")
            return 1

    finally:
        await client.close()


async def cmd_delete(args: argparse.Namespace) -> int:
    """Handle the 'delete' command."""
    console.print(Panel("[bold]Delete User[/bold]", style="red"))
    console.print()

    client = await connect_to_mongodb(args.mongodb_url)

    try:
        # Get email
        email = args.email
        if not email:
            # Show available users
            users = await list_users_detailed(client, args.database)
            if users:
                console.print(f"[bold]Users in '[cyan]{args.database}[/cyan]':[/bold]")
                for user in sorted(users, key=lambda u: u.get("email", "")):
                    admin_badge = " [yellow][admin][/yellow]" if user.get("is_admin") else ""
                    console.print(f"  [dim]•[/dim] [cyan]{user.get('email')}[/cyan]{admin_badge}")
                console.print()

            email = console.input("[bold]Email of user to delete:[/bold] ").strip()
            if not email:
                print_error("Email is required.")
                return 1

        # Verify user exists
        user = await get_user_by_email(client, args.database, email)
        if not user:
            print_error(f"User with email '[cyan]{email}[/cyan]' not found.")
            return 1

        # Show user info
        console.print()
        console.print("[bold]User to delete:[/bold]")
        console.print(f"  Email: [cyan]{email}[/cyan]")
        if user.get("full_name"):
            console.print(f"  Name:  [white]{user['full_name']}[/white]")
        if user.get("is_admin"):
            console.print(f"  Role:  [yellow]Administrator[/yellow]")
        console.print()
        console.print(f"  [dim]Database: {args.database}[/dim]")
        if hasattr(args, '_config_file_used') and args._config_file_used:
            console.print(f"  [dim]Config:   {args._config_file_used}[/dim]")

        # Confirm deletion
        if not args.force:
            console.print()
            confirm = console.input(
                f"[bold red]Are you sure you want to delete this user?[/bold red] "
                "[dim][y/N][/dim]: "
            ).strip().lower()
            if confirm != 'y':
                print_warning("Cancelled.")
                return 0

        # Delete the user
        success = await delete_user(client, args.database, email)

        console.print()
        if success:
            print_success(f"User '[cyan]{email}[/cyan]' deleted successfully.")
            return 0
        else:
            print_error(f"Failed to delete user '[cyan]{email}[/cyan]'.")
            return 1

    finally:
        await client.close()


async def cmd_reset_password(args: argparse.Namespace) -> int:
    """Handle the 'reset-password' command."""
    console.print(Panel("[bold]Reset User Password[/bold]", style="yellow"))
    console.print()

    client = await connect_to_mongodb(args.mongodb_url)

    try:
        # Get email
        email = args.email
        if not email:
            # Show available users
            users = await list_users_detailed(client, args.database)
            if users:
                console.print(f"[bold]Users in '[cyan]{args.database}[/cyan]':[/bold]")
                for user in sorted(users, key=lambda u: u.get("email", "")):
                    admin_badge = " [yellow][admin][/yellow]" if user.get("is_admin") else ""
                    console.print(f"  [dim]•[/dim] [cyan]{user.get('email')}[/cyan]{admin_badge}")
                console.print()

            email = console.input("[bold]Email:[/bold] ").strip()
            if not email:
                print_error("Email is required.")
                return 1

        # Verify user exists
        user = await get_user_by_email(client, args.database, email)
        if not user:
            print_error(f"User with email '[cyan]{email}[/cyan]' not found.")
            return 1

        console.print()
        print_success(f"Found user: [cyan]{email}[/cyan]")
        if user.get("is_admin"):
            console.print(f"  Role: [yellow]Administrator[/yellow]")

        # Get password
        password = args.password
        if not password:
            console.print()
            password = prompt_for_password("New password: ", confirm=True)

        # Validate password
        if len(password) < 8:
            print_error("Password must be at least 8 characters long.")
            return 1

        # Hash the password
        from putplace_server.user_auth import get_password_hash
        hashed_password = get_password_hash(password)

        # Confirm in interactive mode
        if not args.password:
            console.print()
            console.print(f"  [dim]Database: {args.database}[/dim]")
            if hasattr(args, '_config_file_used') and args._config_file_used:
                console.print(f"  [dim]Config:   {args._config_file_used}[/dim]")
            console.print()
            confirm = console.input(
                f"[bold]Reset password for '[cyan]{email}[/cyan]'?[/bold] "
                "[dim][y/N][/dim]: "
            ).strip().lower()
            if confirm != 'y':
                print_warning("Cancelled.")
                return 0

        # Update the password
        success = await update_password(client, args.database, email, hashed_password)

        console.print()
        if success:
            print_success(f"Password successfully reset for '[cyan]{email}[/cyan]'.")
            return 0
        else:
            print_error(f"Failed to update password for '[cyan]{email}[/cyan]'.")
            return 1

    finally:
        await client.close()


async def cmd_setadmin(args: argparse.Namespace) -> int:
    """Handle the 'setadmin' command."""
    console.print(Panel("[bold]Grant Admin Privileges[/bold]", style="green"))
    console.print()

    client = await connect_to_mongodb(args.mongodb_url)

    try:
        email = args.email
        if not email:
            # Show available non-admin users
            users = await list_users_detailed(client, args.database)
            non_admins = [u for u in users if not u.get("is_admin")]
            if non_admins:
                console.print(f"[bold]Non-admin users in '[cyan]{args.database}[/cyan]':[/bold]")
                for user in sorted(non_admins, key=lambda u: u.get("email", "")):
                    console.print(f"  [dim]•[/dim] [cyan]{user.get('email')}[/cyan]")
                console.print()

            email = console.input("[bold]Email:[/bold] ").strip()
            if not email:
                print_error("Email is required.")
                return 1

        # Verify user exists
        user = await get_user_by_email(client, args.database, email)
        if not user:
            print_error(f"User with email '[cyan]{email}[/cyan]' not found.")
            return 1

        # Check if already admin
        if user.get("is_admin"):
            print_warning(f"User '[cyan]{email}[/cyan]' is already an administrator.")
            return 0

        console.print(f"User: [cyan]{email}[/cyan]")
        if user.get("full_name"):
            console.print(f"Name: [white]{user['full_name']}[/white]")

        # Update admin status
        success = await update_admin_status(client, args.database, email, True)

        console.print()
        if success:
            print_success(f"User '[cyan]{email}[/cyan]' is now an administrator.")
            return 0
        else:
            print_error(f"Failed to update admin status for '[cyan]{email}[/cyan]'.")
            return 1

    finally:
        await client.close()


async def cmd_unsetadmin(args: argparse.Namespace) -> int:
    """Handle the 'unsetadmin' command."""
    console.print(Panel("[bold]Revoke Admin Privileges[/bold]", style="yellow"))
    console.print()

    client = await connect_to_mongodb(args.mongodb_url)

    try:
        email = args.email
        if not email:
            # Show available admin users
            users = await list_users_detailed(client, args.database)
            admins = [u for u in users if u.get("is_admin")]
            if admins:
                console.print(f"[bold]Admin users in '[cyan]{args.database}[/cyan]':[/bold]")
                for user in sorted(admins, key=lambda u: u.get("email", "")):
                    console.print(f"  [dim]•[/dim] [cyan]{user.get('email')}[/cyan]")
                console.print()
            else:
                print_warning("No admin users found.")
                return 0

            email = console.input("[bold]Email:[/bold] ").strip()
            if not email:
                print_error("Email is required.")
                return 1

        # Verify user exists
        user = await get_user_by_email(client, args.database, email)
        if not user:
            print_error(f"User with email '[cyan]{email}[/cyan]' not found.")
            return 1

        # Check if not admin
        if not user.get("is_admin"):
            print_warning(f"User '[cyan]{email}[/cyan]' is not an administrator.")
            return 0

        console.print(f"User: [cyan]{email}[/cyan]")
        if user.get("full_name"):
            console.print(f"Name: [white]{user['full_name']}[/white]")

        # Update admin status
        success = await update_admin_status(client, args.database, email, False)

        console.print()
        if success:
            print_success(f"Admin privileges revoked for '[cyan]{email}[/cyan]'.")
            return 0
        else:
            print_error(f"Failed to update admin status for '[cyan]{email}[/cyan]'.")
            return 1

    finally:
        await client.close()


def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser with subcommands."""
    parser = argparse.ArgumentParser(
        prog="pp_manage_users",
        description="Manage users in the PutPlace database.\n\n"
                    "Note: Email addresses serve as usernames in PutPlace.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # List all users
    pp_manage_users list

    # List pending users awaiting email confirmation
    pp_manage_users pending

    # Approve a pending user (bypass email confirmation)
    pp_manage_users approve --email user@example.com

    # Approve a pending user and make them admin
    pp_manage_users approve --email user@example.com --admin

    # Add a new user interactively
    pp_manage_users add

    # Add a user with arguments
    pp_manage_users add --email user@example.com --password secret123

    # Add an admin user
    pp_manage_users add --email admin@example.com --password secret123 --admin

    # Delete a user
    pp_manage_users delete --email user@example.com

    # Reset a user's password
    pp_manage_users reset-password --email user@example.com --password newpass123

    # Grant admin privileges
    pp_manage_users setadmin --email user@example.com

    # Revoke admin privileges
    pp_manage_users unsetadmin --email user@example.com

    # Use a custom MongoDB URL
    pp_manage_users --mongodb-url mongodb://host:27017 list
        """
    )

    # Global arguments
    parser.add_argument(
        "--config-file",
        type=Path,
        help=f"Path to ppserver.toml config file (default: {DEFAULT_CONFIG_FILE} in current directory)"
    )
    parser.add_argument(
        "--mongodb-url",
        help=f"MongoDB connection URL (default: from config or {DEFAULT_MONGODB_URL})"
    )
    parser.add_argument(
        "--database",
        help=f"Database name (default: from config or {DEFAULT_DATABASE})"
    )

    # Subcommands
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # List command
    list_parser = subparsers.add_parser("list", help="List all users")
    list_parser.add_argument(
        "--no-table",
        action="store_true",
        help="Output plain text without table decorations (useful for scripting)"
    )
    list_parser.set_defaults(func=cmd_list)

    # Pending command
    pending_parser = subparsers.add_parser("pending", help="List pending users awaiting confirmation")
    pending_parser.add_argument(
        "--no-table",
        action="store_true",
        help="Output plain text without table decorations (useful for scripting)"
    )
    pending_parser.set_defaults(func=cmd_pending)

    # Approve command
    approve_parser = subparsers.add_parser(
        "approve", help="Approve a pending user (bypass email confirmation)"
    )
    approve_parser.add_argument(
        "--email", help="Pending user's email address (will prompt if not provided)"
    )
    approve_parser.add_argument(
        "--admin", action="store_true", help="Grant admin privileges when approving"
    )
    approve_parser.set_defaults(func=cmd_approve)

    # Add command
    add_parser = subparsers.add_parser("add", help="Add a new user")
    add_parser.add_argument("--email", help="User's email address")
    add_parser.add_argument("--password", help="User's password (will prompt if not provided)")
    add_parser.add_argument("--admin", action="store_true", help="Make user an administrator")
    add_parser.set_defaults(func=cmd_add)

    # Delete command
    delete_parser = subparsers.add_parser("delete", help="Delete a user")
    delete_parser.add_argument("--email", help="Email of user to delete")
    delete_parser.add_argument(
        "--force", "-f", action="store_true", help="Skip confirmation prompt"
    )
    delete_parser.set_defaults(func=cmd_delete)

    # Reset password command
    reset_parser = subparsers.add_parser("reset-password", help="Reset a user's password")
    reset_parser.add_argument("--email", help="User's email address")
    reset_parser.add_argument("--password", help="New password (will prompt if not provided)")
    reset_parser.set_defaults(func=cmd_reset_password)

    # Set admin command
    setadmin_parser = subparsers.add_parser("setadmin", help="Grant admin privileges to a user")
    setadmin_parser.add_argument("--email", help="User's email address (will prompt if not provided)")
    setadmin_parser.set_defaults(func=cmd_setadmin)

    # Unset admin command
    unsetadmin_parser = subparsers.add_parser(
        "unsetadmin", help="Revoke admin privileges from a user"
    )
    unsetadmin_parser.add_argument("--email", help="User's email address (will prompt if not provided)")
    unsetadmin_parser.set_defaults(func=cmd_unsetadmin)

    return parser


async def main() -> int:
    """Main entry point."""
    parser = create_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # Load config from file if available
    config = load_config_from_file(args.config_file)

    # Apply config values as defaults if not specified on command line
    config_file_used = None
    if config:
        if args.config_file:
            config_file_used = args.config_file.resolve()
        else:
            config_file_used = (Path.cwd() / DEFAULT_CONFIG_FILE).resolve()

        if not args.mongodb_url and "mongodb_url" in config:
            args.mongodb_url = config["mongodb_url"]
        if not args.database and "database" in config:
            args.database = config["database"]

    # Check environment variables (from .env or shell)
    if not args.mongodb_url:
        args.mongodb_url = os.getenv("MONGODB_URL")
    if not args.database:
        args.database = os.getenv("MONGODB_DATABASE")

    # Apply final defaults if still not set
    if not args.mongodb_url:
        args.mongodb_url = DEFAULT_MONGODB_URL
    if not args.database:
        args.database = DEFAULT_DATABASE

    # Store config file path in args for use in confirmation prompts
    args._config_file_used = config_file_used

    # Display configuration info
    console.print()
    if config_file_used:
        print_info(f"Config file: [cyan]{config_file_used}[/cyan]")
    else:
        print_info(f"Config file: [dim]Not found (using defaults)[/dim]")
    print_info(f"Database:    [cyan]{args.database}[/cyan]")
    console.print()

    return await args.func(args)


def run() -> None:
    """Entry point for the script."""
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        console.print("\n[yellow]![/yellow] Interrupted.")
        sys.exit(130)  # Standard exit code for Ctrl-C


if __name__ == "__main__":
    run()
