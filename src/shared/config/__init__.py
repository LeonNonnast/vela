"""Vela application configuration."""

import os

from dotenv import load_dotenv

load_dotenv()

# Application
APP_ENV = os.getenv("APP_ENV", "development")
APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:8000")
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")

# Vela Directories
VELA_WORKFLOWS_DIR = os.getenv("VELA_WORKFLOWS_DIR", os.path.expanduser("~/.vela/workflows"))
VELA_AGENTS_DIR = os.getenv("VELA_AGENTS_DIR", os.path.expanduser("~/.vela/agents"))
VELA_RESOURCES_DIR = os.getenv("VELA_RESOURCES_DIR", os.path.expanduser("~/.vela/resources"))
VELA_MODULES_DIR = os.getenv("VELA_MODULES_DIR",
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "modules"))
VELA_LOCAL_MODULES_DIR = os.getenv("VELA_LOCAL_MODULES_DIR", os.path.expanduser("~/.vela/modules"))
VELA_MODULES = os.getenv("VELA_MODULES", "")

# Database
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./vela.db")

# Sentry
SENTRY_DSN = os.getenv("SENTRY_DSN")

# Server
MCP_PORT = int(os.getenv("MCP_PORT", os.getenv("PORT", "8000")))
API_PORT = int(os.getenv("API_PORT", "8001"))
API_BASE_URL = os.getenv("API_BASE_URL", f"http://localhost:{API_PORT}")
HOST = os.getenv("HOST", "0.0.0.0")
