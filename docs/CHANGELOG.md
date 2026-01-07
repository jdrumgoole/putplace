# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.10.0] - 2026-01-07

### Removed

#### Full Name Field Elimination (putplace-server)
- **BREAKING: Full Name Field Removed**: Completely eliminated the full_name/Name field from all user management
  - Registration now requires only: Email, Password
  - Database no longer stores full_name in users or pending_users collections
  - UserCreate API model no longer accepts full_name parameter
  - pp_manage_users CLI tool no longer displays or accepts Name/full_name
  - All user operations simplified to use email as the sole identifier

### Changed

#### Database Schema
- `create_user()` - Removed `full_name` parameter
- `create_pending_user()` - Removed `full_name` parameter
- User documents now contain: email, username (=email), hashed_password, is_active, is_admin, created_at

#### API Changes
- `/api/register` endpoint - UserCreate model no longer accepts `full_name`
- Email confirmation workflow - No longer processes full_name
- OAuth registration - Simplified to use email only

#### CLI Tool (pp_manage_users)
- `list` command - Name column removed from output
- `pending` command - Name column removed from output
- `add` command - `--name` argument removed
- `approve` command - No longer displays full name
- `reset-password` command - No longer displays full name

#### Web UI
- Registration form - Full Name input field removed
- Cleaner, simpler registration experience

### Benefits
- Simplified user model: email is the universal identifier
- Reduced database storage and memory footprint
- Cleaner API surface with fewer optional fields
- Consistent with email-as-identity pattern used throughout the application
- Less confusion about which name field to use

### Migration Notes
- **No database migration required** - full_name was optional and not used in core functionality
- Existing users with full_name data will retain it in the database (not deleted)
- New users will not have full_name field created
- API clients should remove full_name from registration payloads (will be ignored if sent)

## [0.9.1] - 2026-01-07

### Changed

#### Registration Simplification (putplace-server)
- **Username Field Removed**: Email now serves as both email and username throughout the application
  - Registration page simplified - no longer asks for separate username
  - Users register with: Email, Password, Full Name (optional)
  - Backend automatically uses email as username in database
  - Login continues to use email and password
  - No migration needed - backend was already using email as username internally

### Benefits
- Clearer user experience - one less field to fill out
- Eliminates confusion between email and username
- Consistent with modern web application patterns

## [0.2.2] - 2026-01-07

### Changed

#### Web UI Enhancement (putplace-assist)
- **Three-Component Architecture Display**: Updated daemon web UI to fully represent the queue-based architecture
  - Replaced 4-card stats layout with 3-group component view matching Electron GUI
  - **File Statistics**: Files Tracked, Paths Watched
  - **Processing Queue**: Scanner→SHA256, SHA256→Upload, In Progress (with pipeline visualization)
  - **Today's Activity**: Completed uploads, Failed uploads
  - Real-time component status indicators:
    - ● (green) = Component actively running
    - ○ (gray) = Component inactive
  - Shows Scanner (watcher_active) and SHA256 Processor (sha256_processor_active) status
  - Color-coded statistics: green (success/active), orange (pending), red (errors)
  - Responsive design (stacks to single column on mobile)
  - Web UI accessible at `http://localhost:8765/ui`

### Technical Details
- Enhanced `loadStats()` JavaScript function to fetch from 3 endpoints:
  - `/status` - component status and uptime
  - `/files/stats` - file counts and sizes
  - `/uploads/queue` - in_progress, completed_today, failed_today
- Added CSS for component status indicators and color-coded values
- UI now matches Electron GUI (v1.0.16) in displaying full three-component model

## [0.2.1] - 2026-01-06

### Added

#### Merged putplace-client into putplace-assist
- **Unified Client Package**: `pp_client` CLI tool now included in putplace-assist
  - No longer need to install separate `putplace-client` package
  - All client-side tools (daemon + CLI) available in single package
  - `pp_client` command available after installing `putplace-assist`
  - Backwards compatible - existing `pp_client` users can switch seamlessly

### Changed
- **Package Consolidation**: putplace-client functionality merged into putplace-assist
  - Install: `pip install putplace-assist` gives you both `pp_assist` and `pp_client`
  - Simplifies client deployment - one package for all client-side operations

### Deprecated
- **putplace-client package** - Use putplace-assist instead
  - The standalone `putplace-client` package (v0.8.4) is now deprecated
  - New installations should use `putplace-assist` which includes `pp_client`
  - Existing users: `pip uninstall putplace-client && pip install putplace-assist`

## [0.9.0] - 2026-01-06

