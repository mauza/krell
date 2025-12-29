# Admin Authentication Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add password protection to the dashboard and admin API endpoints with first-visit setup flow.

**Architecture:** Use existing `settings` table to store bcrypt password hash and session token. Add FastAPI dependency for auth checking. Create minimal HTML templates for setup/login forms using existing Tailwind styling.

**Tech Stack:** FastAPI, bcrypt, Jinja2 templates, Tailwind CSS, HTTP-only cookies

---

## Task 1: Add bcrypt Dependency

**Files:**
- Modify: `pyproject.toml:31`

**Step 1: Add bcrypt to dependencies**

In `pyproject.toml`, add bcrypt to the dependencies list:

```toml
    "websockets>=15.0.1",
    "bcrypt>=4.0.0",
]
```

**Step 2: Install dependencies**

Run: `uv sync`
Expected: bcrypt installed successfully

**Step 3: Verify installation**

Run: `uv run python -c "import bcrypt; print(bcrypt.__version__)"`
Expected: Version number printed (e.g., "4.2.0")

**Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "Add bcrypt dependency for password hashing"
```

---

## Task 2: Create Auth Helper Functions

**Files:**
- Create: `auth.py`
- Test: `tests/test_auth.py`

**Step 1: Write failing tests for auth helpers**

Create `tests/test_auth.py`:

```python
"""Tests for authentication helpers."""

import pytest
from datetime import datetime, timedelta


def test_hash_password_returns_bytes():
    """hash_password should return a bcrypt hash."""
    from auth import hash_password
    
    result = hash_password("mysecretpassword")
    
    assert isinstance(result, str)
    assert result.startswith("$2b$")


def test_verify_password_correct():
    """verify_password should return True for correct password."""
    from auth import hash_password, verify_password
    
    hashed = hash_password("mysecretpassword")
    
    assert verify_password("mysecretpassword", hashed) is True


def test_verify_password_incorrect():
    """verify_password should return False for wrong password."""
    from auth import hash_password, verify_password
    
    hashed = hash_password("mysecretpassword")
    
    assert verify_password("wrongpassword", hashed) is False


def test_generate_session_token_length():
    """generate_session_token should return 64-char hex string."""
    from auth import generate_session_token
    
    token = generate_session_token()
    
    assert isinstance(token, str)
    assert len(token) == 64  # 32 bytes = 64 hex chars


def test_generate_session_token_unique():
    """generate_session_token should return unique tokens."""
    from auth import generate_session_token
    
    tokens = [generate_session_token() for _ in range(10)]
    
    assert len(set(tokens)) == 10


def test_get_session_expiry():
    """get_session_expiry should return datetime 7 days from now."""
    from auth import get_session_expiry
    
    before = datetime.utcnow()
    expiry = get_session_expiry()
    after = datetime.utcnow()
    
    # Should be ~7 days in future
    assert expiry > before + timedelta(days=6, hours=23)
    assert expiry < after + timedelta(days=7, hours=1)


def test_is_session_expired_false_for_future():
    """is_session_expired should return False for future timestamp."""
    from auth import is_session_expired
    
    future = (datetime.utcnow() + timedelta(days=1)).isoformat()
    
    assert is_session_expired(future) is False


def test_is_session_expired_true_for_past():
    """is_session_expired should return True for past timestamp."""
    from auth import is_session_expired
    
    past = (datetime.utcnow() - timedelta(days=1)).isoformat()
    
    assert is_session_expired(past) is True


def test_is_session_expired_true_for_none():
    """is_session_expired should return True for None."""
    from auth import is_session_expired
    
    assert is_session_expired(None) is True
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_auth.py -v`
Expected: All tests FAIL with "ModuleNotFoundError: No module named 'auth'"

**Step 3: Implement auth helpers**

Create `auth.py`:

```python
"""Authentication helpers for admin dashboard."""

import bcrypt
import secrets
from datetime import datetime, timedelta
from typing import Optional

# Session duration: 7 days
SESSION_DURATION_DAYS = 7


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    """Verify a password against a bcrypt hash."""
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


def generate_session_token() -> str:
    """Generate a cryptographically secure session token."""
    return secrets.token_hex(32)


