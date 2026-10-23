from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from app.api import events, leads, pipeline
from app.db import init_db

STATIC = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="lead_er", lifespan=lifespan)

app.include_router(events.router, prefix="/events", tags=["events"])
app.include_router(leads.router, prefix="", tags=["leads"])
app.include_router(pipeline.router)


@app.get("/", include_in_schema=False)
async def index():
    return FileResponse(STATIC / "index.html")


@app.get("/health")
async def health():
    return {"ok": True}
