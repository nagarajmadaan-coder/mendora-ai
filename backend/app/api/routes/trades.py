from fastapi import APIRouter

from ...schemas import TradeListResponse, TradeOut
from ...services.trades import list_trades

router = APIRouter(tags=["Trades"])


@router.get("/trades", response_model=TradeListResponse, summary="List supported trades")
def get_trades() -> TradeListResponse:
    return TradeListResponse(trades=[TradeOut(id=t.id, name=t.name) for t in list_trades()])