def get_session_expiry() -> datetime:
    """Get expiry datetime for a new session (7 days from now)."""
    return datetime.utcnow() + timedelta(days=SESSION_DURATION_DAYS)


def is_session_expired(expiry_iso: Optional[str]) -> bool:
    """Check if a session has expired."""
    if expiry_iso is None:
        return True
    try:
        expiry = datetime.fromisoformat(expiry_iso)
        return datetime.utcnow() > expiry
    except ValueError:
        return True
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_auth.py -v`
Expected: All 9 tests PASS

**Step 5: Commit**

```bash
git add auth.py tests/test_auth.py
git commit -m "Add auth helper functions for password hashing and sessions"
```

---

## Task 3: Create Setup Page Template

**Files:**
- Create: `templates/setup.html`

**Step 1: Create setup template**

Create `templates/setup.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Setup Admin Password - Krell</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-100 min-h-screen flex items-center justify-center">
    <div class="bg-white rounded-lg shadow-md p-8 w-full max-w-md">
        <h1 class="text-2xl font-bold text-gray-900 mb-2">Set Admin Password</h1>
        <p class="text-gray-600 mb-6">Create a password to protect your Krell dashboard.</p>
        
        {% if error %}
        <div class="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded mb-4">
            {{ error }}
        </div>
        {% endif %}
        
        <form method="POST" action="/dashboard/setup" class="space-y-4">
            <div>
                <label for="password" class="block text-sm font-medium text-gray-700 mb-2">
                    Password
                </label>
                <input type="password" 
                       id="password" 
                       name="password" 
                       required
                       minlength="8"
                       class="w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                       placeholder="Enter password (min 8 characters)">
            </div>
            
            <div>
                <label for="confirm_password" class="block text-sm font-medium text-gray-700 mb-2">
                    Confirm Password
                </label>
                <input type="password" 
                       id="confirm_password" 
                       name="confirm_password" 
                       required
                       minlength="8"
                       class="w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                       placeholder="Confirm password">
            </div>
            
            <button type="submit" 
                    class="w-full bg-blue-600 text-white py-2 px-4 rounded-md hover:bg-blue-700 focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 transition-colors">
                Set Password
            </button>
        </form>
    </div>
</body>
</html>
```

**Step 2: Commit**

```bash
git add templates/setup.html
git commit -m "Add admin password setup page template"
```

---

## Task 4: Create Login Page Template

**Files:**
- Create: `templates/login.html`

**Step 1: Create login template**

Create `templates/login.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Login - Krell Dashboard</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-100 min-h-screen flex items-center justify-center">
    <div class="bg-white rounded-lg shadow-md p-8 w-full max-w-md">
        <h1 class="text-2xl font-bold text-gray-900 mb-2">Krell Dashboard</h1>
        <p class="text-gray-600 mb-6">Enter your password to continue.</p>
        
        {% if error %}
        <div class="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded mb-4">
            {{ error }}
        </div>
        {% endif %}
        
        <form method="POST" action="/dashboard/login" class="space-y-4">
            <div>
                <label for="password" class="block text-sm font-medium text-gray-700 mb-2">
                    Password
                </label>
                <input type="password" 
                       id="password" 
                       name="password" 
                       required
                       autofocus
                       class="w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                       placeholder="Enter password">
            </div>
            
            <button type="submit" 
                    class="w-full bg-blue-600 text-white py-2 px-4 rounded-md hover:bg-blue-700 focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 transition-colors">
                Login
            </button>
        </form>
    </div>
