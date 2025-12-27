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

from fastapi import FastAPI, Request, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from contextlib import asynccontextmanager
from api.routes import router
from api.websocket import router as websocket_router
from database.db import ConversationDB, Database
from config import Config
from core.plugin_loader import PluginLoader
import time
from datetime import datetime

# Load configuration
config = Config()

# Initialize database
db = ConversationDB(config.database_path)

# Initialize plugin tools
plugin_loader = PluginLoader()
tools = plugin_loader.get_tools()

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
    logger.info("Kyutai TTS initialized")

    # Load plugins
    logger.info(f"Loaded {len(tools)} plugin tools")
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
# Dashboard Routes
# ============================================================================


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Serve dashboard HTML page"""
    return templates.TemplateResponse(request, "dashboard.html")


@app.get("/dashboard/api/status")
async def dashboard_status():
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
async def dashboard_get_settings():
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
    llm_endpoint: str = Form(...),
    llm_model: str = Form(...),
    llm_provider: str = Form("auto"),
    api_key: str = Form(""),
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
async def dashboard_test_connection(request: dict):
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
async def dashboard_get_plugins():
    """Get loaded plugins info for dashboard"""
    # Simple plugin info for the new function-based loader
    plugin_info = []
    for tool in tools:
        plugin_info.append(
            {"name": tool.__name__, "module": tool.__module__, "status": "loaded"}
        )
    return {"plugins": plugin_info}


@app.post("/dashboard/api/plugins/reload")
async def dashboard_reload_plugins():
    """Reload plugins manually from dashboard"""
    # Reload tools
    global tools
    plugin_loader.reload_plugins()
    tools = plugin_loader.get_tools()

    return {
        "success": True,
        "plugins_loaded": len(tools),
        "tools_count": len(tools),
    }


@app.get("/dashboard/api/recent/conversations")
async def dashboard_recent_conversations():
    """Get recent conversations for dashboard"""
    database = Database(db.db_path)
    conversations = await database.list_conversations(limit=10)
    return conversations


@app.get("/dashboard/api/recent/journal")
async def dashboard_recent_journal():
    """Get recent journal entries for dashboard"""
    database = Database(db.db_path)
    entries = await database.search_journals(limit=10)
    return entries


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app", host=config.server_host, port=config.server_port, reload=True
    )
