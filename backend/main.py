"""FastAPI application entrypoint for the Clinic Studio backend pipeline."""
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND_DIR))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from routers.reels import OUTPUT_DIR
from routers.reels import router as reels_router
from services.jobs import JobStatusResponse, get_job

app = FastAPI(title="Clinic Studio API")

app.add_middleware(
    CORSMiddleware,
    # Wildcard for local LAN dev (e.g. a phone on the same Wi-Fi hitting
    # http://<lan-ip>:3000, which the Next.js dev server proxies here).
    # No cookies/credentialed requests are used anywhere in this app, so a
    # wildcard origin is safe without allow_credentials.
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

class RootResponse(BaseModel):
    status: str
    service: str


@app.get("/api/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str) -> JobStatusResponse:
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
    return job


app.include_router(reels_router, prefix="/api")

# Serve rendered reels directly, e.g. http://localhost:8000/outputs/<filename>.mp4
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/outputs", StaticFiles(directory=str(OUTPUT_DIR)), name="outputs")


@app.get("/", response_model=RootResponse)
async def root() -> RootResponse:
    return RootResponse(status="ok", service="clinic-studio-api")
