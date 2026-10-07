"""FastAPI application entrypoint for the Clinic Studio backend pipeline."""
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND_DIR))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from routers.reels import OUTPUT_DIR
from routers.reels import router as reels_router

app = FastAPI(title="Clinic Studio API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(reels_router, prefix="/api")

# Serve rendered reels directly, e.g. http://localhost:8000/outputs/<filename>.mp4
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/outputs", StaticFiles(directory=str(OUTPUT_DIR)), name="outputs")


@app.get("/")
def root():
    return {"status": "ok", "service": "clinic-studio-api"}