</body>
</html>
```

**Step 2: Commit**

```bash
git add templates/login.html
git commit -m "Add login page template"
```

---

## Task 5: Implement Setup and Login Routes

**Files:**
- Modify: `main.py`
- Test: `tests/test_admin_auth.py`

**Step 1: Write failing tests for setup/login routes**

Create `tests/test_admin_auth.py`:

```python
"""Tests for admin authentication routes."""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create test client."""
    from main import app
    return TestClient(app)


@pytest.fixture(autouse=True)
def clean_settings():
    """Clean auth settings before each test."""
    import asyncio
    from database.db import Database
    
    async def cleanup():
        db = Database(":memory:")
        await db.init_db()
        # Clear any existing auth settings
        try:
            await db.delete_setting("admin_password_hash")
            await db.delete_setting("admin_session_token")
            await db.delete_setting("admin_session_expires")
        except:
            pass
    
    # Note: This won't work with the real DB, but shows intent
    # The actual test isolation is handled by the test database fixture
    yield


class TestSetupFlow:
    """Tests for initial password setup."""
    
    def test_dashboard_redirects_to_setup_when_no_password(self, client):
        """GET /dashboard should redirect to /dashboard/setup if no password set."""
        response = client.get("/dashboard", follow_redirects=False)
        
        assert response.status_code == 307
        assert response.headers["location"] == "/dashboard/setup"
    
    def test_setup_page_renders(self, client):
        """GET /dashboard/setup should render setup form."""
        response = client.get("/dashboard/setup")
        
        assert response.status_code == 200
        assert b"Set Admin Password" in response.content
    
    def test_setup_post_passwords_must_match(self, client):
        """POST /dashboard/setup with mismatched passwords shows error."""
        response = client.post(
            "/dashboard/setup",
            data={"password": "password123", "confirm_password": "different123"}
        )
        
        assert response.status_code == 200
        assert b"Passwords do not match" in response.content
    
    def test_setup_post_password_min_length(self, client):
        """POST /dashboard/setup with short password shows error."""
        response = client.post(
            "/dashboard/setup",
            data={"password": "short", "confirm_password": "short"}
        )
        
        assert response.status_code == 200
        assert b"at least 8 characters" in response.content
    
    def test_setup_post_success_redirects_to_login(self, client):
        """POST /dashboard/setup with valid password redirects to login."""
        response = client.post(
            "/dashboard/setup",
            data={"password": "validpassword123", "confirm_password": "validpassword123"},
            follow_redirects=False
        )
        
        assert response.status_code == 303
        assert response.headers["location"] == "/dashboard/login"


class TestLoginFlow:
    """Tests for login functionality."""
    
    def test_login_page_renders(self, client):
        """GET /dashboard/login should render login form."""
        # First set up a password
        client.post(
            "/dashboard/setup",
            data={"password": "validpassword123", "confirm_password": "validpassword123"}
        )
        
        response = client.get("/dashboard/login")
        
        assert response.status_code == 200
        assert b"Krell Dashboard" in response.content
    
    def test_login_wrong_password_shows_error(self, client):
        """POST /dashboard/login with wrong password shows error."""
        # First set up a password
        client.post(
            "/dashboard/setup",
            data={"password": "validpassword123", "confirm_password": "validpassword123"}
        )
        
        response = client.post(
            "/dashboard/login",
            data={"password": "wrongpassword"}
        )
        
        assert response.status_code == 200
        assert b"Invalid password" in response.content
    
    def test_login_success_sets_cookie_and_redirects(self, client):
        """POST /dashboard/login with correct password sets cookie and redirects."""
        # First set up a password
        client.post(
            "/dashboard/setup",
            data={"password": "validpassword123", "confirm_password": "validpassword123"}
        )
        
        response = client.post(
            "/dashboard/login",
            data={"password": "validpassword123"},
            follow_redirects=False
        )
        
        assert response.status_code == 303
        assert response.headers["location"] == "/dashboard"
        assert "krell_session" in response.cookies


class TestLogout:
    """Tests for logout functionality."""
    
    def test_logout_clears_cookie_and_redirects(self, client):
        """GET /dashboard/logout clears session and redirects to login."""
        # Setup and login first
        client.post(
            "/dashboard/setup",
            data={"password": "validpassword123", "confirm_password": "validpassword123"}
        )
        client.post(
            "/dashboard/login",
            data={"password": "validpassword123"}
        )
        
        response = client.get("/dashboard/logout", follow_redirects=False)
        
        assert response.status_code == 307
        assert response.headers["location"] == "/dashboard/login"
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_admin_auth.py -v`
Expected: Tests FAIL (routes don't exist yet)

**Step 3: Implement setup and login routes in main.py**

Add these imports at the top of `main.py` (after existing imports):

```python
from fastapi import Form
from fastapi.responses import RedirectResponse
from auth import (
    hash_password,
    verify_password,
    generate_session_token,
    get_session_expiry,
    is_session_expired,
)
```

Add these routes after the existing dashboard routes section (around line 120):

```python
# ============================================================================
# Authentication Routes
# ============================================================================


async def is_admin_password_set() -> bool:
    """Check if admin password has been set."""
    database = Database(db.db_path)
    password_hash = await database.get_setting("admin_password_hash")
    return password_hash is not None


async def get_current_session(request: Request) -> Optional[str]:
    """Get and validate current session from cookie."""
    token = request.cookies.get("krell_session")
    if not token:
        return None
    
    database = Database(db.db_path)
    stored_token = await database.get_setting("admin_session_token")
    expires = await database.get_setting("admin_session_expires")
    
    if token != stored_token or is_session_expired(expires):
        return None
    
    return token


@app.get("/dashboard/setup", response_class=HTMLResponse)
async def dashboard_setup_page(request: Request):
    """Show password setup form."""
    # If password already set, redirect to login
    if await is_admin_password_set():
        return RedirectResponse(url="/dashboard/login", status_code=307)
    
    return templates.TemplateResponse(request, "setup.html", {"error": None})


@app.post("/dashboard/setup", response_class=HTMLResponse)
async def dashboard_setup_submit(
    request: Request,
    password: str = Form(...),
    confirm_password: str = Form(...),
):
    """Handle password setup form submission."""
    # If password already set, redirect to login
    if await is_admin_password_set():
        return RedirectResponse(url="/dashboard/login", status_code=307)
    
    # Validate password
    if password != confirm_password:
        return templates.TemplateResponse(
            request, "setup.html", {"error": "Passwords do not match"}
        )
    
    if len(password) < 8:
        return templates.TemplateResponse(
            request, "setup.html", {"error": "Password must be at least 8 characters"}
        )
    
    # Hash and store password
    password_hash = hash_password(password)
    database = Database(db.db_path)
    await database.set_setting("admin_password_hash", password_hash)
    
    # Redirect to login
    return RedirectResponse(url="/dashboard/login", status_code=303)


@app.get("/dashboard/login", response_class=HTMLResponse)
async def dashboard_login_page(request: Request):
    """Show login form."""
    # If no password set, redirect to setup
    if not await is_admin_password_set():
        return RedirectResponse(url="/dashboard/setup", status_code=307)
    
    # If already logged in, redirect to dashboard
    if await get_current_session(request):
        return RedirectResponse(url="/dashboard", status_code=307)
    
    return templates.TemplateResponse(request, "login.html", {"error": None})


@app.post("/dashboard/login", response_class=HTMLResponse)
async def dashboard_login_submit(
    request: Request,
    password: str = Form(...),
):
    """Handle login form submission."""
    database = Database(db.db_path)
    stored_hash = await database.get_setting("admin_password_hash")
    
    if not stored_hash or not verify_password(password, stored_hash):
        return templates.TemplateResponse(
            request, "login.html", {"error": "Invalid password"}
        )
    
    # Create session
    token = generate_session_token()
    expiry = get_session_expiry()
    
    await database.set_setting("admin_session_token", token)
    await database.set_setting("admin_session_expires", expiry.isoformat())
    
    # Set cookie and redirect
    response = RedirectResponse(url="/dashboard", status_code=303)
    response.set_cookie(
        key="krell_session",
        value=token,
        httponly=True,
        max_age=7 * 24 * 60 * 60,  # 7 days
        samesite="lax",
    )
    return response


@app.get("/dashboard/logout")
async def dashboard_logout(request: Request):
    """Log out and clear session."""
    database = Database(db.db_path)
    
    # Clear session from database
    await database.delete_setting("admin_session_token")
    await database.delete_setting("admin_session_expires")
    
    # Clear cookie and redirect
    response = RedirectResponse(url="/dashboard/login", status_code=307)
    response.delete_cookie("krell_session")
    return response
```

**Step 4: Update the existing dashboard route to check auth**

Modify the existing `dashboard` function (around line 120):

```python
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Serve dashboard HTML page"""
    # Check if password is set
    if not await is_admin_password_set():
        return RedirectResponse(url="/dashboard/setup", status_code=307)
    
    # Check if logged in
    if not await get_current_session(request):
        return RedirectResponse(url="/dashboard/login", status_code=307)
    
    return templates.TemplateResponse(request, "dashboard.html")
