"""In-memory background jobs so long reel work survives the Next.js proxy timeout."""
import asyncio
import uuid
from collections.abc import Callable
from typing import Any, Literal

from pydantic import BaseModel

JobStatusName = Literal["queued", "running", "completed", "failed"]


class JobStatusResponse(BaseModel):
    job_id: str
    status: JobStatusName
    result: dict[str, Any] | None = None
    error: str | None = None


class JobAcceptedResponse(BaseModel):
    job_id: str
    status: Literal["queued"] = "queued"


_JOBS: dict[str, JobStatusResponse] = {}
_TASKS: set[asyncio.Task[None]] = set()


def create_job() -> JobStatusResponse:
    job = JobStatusResponse(job_id=uuid.uuid4().hex, status="queued")
    _JOBS[job.job_id] = job
    return job


def get_job(job_id: str) -> JobStatusResponse | None:
    return _JOBS.get(job_id)


def schedule_job(job_id: str, fn: Callable[..., Any], *args: Any) -> None:
    """Run fn in a worker thread and record queued → running → completed/failed."""

    async def _runner() -> None:
        job = _JOBS[job_id]
        job.status = "running"
        try:
            job.result = await asyncio.to_thread(fn, *args)
            job.status = "completed"
        except Exception as exc:
            job.error = str(exc)
            job.status = "failed"

    task = asyncio.create_task(_runner())
    _TASKS.add(task)
    task.add_done_callback(_TASKS.discard)
