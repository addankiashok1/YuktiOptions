from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def get_wallet():
    pass


@router.post("/deposit")
async def deposit():
    pass


@router.post("/withdraw")
async def withdraw():
    pass
