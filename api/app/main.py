import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI

from . import events
from .config import settings
from .db import Base, engine
from .routers import auth, jobs, system, voices

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("voicely.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.secret_key == "change-me":
        log.warning("SECRET_KEY is the default value. Set a random one before exposing this server.")
    # No migration tool yet: tables are created if missing, never altered.
    Base.metadata.create_all(engine)
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    consumer = asyncio.create_task(events.consume())
    yield
    consumer.cancel()
    with suppress(asyncio.CancelledError):
        await consumer


app = FastAPI(title="Voicely API", version="1.0.0", lifespan=lifespan,
              docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None)

for r in (auth.router, voices.router, jobs.router, system.router):
    app.include_router(r)
