from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def list_positions():
    pass


@router.get("/{position_id}")
async def get_position(position_id: str):
    pass


@router.post("/{position_id}/close")
async def close_position(position_id: str):
    pass
