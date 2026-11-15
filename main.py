"""
Krell Backend - FastAPI Application Entry Point
"""

import logging
import sys

# Configure logging before any other imports
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)

# Set specific loggers
logging.getLogger("api.websocket").setLevel(logging.INFO)
logging.getLogger("services").setLevel(logging.INFO)
logging.getLogger("core").setLevel(logging.INFO)

# Reduce noise from other libraries
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

from pathlib import Path

from typing import Optional
from fastapi import FastAPI, Request, Form, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from contextlib import asynccontextmanager
from auth import (
    hash_password,
    verify_password,
    generate_session_token,
    get_session_expiry,
    is_session_expired,
)
from api.routes import router
from api.websocket import router as websocket_router
from database.db import ConversationDB, Database
from config import Config
from core.plugin_loader import PluginLoader
from core.plugin_manager import PluginManager
from services.model_loader import verify_model_files, download_kyutai_models
import time
from datetime import datetime

# Load configuration
config = Config()

# Initialize database
db = ConversationDB(config.database_path)

# Initialize plugin tools
plugin_loader = PluginLoader()
tools = plugin_loader.get_tools()

# Initialize new plugin manager for runtime plugins
plugin_manager = PluginManager(Path(config.database_path).parent)

# Initialize templates
templates = Jinja2Templates(directory="templates")

