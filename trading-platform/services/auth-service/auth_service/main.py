"""Entry point for uvicorn: `uvicorn auth_service.main:app --port 8001`"""
from .app import create_app
from .config import Settings

app = create_app(Settings.from_env())
