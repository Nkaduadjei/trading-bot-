"""uvicorn entry point: python -m uvicorn admin_console.main:app --port 8004"""
from .app import create_app
from .config import Settings

app = create_app(Settings.from_env())
