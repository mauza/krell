**Status:** Implemented (2025-12-29)

# Admin Authentication Design

## Overview

Add password protection to the dashboard and admin API endpoints. The admin password is set on first visit and stored as a bcrypt hash in the database.

## Scope

**Protected:**
- `/dashboard` and all `/dashboard/*` routes
- `/api/admin/*` endpoints

**Unprotected (no change):**
- `/api/chat`, `/api/conversations/*`, etc.
- WebSocket endpoints
- Health check endpoints

## Data Storage

Use existing `settings` table with these keys:
- `admin_password_hash` - bcrypt hash of admin password
- `admin_session_token` - current valid session token
- `admin_session_expires` - timestamp when session expires

No new database tables required.

## First-Visit Setup Flow

1. User visits `/dashboard`
2. Check if `admin_password_hash` exists in settings
3. If no password exists, redirect to `/dashboard/setup`
4. Setup page shows form with:
   - Password field
   - Confirm password field
   - Submit button
5. On submit:
   - Validate passwords match
   - Hash with bcrypt
   - Store hash in settings
   - Redirect to `/dashboard/login`

## Login Flow

**Login page (`/dashboard/login`):**
- Password field (no username - single admin)
- Submit button

**On successful login:**
- Generate secure random session token (32 bytes, hex encoded)
- Store token and expiry (7 days from now) in settings
- Set HTTP-only cookie `krell_session` with token, 7-day expiry
- Redirect to `/dashboard`

**On failed login:**
- Show error message
- Stay on login page

## Session Validation

On each request to protected routes:
1. Check for `krell_session` cookie
2. Compare token against `admin_session_token` in settings
3. Check `admin_session_expires` hasn't passed
4. If invalid or expired:
   - HTML routes: redirect to `/dashboard/login`
   - API routes: return 401 JSON response

## Logout

`GET /dashboard/logout`:
1. Clear `admin_session_token` and `admin_session_expires` from settings
2. Clear `krell_session` cookie
3. Redirect to `/dashboard/login`

## Implementation Details

**Dependencies:**
- `bcrypt` - password hashing

**New files:**
- `templates/login.html` - login form
- `templates/setup.html` - password setup form

**Modified files:**
- `main.py` - add auth routes and middleware
- `database/db.py` - add helper methods for auth (optional, can use existing get/set_setting)
- `templates/dashboard.html` - add logout button

**Auth dependency function:**
```python
async def require_admin_auth(request: Request):
    token = request.cookies.get("krell_session")
    if not token:
        # redirect or 401
    stored_token = await database.get_setting("admin_session_token")
    expires = await database.get_setting("admin_session_expires")
    if token != stored_token or datetime.now() > datetime.fromisoformat(expires):
        # redirect or 401
```

## UI

**Setup page (`/dashboard/setup`):**
- Centered card with form
- "Set Admin Password" header
- Password + confirm fields
- Submit button
- Use existing Tailwind styling

**Login page (`/dashboard/login`):**
- Centered card with form
- "Krell Dashboard Login" header
- Password field
- Submit button
- Error message area

**Dashboard change:**
- Add "Logout" link/button in header area

## Future Considerations

User authentication for API access will be designed separately. This admin auth is specifically for dashboard/admin protection.
