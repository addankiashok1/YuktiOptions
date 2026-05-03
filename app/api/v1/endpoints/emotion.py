from fastapi import APIRouter

router = APIRouter()


@router.post("/log")
async def log_emotion():
    pass


@router.get("/history")
async def get_emotion_history():
    pass
