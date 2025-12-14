# User Management

This guide covers managing users in PutPlace using the `pp_manage_users` command-line tool.

## Overview

PutPlace uses MongoDB to store user accounts. Users can be:
- **Active users** - Can log in and use the system
- **Pending users** - Registered but awaiting email confirmation
- **Admin users** - Have administrative privileges

## Installation

The `pp_manage_users` command is installed as part of the `putplace-server` package:

```bash
# Run directly
pp_manage_users --help

# Or via uv
uv run pp_manage_users --help
```

## Quick Reference

| Command | Description |
|---------|-------------|
| `pp_manage_users list` | List all active users |
| `pp_manage_users pending` | List users awaiting email confirmation |
| `pp_manage_users add` | Create a new user |
| `pp_manage_users approve` | Approve a pending user |
| `pp_manage_users delete` | Delete a user |
| `pp_manage_users reset-password` | Reset a user's password |
| `pp_manage_users setadmin` | Grant admin privileges |
| `pp_manage_users unsetadmin` | Revoke admin privileges |

## Commands

### List Users

List all active users in the database:

```bash
# Rich table output (default)
pp_manage_users list

# Plain text output (for scripting)
pp_manage_users list --no-table
```

Example output:
```
┏━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━┳━━━━━━━┳━━━━━━━━┳━━━━━━━━━━━━━━━━━━┓
┃ Email                 ┃ Name         ┃ Admin ┃ Active ┃ Created          ┃
┡━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━╇━━━━━━━╇━━━━━━━━╇━━━━━━━━━━━━━━━━━━┩
│ admin@example.com     │ Administrator│  Yes  │  Yes   │ 2024-01-15 10:30 │
│ user@example.com      │ John Doe     │  No   │  Yes   │ 2024-01-16 14:22 │
└───────────────────────┴──────────────┴───────┴────────┴──────────────────┘
```

### List Pending Users

Show users who have registered but not yet confirmed their email:

```bash
pp_manage_users pending
```

Pending users have an expiration time. Expired registrations can be cleaned up or manually approved.

### Add a New User

Create a user directly (bypassing email confirmation):

```bash
# Interactive mode (prompts for all values)
pp_manage_users add

# With command-line arguments
pp_manage_users add --email user@example.com --password secret123

# With full name
pp_manage_users add --email user@example.com --password secret123 --name "John Doe"

# Create an admin user
pp_manage_users add --email admin@example.com --password secret123 --admin
```

Password requirements:
- Minimum 8 characters

### Approve Pending Users

Approve a user who registered but hasn't confirmed their email:

```bash
# Interactive mode (shows available pending users)
pp_manage_users approve

# Approve specific user
pp_manage_users approve --email user@example.com

# Approve and grant admin privileges
pp_manage_users approve --email user@example.com --admin
```

This moves the user from the `pending_users` collection to the `users` collection.

### Delete a User

Remove a user from the system:

```bash
# Interactive mode (shows users and confirms)
pp_manage_users delete

# Delete specific user
pp_manage_users delete --email user@example.com

# Skip confirmation prompt
pp_manage_users delete --email user@example.com --force
```

### Reset Password

Change a user's password:

```bash
# Interactive mode (prompts for new password)
pp_manage_users reset-password

# With command-line arguments
pp_manage_users reset-password --email user@example.com --password newpass123
```

### Manage Admin Privileges

Grant admin privileges:

```bash
pp_manage_users setadmin --email user@example.com
```

Revoke admin privileges:

```bash
pp_manage_users unsetadmin --email admin@example.com
```

## Global Options

These options apply to all commands:

```bash
# Use a custom MongoDB URL
pp_manage_users --mongodb-url mongodb://host:27017 list

# Use a different database
pp_manage_users --database putplace_prod list

# Combine options
pp_manage_users --mongodb-url mongodb://prod-host:27017 --database putplace_prod list
```

Default values:
- `--mongodb-url`: `mongodb://localhost:27017`
- `--database`: `putplace`

## User Lifecycle

```
┌─────────────────┐
│   Registration  │
│   (via API)     │
└────────┬────────┘
         │
         ▼
┌─────────────────┐     ┌─────────────────┐
│  Pending User   │────▶│  Email Sent     │
│  (pending_users)│     │  (confirmation) │
└────────┬────────┘     └─────────────────┘
         │
         │ Email confirmed OR
         │ pp_manage_users approve
         ▼
┌─────────────────┐
│  Active User    │
│  (users)        │
└────────┬────────┘
         │
         │ pp_manage_users setadmin
         ▼
┌─────────────────┐
│  Admin User     │
│  (is_admin=true)│
└─────────────────┘
```

## Database Collections

PutPlace stores users in two MongoDB collections:

### `users` Collection

Active, confirmed users:

```json
{
  "_id": "ObjectId",
  "email": "user@example.com",
  "username": "user@example.com",
  "hashed_password": "bcrypt hash",
  "full_name": "John Doe",
  "is_active": true,
  "is_admin": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

### `pending_users` Collection

Users awaiting email confirmation:

```json
{
  "_id": "ObjectId",
  "email": "newuser@example.com",
  "hashed_password": "bcrypt hash",
  "full_name": "Jane Smith",
  "confirmation_token": "random-token",
  "created_at": "2024-01-16T14:00:00Z",
  "expires_at": "2024-01-17T14:00:00Z"
}
```

## Scripting Examples

### Backup user list

```bash
pp_manage_users list --no-table > users_backup.txt
```

### Check if user exists

```bash
if pp_manage_users list --no-table | grep -q "user@example.com"; then
    echo "User exists"
fi
```

### Bulk user creation

```bash
#!/bin/bash
while IFS=, read -r email name password; do
    pp_manage_users add --email "$email" --name "$name" --password "$password"
done < users.csv
```

## Troubleshooting

### Cannot connect to MongoDB

```
✗ Could not connect to MongoDB: ...
```

Check that:
1. MongoDB is running: `invoke mongo-status`
2. The connection URL is correct
3. Network connectivity to the MongoDB host

### User already exists

```
✗ User with email 'user@example.com' already exists.
```

The email is already registered. Use `reset-password` to change credentials or `delete` to remove.

### Password too short

```
✗ Password must be at least 8 characters long.
```

Provide a password with at least 8 characters.

## See Also

- [Authentication](AUTHENTICATION.md) - Authentication system overview
- [Configuration](configuration.md) - Server configuration
- [API Reference](api-reference.md) - REST API endpoints for user management
