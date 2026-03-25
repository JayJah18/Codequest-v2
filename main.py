from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.routes import router


app = FastAPI(title="CodeQuest Minimal Prototype")
app.include_router(router)

FRONTEND_DIR = Path(__file__).parent / "frontend"


@app.get("/ui")
def ui_index() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


app.mount("/ui/static", StaticFiles(directory=FRONTEND_DIR), name="ui-static")