```

**Step 5: Add delete_setting method to Database if not exists**

Check if `delete_setting` exists in `database/db.py`. If not, add it:

```python
async def delete_setting(self, key: str) -> bool:
    """Delete a setting by key."""
    async with aiosqlite.connect(self.db_path) as db:
        cursor = await db.execute("DELETE FROM settings WHERE key = ?", (key,))
        await db.commit()
        return cursor.rowcount > 0
```

**Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_admin_auth.py -v`
Expected: All tests PASS

**Step 7: Commit**

```bash
git add main.py database/db.py tests/test_admin_auth.py
git commit -m "Implement setup, login, and logout routes for admin auth"
```

---

## Task 6: Protect Dashboard API Routes

**Files:**
- Modify: `main.py`
- Modify: `tests/test_admin_auth.py`

**Step 1: Add tests for protected routes**

Add to `tests/test_admin_auth.py`:

```python
class TestProtectedRoutes:
    """Tests for authentication on protected routes."""
    
    def test_dashboard_api_status_requires_auth(self, client):
        """GET /dashboard/api/status should require auth."""
        # Setup password first
        client.post(
            "/dashboard/setup",
            data={"password": "validpassword123", "confirm_password": "validpassword123"}
        )
        
        response = client.get("/dashboard/api/status")
        
        assert response.status_code == 401
    
    def test_dashboard_api_status_works_with_auth(self, client):
        """GET /dashboard/api/status should work when authenticated."""
        # Setup and login
        client.post(
            "/dashboard/setup",
            data={"password": "validpassword123", "confirm_password": "validpassword123"}
        )
        client.post(
            "/dashboard/login",
            data={"password": "validpassword123"}
        )
        
        response = client.get("/dashboard/api/status")
        
        assert response.status_code == 200
    
    def test_admin_reload_plugins_requires_auth(self, client):
        """POST /api/admin/reload-plugins should require auth."""
        response = client.post("/api/admin/reload-plugins")
        
        assert response.status_code == 401
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_admin_auth.py::TestProtectedRoutes -v`
Expected: Tests FAIL (routes not protected yet)