### Added

#### Admin Dashboard (putplace-server)
- **Complete Admin Dashboard**: New `/admin/dashboard` endpoint with professional UI
  - Real-time statistics: Total Users, Active Users, Admin Users, Pending Registrations, Total Files, Files with Content
  - User management table showing all registered users with file upload counts
  - Pending registrations table for email confirmation tracking
  - Secure admin-only access with proper authentication and authorization
  - Modern gradient design with responsive layout

#### 3-Component Queue Architecture (putplace-assist v0.2.0)
- **Component 1 - Scanner**: Directory scanning with file discovery and change detection
  - Detects new files, modified files (by mtime), and unchanged files
  - Queues new/modified files to `queue_pending_checksum` for processing
  - Uses persistent SQLite `files` table for state tracking

- **Component 2 - SHA256 Processor**: Background checksum calculation
  - Processes files from `queue_pending_checksum` queue (FIFO)
  - Implements rate-limited SHA256 calculation to avoid CPU saturation
  - Detects duplicate checksums and skips unnecessary uploads
  - Queues changed files to `queue_pending_upload`
  - Configurable retry logic with exponential backoff

- **Component 3 - Uploader**: Chunked upload manager
  - Processes files from `queue_pending_upload` queue (FIFO)
  - 2MB chunk size for efficient large file uploads
  - Parallel upload support (configurable concurrency)
  - Handles deletion notifications via `queue_pending_deletion`
  - Proper error handling and retry mechanisms

### Changed

#### Server Refactoring (putplace-server)
- **Router Organization**: Completed main.py refactoring (3,682 → 430 lines, 88% reduction)
  - `routers/admin.py`: Admin dashboard endpoints
  - `routers/files.py`: File operations endpoints
  - `routers/uploads.py`: Chunked upload protocol
  - `routers/users.py`: User authentication and management
  - `routers/api_keys.py`: API key management
  - `routers/pages.py`: HTML page rendering
  - `dependencies.py`: Centralized dependency injection (no circular imports)

#### Database Schema (putplace-assist)
- **New Queue Tables**: Persistent FIFO queues for 3-component architecture
  - `queue_pending_checksum`: Files awaiting SHA256 calculation
  - `queue_pending_upload`: Files ready for upload
  - `queue_pending_deletion`: Deletion notifications

- **Files Table**: Central file tracking with state machine
  - Status flow: `discovered` → `ready_for_upload` → `completed`
  - Tracks file metadata, checksums, and modification times
  - Enables change detection and duplicate prevention

### Fixed
- **Test Suite**: All unit tests passing (245/245 server, 36/36 assist)
  - Fixed model imports after FileInfo removal
  - Updated database tests for new queue-based API
  - Fixed `get_file_stats()` to query new files table
  - All admin dashboard authentication tests passing

### Removed
- **Legacy Monthly Tables**: Replaced filelog_YYYYMM pattern with queue-based architecture
- **Deprecated Models**: Removed FileInfo and related monthly table models

## [0.8.11] - 2025-12-14

### Security

#### Critical Path Traversal Fix
- **SHA256 Validation**: Fixed critical path traversal vulnerability in file metadata validation
  - Added regex pattern validation to SHA256 field: `^[a-f0-9]{64}$`
  - Previously only validated length (64 chars), allowing malicious inputs like `../../etc/passwd`
  - Now requires exactly 64 lowercase hexadecimal characters
  - Prevents directory traversal attacks via crafted SHA256 values
  - Added comprehensive test coverage for invalid patterns

#### HTTP Security Headers
- **Security Middleware**: Added comprehensive HTTP security headers to all responses
  - `X-Frame-Options: DENY` - Prevents clickjacking attacks
  - `X-Content-Type-Options: nosniff` - Prevents MIME type sniffing
  - `X-XSS-Protection: 1; mode=block` - Legacy XSS protection
  - `Content-Security-Policy` - Restricts resource loading and execution
  - `Referrer-Policy: strict-origin-when-cross-origin` - Prevents URL information leakage
  - `Permissions-Policy` - Restricts dangerous browser features (geolocation, camera, microphone, etc.)

### Added

#### CORS Configuration
- **Configuration Wizard Enhancement**: Added CORS settings to `putplace_configure.py`
  - New `--cors-allow-origins` argument for comma-separated origins or wildcard `*`
  - New `--cors-allow-credentials` argument (default: true)
  - Generates `[cors]` section in `ppserver.toml` configuration file
  - Simplifies production deployment with proper origin restrictions

