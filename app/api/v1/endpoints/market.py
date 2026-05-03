from fastapi import APIRouter

router = APIRouter()


@router.get("/quote/{symbol}")
async def get_quote(symbol: str):
    pass


@router.get("/chain/{symbol}")
async def get_option_chain(symbol: str):
    pass