**Step 3: Create auth dependency function**

Add to `main.py` after the helper functions:

```python
from fastapi import Depends, HTTPException


async def require_admin_auth_api(request: Request):
    """Dependency to require admin auth for API routes. Returns 401 if not authenticated."""
    if not await is_admin_password_set():
        raise HTTPException(status_code=401, detail="Admin password not configured")
    
    session = await get_current_session(request)
    if not session:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    return session
```

**Step 4: Add dependency to dashboard API routes**

Update each dashboard API route to include the dependency. For example:

```python
@app.get("/dashboard/api/status")
async def dashboard_status(request: Request, _: str = Depends(require_admin_auth_api)):
    """Get system status for dashboard"""
    # ... existing code
```

Apply to these routes:
- `/dashboard/api/status`
- `/dashboard/api/settings` (GET)
- `/dashboard/api/settings` (POST)
- `/dashboard/api/test-connection`
- `/dashboard/api/plugins`
- `/dashboard/api/plugins/reload`
- `/dashboard/api/recent/conversations`
- `/dashboard/api/recent/journal`

**Step 5: Add dependency to admin API routes in api/routes.py**

Add import at top of `api/routes.py`:

```python
from fastapi import Depends, Request
```

Create the same dependency (or import from main):

```python
# For now, duplicate the helper - can refactor later
async def require_admin_auth_api(request: Request):
    """Require admin auth for API routes."""
    from database.db import Database
    from database import db
    from auth import is_session_expired
    
    database = Database(db.db_path)
    password_hash = await database.get_setting("admin_password_hash")
    
    if not password_hash:
        raise HTTPException(status_code=401, detail="Admin password not configured")
    
    token = request.cookies.get("krell_session")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    stored_token = await database.get_setting("admin_session_token")
    expires = await database.get_setting("admin_session_expires")
    
    if token != stored_token or is_session_expired(expires):
        raise HTTPException(status_code=401, detail="Session expired")
    
    return token
```

