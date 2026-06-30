"""FastAPI application entry point.

Mounts CRUD and chat API routers under ``/api`` and serves the built React
SPA from ``frontend/dist`` when present.
"""
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from backend import routes_chat, routes_crud

app = FastAPI(title="Agent Skills Dev Studio")

app.include_router(routes_crud.router, prefix="/api")
app.include_router(routes_chat.router, prefix="/api")

# Serve the built single-page app if it has been compiled.
_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if _dist.is_dir():
    app.mount("/", StaticFiles(directory=_dist, html=True), name="spa")
