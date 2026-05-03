from fastapi import APIRouter

router = APIRouter()


@router.post("/")
async def place_order():
    pass


@router.get("/")
async def list_orders():
    pass


@router.delete("/{order_id}")
async def cancel_order(order_id: str):
    pass