### Changed
- **Security Audit**: Completed comprehensive security review
  - ✅ NoSQL Injection: SAFE - All queries use proper field matching
  - ✅ XSS Protection: SAFE - All user data escaped via `escapeHtml()`
  - ✅ Path Traversal: FIXED - SHA256 pattern validation
  - ✅ CORS Configuration: ENHANCED - Configurable via wizard
  - ✅ Security Headers: FIXED - Comprehensive middleware
  - ✅ Secrets in Logs: SAFE - No user credentials logged

## [0.8.9] - 2025-12-06

### Fixed

#### Electron Client Stability
- **Large File Upload Crash Fix**: Fixed crashes during large file uploads (multi-GB files)
  - Added global error handlers (`uncaughtException`, `unhandledRejection`) to prevent app crashes
  - Added `event.sender.isDestroyed()` check before sending IPC progress updates
  - Implemented stream backpressure handling with pause/resume for file uploads
  - Properly positioned request error handlers to clean up file streams on errors
  - App now remains stable when uploading files of any size

### Added

#### Electron Client Testing
- **Playwright E2E Test Suite**: Comprehensive automated tests for the Electron client
  - Tests login form display, authentication, directory selection, file upload, and logout
  - Invalid credentials error handling test
  - Crash detection during uploads
  - Support for large file uploads with progress monitoring
  - Uses `DEV_TEST_USER` and `DEV_TEST_PASSWORD` from `.env` file
  - Run with: `npm run test` or `npm run test:headed`

### Changed
- **Test Configuration**: Added Playwright dependencies and test scripts to `package.json`
  - `@playwright/test`, `dotenv`, `@types/dotenv` added to devDependencies
  - New npm scripts: `test`, `test:headed`, `test:debug`, `test:report`

### Refactored
- **Server Code Organization**: Extracted routes and templates for better maintainability
  - Created `routers/` module with separate files for `api_keys`, `files`, `pages`, `users`, `admin`
  - Moved HTML templates to `templates.py` module
  - Reduced `main.py` size by ~1100 lines

## [0.5.1] - 2025-01-06

### Fixed
- **Configuration Priority**: Fixed critical bug where `ppserver.toml` values were overriding environment variables
  - Environment variables now correctly take precedence over TOML configuration
  - Proper priority order: env vars > TOML > defaults
  - Rewrote `Settings.__init__()` to check environment variables first
  - Fixes issues with test environments and containerized deployments
- **Server Startup**: Fixed `UnboundLocalError` crash caused by local `os` import after usage
  - Moved `import os` to module-level imports in `main.py`
- **E2E Test Suite**: Fixed and re-enabled `test_e2e_real_server_and_client_with_upload`
  - Corrected storage path assumptions to match actual storage backend structure
  - Test now passes successfully in isolation
  - Storage backend uses single-level subdirectory: `storage/XX/SHA256` (not `storage/XX/XX/SHA256`)

### Changed
- Updated configuration loading in `config.py` to properly respect environment variable precedence
- Cleaned up redundant local imports in `main.py`

## [0.5.0] - 2025-11-05

### Added

#### Electron Desktop GUI
- **Cross-Platform Desktop Application**: New Electron-based GUI client built with TypeScript
  - Native macOS, Windows, and Linux support
  - Proper application branding with "PutPlace Client" menu name
  - Custom application menu with standard macOS items
  - Packaged .app bundle with correct Info.plist metadata
  - DMG installer for easy distribution

- **Authentication & Security**:
  - JWT-based authentication (replaced API key authentication)
  - User login and registration forms
  - Password visibility toggle with eye icon
  - Session persistence using localStorage
  - Secure IPC communication with context isolation

- **User Interface Features**:
  - Native directory picker dialog
  - Exclude patterns manager with wildcard support
  - Real-time progress tracking with statistics
  - Color-coded log output (success, error, warning, info)
  - System information display (hostname, IP address)
  - Settings persistence between sessions

- **Build & Development Tools**:
  - `invoke gui-electron` - Launch packaged app (recommended)
  - `invoke gui-electron-package` - Package app into .app bundle and DMG
  - `invoke gui-electron-build` - Build TypeScript source
  - `invoke gui-electron-test-install` - Semi-automated installation testing
    - Automated mode (`--automated` flag) for CI/CD
    - Automatic app quit after testing
    - Full cleanup of app data and preferences

- **Documentation**:
  - Updated README with Electron GUI usage
  - Added installation and testing instructions
  - Documented new invoke tasks

