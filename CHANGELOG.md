# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
