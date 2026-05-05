from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import router as api_v1_router
from app.core.config import settings
from app.core.redis import close_redis
from app.services.stoploss_service import stoploss_engine

_is_production = settings.env == "production"


@asynccontextmanager
async def lifespan(app: FastAPI):
    stoploss_engine.start()
    yield
    stoploss_engine.stop()
    await close_redis()


app = FastAPI(
    title=settings.app_name,
    description="Options trading simulation platform",
    version="1.0.0",
    docs_url=None if _is_production else "/docs",
    redoc_url=None if _is_production else "/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_v1_router, prefix="/api/v1")


@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok", "service": "yuktioptions"}