# Track startup time for uptime calculation
startup_time = time.time()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle - startup and shutdown."""
    # Startup
    await db.init_db()
    logger.info("Database initialized")

    # Verify and load Kyutai models (eager loading)
    if not verify_model_files(config.tts_model_path, config.tts_voices_path):
        logger.warning("Kyutai models not found, attempting to download...")
        try:
            if download_kyutai_models(config.tts_model_path, config.tts_voices_path):
                # Verify again after download
                if not verify_model_files(
                    config.tts_model_path, config.tts_voices_path
                ):
                    raise RuntimeError("Model verification failed after download")
            else:
                raise RuntimeError("Failed to download Kyutai models on startup")
        except Exception as e:
            logger.error(f"Failed to initialize Kyutai models: {e}")
            raise

    logger.info("Kyutai models verified and ready")
    logger.info("Kyutai TTS initialized")

    # Initialize metrics
    from core.metrics import set_app_info, COMPONENT_STATUS
    set_app_info(version="0.1.0", tts_provider="kyutai")
    COMPONENT_STATUS.labels(component="database").set(1)
    COMPONENT_STATUS.labels(component="tts").set(1)
    logger.info("Prometheus metrics initialized")

    # Load plugins
    logger.info(f"Loaded {len(tools)} plugin tools")

    # Load runtime-installed plugins
    runtime_tools = plugin_manager.load_plugins()
    logger.info(f"Loaded {len(runtime_tools)} runtime plugin tools")

    logger.info("Krell backend started successfully!")

    yield

    # Shutdown
    logger.info("Krell backend shutting down...")


# Create FastAPI app with lifespan
app = FastAPI(
    title="Krell Backend",
    description="Self-hosted agentic AI backend with tool calling, persistent memory, and TTS",
    version="0.1.0",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify allowed origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(router, prefix="/api")
app.include_router(websocket_router, prefix="/api")


@app.get("/")
async def root():
    """Root endpoint"""
    return {"message": "Krell Backend API", "version": "0.1.0", "docs": "/docs"}


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


async def require_admin_auth_api(request: Request):
    """Dependency to require admin auth for API routes. Returns 401 if not authenticated."""
    if not await is_admin_password_set():
        raise HTTPException(status_code=401, detail="Admin password not configured")

    session = await get_current_session(request)
    if not session:
        raise HTTPException(status_code=401, detail="Not authenticated")

    return session


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


# ============================================================================
# Dashboard Routes
# ============================================================================


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


@app.get("/dashboard/api/status")
async def dashboard_status(request: Request, _: str = Depends(require_admin_auth_api)):
    """Get system status for dashboard"""
    database = Database(db.db_path)

    # Calculate uptime
    uptime_seconds = int(time.time() - startup_time)
    uptime_str = f"{uptime_seconds // 3600}h {(uptime_seconds % 3600) // 60}m"

    # Get counts
    conversations = await database.list_conversations(limit=10000)
    journals = await database.search_journals(limit=10000)

    return {
        "uptime": uptime_str,
        "total_conversations": len(conversations),
        "total_journal_entries": len(journals),
    }


@app.get("/dashboard/api/settings")
async def dashboard_get_settings(
    request: Request, _: str = Depends(require_admin_auth_api)
):
    """Get current LLM settings for dashboard"""
    database = Database(db.db_path)

    llm_endpoint = (
        await database.get_setting("llm_endpoint") or "http://localhost:11434"
    )
    llm_model = await database.get_setting("llm_model") or "llama3.2:latest"
    llm_provider = await database.get_setting("llm_provider") or "auto"
    api_key = await database.get_setting("api_key")

    # Mask API key if set
    if api_key and api_key != "CONFIGURE_IN_DASHBOARD":
        api_key = "••••••••"
    else:
        api_key = ""

    return {
        "llm_endpoint": llm_endpoint,
        "llm_model": llm_model,
        "llm_provider": llm_provider,
        "api_key": api_key,
    }


@app.post("/dashboard/api/settings")
async def dashboard_update_settings(
    request: Request,
    llm_endpoint: str = Form(...),
    llm_model: str = Form(...),
    llm_provider: str = Form("auto"),
    api_key: str = Form(""),
    _: str = Depends(require_admin_auth_api),
):
    """Update LLM settings from dashboard and reload agent."""
    database = Database(db.db_path)

    # Update each setting
    await database.set_setting("llm_endpoint", llm_endpoint)
    await database.set_setting("llm_model", llm_model)
    await database.set_setting("llm_provider", llm_provider)
    if api_key and "•" not in api_key:
        await database.set_setting("api_key", api_key, encrypt=True)

    # Reload agent to pick up new settings
    from api.routes import reload_krell_agent

    try:
        await reload_krell_agent()
        message = "Settings updated and agent reloaded successfully"
    except Exception as e:
        message = f"Settings updated but agent reload failed: {str(e)}"
        # Still return success since settings were saved
        return {"success": True, "message": message, "warning": True}

    return {"success": True, "message": message}


@app.post("/dashboard/api/test-connection")
async def dashboard_test_connection(
    http_request: Request,
    request: dict,
    _: str = Depends(require_admin_auth_api),
):
    """Test connection to LLM endpoint"""
    import httpx
    import json

    print(f"Test connection request: {request}")

    endpoint = request.get("endpoint")
    model = request.get("model")
    provider = request.get("provider")

    if not endpoint or not model:
        error_msg = (
            f"Missing endpoint or model. Received: endpoint={endpoint}, model={model}"
        )
        print(f"Validation error: {error_msg}")
        return {"success": False, "error": error_msg}

    # Use OpenAI-compatible API standard
    if not provider:
        provider = "openai"

    try:
        start_time = time.time()

        # Test using OpenAI-compatible /v1/models endpoint
        # Handle endpoints that may already include /v1
        if endpoint.rstrip("/").endswith("/v1"):
            test_url = f"{endpoint.rstrip('/')}/models"
        else:
            test_url = f"{endpoint.rstrip('/')}/v1/models"
        test_payload = None
        method = "GET"

        print(f"Testing connection to {test_url} with provider={provider}")

        async with httpx.AsyncClient(timeout=60.0) as client:
            if method == "POST":
                response = await client.post(test_url, json=test_payload)
            else:
                response = await client.get(test_url)

        latency_ms = int((time.time() - start_time) * 1000)
        print(f"Response status: {response.status_code}, latency: {latency_ms}ms")

        if response.status_code == 200:
            return {"success": True, "latency_ms": latency_ms, "provider": provider}
        else:
            error_body = response.text
            print(f"HTTP error body: {error_body}")
            return {
                "success": False,
                "error": f"HTTP {response.status_code}: {error_body}",
                "provider": provider,
            }

    except Exception as e:
        import traceback

        error_msg = f"{type(e).__name__}: {str(e)}"
        print(f"Connection test error: {error_msg}")
        traceback.print_exc()
        return {"success": False, "error": error_msg, "provider": provider or "unknown"}


@app.get("/dashboard/api/plugins")
async def dashboard_get_plugins(
    request: Request, _: str = Depends(require_admin_auth_api)
):
    """Get loaded plugins info for dashboard"""
    # Built-in plugins from PluginLoader
    builtin_plugins = []
    for tool in tools:
        builtin_plugins.append(
            {
                "name": tool.__name__,
                "module": tool.__module__,
                "status": "loaded",
                "source": "builtin",
            }
        )

    # Runtime-installed plugins from PluginManager
    runtime_plugins = []
    for plugin in plugin_manager.list_plugins():
        runtime_plugins.append(
            {
                "name": plugin["name"],
                "version": plugin["version"],
                "description": plugin.get("description", ""),
                "enabled": plugin["enabled"],
                "configured": plugin["configured"],
                "missing_config": plugin.get("missing_config", []),
                "source": "runtime",
                "status": "loaded"
                if plugin["enabled"] and plugin["configured"]
                else "disabled",
            }
        )

    return {"plugins": builtin_plugins, "runtime_plugins": runtime_plugins}


@app.post("/dashboard/api/plugins/reload")
async def dashboard_reload_plugins(
    request: Request, _: str = Depends(require_admin_auth_api)
):
    """Reload plugins manually from dashboard"""
    # Reload built-in tools
    global tools
    plugin_loader.reload_plugins()
    tools = plugin_loader.get_tools()

    # Reload runtime plugins
    runtime_tools = plugin_manager.reload_plugins()

    return {
        "success": True,
        "builtin_plugins_loaded": len(tools),
        "runtime_plugins_loaded": len(runtime_tools),
        "tools_count": len(tools) + len(runtime_tools),
    }


@app.get("/dashboard/api/recent/conversations")
async def dashboard_recent_conversations(
    request: Request, _: str = Depends(require_admin_auth_api)
):
    """Get recent conversations for dashboard"""
    database = Database(db.db_path)
    conversations = await database.list_conversations(limit=10)
    return conversations


@app.get("/dashboard/api/recent/journal")
async def dashboard_recent_journal(
    request: Request, _: str = Depends(require_admin_auth_api)
):
    """Get recent journal entries for dashboard"""
    database = Database(db.db_path)
    entries = await database.search_journals(limit=10)
    return entries


@app.get("/dashboard/api/voices")
async def dashboard_get_voices(
    request: Request, _: str = Depends(require_admin_auth_api)
):
    """Get list of available TTS voices"""
    try:
        from api.routes import tts_service

        if hasattr(tts_service, "_kyutai_model") and tts_service._kyutai_model:
            all_voices = tts_service._kyutai_model.get_available_voices()
            # Filter to only include .safetensors files (voice embeddings)
            # .wav files are just samples for reference
            voices = [v for v in all_voices if v.endswith(".safetensors")]
            return {"success": True, "voices": voices}
        else:
            return {
                "success": False,
                "error": "TTS model not initialized",
                "voices": [],
            }
    except Exception as e:
        return {"success": False, "error": str(e), "voices": []}


@app.get("/dashboard/api/voice/current")
async def dashboard_get_current_voice(
    request: Request, _: str = Depends(require_admin_auth_api)
):
    """Get currently configured voice"""
    database = Database(db.db_path)
    voice = await database.get_setting("tts_voice") or config.tts_voice
    return {"voice": voice}


@app.post("/dashboard/api/voice")
async def dashboard_set_voice(
    request: Request,
    voice: str = Form(...),
    _: str = Depends(require_admin_auth_api),
):
    """Set TTS voice configuration"""
    database = Database(db.db_path)
    await database.set_setting("tts_voice", voice)

    # Update the TTS service to use the new voice
    from api.routes import tts_service

    tts_service.voice = voice

    return {"success": True, "message": "Voice updated successfully"}


@app.get("/dashboard/api/voice/sample")
async def dashboard_voice_sample(
    request: Request,
    voice: str,
    _: str = Depends(require_admin_auth_api),
):
    """Generate a sample audio for a voice"""
    try:
        from api.routes import tts_service
        from fastapi.responses import StreamingResponse

        sample_text = "Hello! This is a sample of my voice. How do I sound?"

        async def generate_sample():
            async for chunk in tts_service.stream_tts_chunked(
                text=sample_text,
                voice=voice,
                max_text_length=500,
            ):
                yield chunk

        return StreamingResponse(
            generate_sample(),
            media_type="audio/wav",
            headers={"Content-Disposition": f"inline; filename=voice_sample.wav"},
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to generate sample: {str(e)}"
        )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app", host=config.server_host, port=config.server_port, reload=True
    )
