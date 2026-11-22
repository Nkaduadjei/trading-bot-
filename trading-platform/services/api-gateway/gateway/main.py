"""uvicorn entry point: python -m uvicorn gateway.main:app --port 8000"""
from .app import create_app
from .config import Settings

app = create_app(Settings.from_env())
