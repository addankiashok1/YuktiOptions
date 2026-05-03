from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import router as api_v1_router

app = FastAPI(
    title="YuktiOptions",
    description="Options trading simulation platform",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── middleware ────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── routers ───────────────────────────────────────────────────────────────────
app.include_router(api_v1_router, prefix="/api/v1")


# ── health check ──────────────────────────────────────────────────────────────
@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok", "service": "yuktioptions"}