### Changed
- **GUI Client**: Replaced Kivy GUI with Electron + TypeScript implementation
  - Better cross-platform support
  - More native look and feel
  - Easier to maintain and extend
  - Modern web technologies (HTML, CSS, TypeScript)

### Technical
- Electron application structure:
  - `src/main.ts` - Main process with IPC handlers
  - `src/preload.ts` - Secure IPC bridge
  - `src/renderer/` - UI components (HTML, CSS, TypeScript)
- electron-builder configuration for packaging
- TypeScript compilation with strict type checking
- Automated testing with installation/uninstallation verification

## [0.4.2] - 2025-10-30

### Changed
- **License**: Changed from MIT to Apache License 2.0
- **Project Description**: Updated to "File and Metadata storage system"
- **Documentation**: Added Apache 2.0 license badge to README

## [0.4.1] - 2025-10-30

### Fixed
- **Documentation Code Examples**: Corrected all code examples in documentation to use actual API field names
  - Fixed incorrect field names: `size` → `file_size`, `permissions` → `file_mode`, `owner` → `file_uid`, `group` → `file_gid`
  - Fixed timestamp format: ISO 8601 strings → Unix timestamps (float)
  - Fixed async/await syntax in test examples
  - Affected files: `docs/development.md`, `docs/api-reference.md`, `docs/troubleshooting.md`
- **Test Infrastructure**: Fixed parallel test execution race conditions
  - Switched from global variable modification to FastAPI dependency overrides
  - Added per-worker database isolation for thread-safe parallel testing
  - Fixed `test_e2e_duplicate_files_different_hosts` intermittent failure
- **Server Management**: Fixed ppserver restart reliability
  - Added port availability checking with 10-second timeout
  - Prevents "address already in use" errors during restart
  - Fixed `test_ppserver_restart` test failure

### Changed
- **Authentication System**: Refactored to use dependency injection
  - Added `get_auth_db()` helper function for database dependency
  - Updated `get_current_api_key()` and `get_optional_api_key()` to use proper dependency injection
  - Improves testability and thread-safety for parallel test execution

## [0.4.0] - 2025-01-17

### Added

#### Web Interface Enhancements
- **File Cloning Detection**: Added clone button next to info button for files with identical SHA256 hashes
  - Shows count of duplicate files in user's collection
  - Displays all clones across all users (cross-user clone detection)
  - Modal with detailed table showing hostname, filepath, size, and status
  - Special handling for zero-length files (shows "0" disabled button)
  - Non-zero files always have active clone button for discovering epoch files

#### Epoch File Management
- **Epoch File Highlighting**: First uploaded file with content (epoch file) is visually distinguished
  - Green background highlighting (#d4edda)
  - Green left border (4px) and bottom border (2px)
  - Green "EPOCH" badge for clear identification
  - Automatic sorting: epoch file first, then metadata-only files
  - Cross-user epoch file linking: metadata files can now link to epoch files uploaded by other users

#### Visual Improvements
- **Zero-Length File Indicators**: Special icon (📭) for empty files
- **Improved Modal Layout**:
  - Increased modal width from 700px to 1200px for better visibility
  - Added scrolling support for long file lists
  - Fixed table layout with proper column widths
  - Word wrapping for long file paths
  - Responsive design with max-height constraints

#### Client Improvements
- **Graceful Interrupt Handling**: ppclient now handles Ctrl-C cleanly
  - Finishes processing current file before exiting
  - Displays partial completion status
  - Shows count of remaining unprocessed files
  - Second Ctrl-C forces immediate termination
  - Proper exit codes for automation/scripting

### Changed
- Clone detection now queries all files across all users, not just current user's files
- Clone button is now always active for non-zero-length files (removed disabled state for single files)
- Modal content area now uses flexbox layout for better scrolling behavior

### Technical
- Added new API endpoint: `GET /api/clones/{sha256}` - Retrieve all files with identical SHA256 across all users
- Added new database method: `get_files_by_sha256()` - Query files by SHA256 hash with epoch file sorting
- Added signal handling (SIGINT) to ppclient for graceful shutdown
- Improved CSS styling for modal dialogs and table layouts

## [0.3.0] - Previous Release

### Features
- File metadata storage with SHA256 hashing
- User authentication with JWT tokens
- API key management via web interface
- Multiple storage backends (local filesystem, AWS S3)
- Web-based file browser with tree layout
- File details modal with comprehensive metadata
- TOML-based configuration
- MongoDB database integration
- Comprehensive test suite (115+ tests)

---

**Note**: This is the first release with a formal changelog. Previous changes are summarized under version 0.3.0.