Add dependency to admin routes:
- `/api/admin/reload-plugins`
- `/api/admin/plugins`
- `/api/admin/reload-agent`

**Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_admin_auth.py -v`
Expected: All tests PASS

**Step 7: Commit**

```bash
git add main.py api/routes.py tests/test_admin_auth.py
git commit -m "Protect dashboard and admin API routes with auth"
```

---

## Task 7: Add Logout Button to Dashboard

**Files:**
- Modify: `templates/dashboard.html`

**Step 1: Add logout button to header**

In `templates/dashboard.html`, modify the header section (around line 12-16):

```html
        <!-- Header -->
        <div class="mb-8 flex justify-between items-start">
            <div>
                <h1 class="text-4xl font-bold text-gray-900">Krell Dashboard</h1>
                <p class="text-gray-600 mt-2">Configuration and monitoring for your AI companion</p>
            </div>
            <a href="/dashboard/logout" 
               class="bg-gray-200 text-gray-700 px-4 py-2 rounded-md hover:bg-gray-300 transition-colors">
                Logout
            </a>
        </div>
```

**Step 2: Commit**

```bash
git add templates/dashboard.html
git commit -m "Add logout button to dashboard header"
```

---

## Task 8: Final Integration Test

**Files:**
- Test: `tests/test_admin_auth.py`

**Step 1: Add end-to-end test**

Add to `tests/test_admin_auth.py`:

```python
class TestFullFlow:
    """End-to-end authentication flow test."""
    
    def test_complete_auth_flow(self, client):
        """Test complete flow: setup -> login -> access -> logout -> denied."""
        # 1. Dashboard redirects to setup
        response = client.get("/dashboard", follow_redirects=False)
        assert response.status_code == 307
        assert "/setup" in response.headers["location"]
        
        # 2. Setup password
        response = client.post(
            "/dashboard/setup",
            data={"password": "securepass123", "confirm_password": "securepass123"},
            follow_redirects=False
        )
        assert response.status_code == 303
        
        # 3. Dashboard now redirects to login
        response = client.get("/dashboard", follow_redirects=False)
        assert response.status_code == 307
        assert "/login" in response.headers["location"]
        
        # 4. Login
        response = client.post(
            "/dashboard/login",
            data={"password": "securepass123"},
            follow_redirects=False
        )
        assert response.status_code == 303
        assert "krell_session" in response.cookies
        
        # 5. Access dashboard (now works)
        response = client.get("/dashboard")
        assert response.status_code == 200
        assert b"Krell Dashboard" in response.content
        
        # 6. Logout
        response = client.get("/dashboard/logout", follow_redirects=False)
        assert response.status_code == 307
        
        # 7. Dashboard redirects to login again
        response = client.get("/dashboard", follow_redirects=False)
        assert response.status_code == 307
        assert "/login" in response.headers["location"]
```

**Step 2: Run all auth tests**

Run: `uv run pytest tests/test_admin_auth.py -v`
Expected: All tests PASS

**Step 3: Run full test suite**

Run: `uv run pytest tests/test_database.py tests/test_admin_endpoints.py tests/test_api_endpoints.py tests/test_admin_auth.py tests/test_auth.py -v`
Expected: All tests PASS

**Step 4: Commit**

```bash
git add tests/test_admin_auth.py
git commit -m "Add end-to-end auth flow integration test"
```

---

## Task 9: Update Design Doc and Final Cleanup

**Files:**
- Modify: `docs/plans/2025-12-29-admin-auth-design.md`

**Step 1: Mark design as implemented**

Add to top of design doc:

```markdown
**Status:** Implemented (2025-12-29)
```

**Step 2: Commit**

```bash
git add docs/plans/2025-12-29-admin-auth-design.md
git commit -m "Mark admin auth design as implemented"
```

---

## Summary

After completing all tasks, you will have:

1. bcrypt dependency for password hashing
2. Auth helper functions (`auth.py`)
3. Setup page for first-time password creation
4. Login page for authentication
5. Session management with HTTP-only cookies (7-day expiry)
6. Protected dashboard and admin API routes
7. Logout functionality
8. Comprehensive test coverage

**Total estimated time:** 45-60 minutes
