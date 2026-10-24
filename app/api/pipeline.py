from uuid import UUID

from fastapi import APIRouter, BackgroundTasks

from app import pipeline

router = APIRouter(prefix="/pipeline", tags=["pipeline"])


@router.post("/discover")
async def run_discover(bg: BackgroundTasks, categories: list[str] | None = None, cities: list[str] | None = None):
    bg.add_task(pipeline.discover, categories, cities)
    return {"started": "discover"}


@router.post("/enrich/{lead_id}")
async def run_enrich(lead_id: UUID, bg: BackgroundTasks):
    bg.add_task(pipeline.enrich_lead, str(lead_id))
    return {"started": "enrich", "lead_id": str(lead_id)}


@router.post("/verify/{lead_id}")
async def run_verify(lead_id: UUID, bg: BackgroundTasks):
    bg.add_task(pipeline.verify_lead, str(lead_id))
    return {"started": "verify", "lead_id": str(lead_id)}


@router.post("/personalize/{lead_id}")
async def run_personalize(lead_id: UUID, bg: BackgroundTasks):
    bg.add_task(pipeline.personalize_lead, str(lead_id))
    return {"started": "personalize", "lead_id": str(lead_id)}


@router.post("/send/{lead_id}")
async def run_send(lead_id: UUID, bg: BackgroundTasks):
    bg.add_task(pipeline.send_lead, str(lead_id))
    return {"started": "send", "lead_id": str(lead_id)}


@router.post("/run")
async def run_full(bg: BackgroundTasks, limit: int = 50):
    bg.add_task(pipeline.run_pipeline, limit)
    return {"started": "run", "limit": limit}


@router.post("/schedule")
async def run_scheduled(bg: BackgroundTasks, limit: int = 30):
    """Cron entrypoint: discover new leads then process + send them."""
    bg.add_task(pipeline.scheduled_run, limit)
    return {"started": "schedule", "limit": limit}
