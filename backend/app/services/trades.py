"""
The trades MENDORA supports.

The IDs match the frontend (`src/data/content.ts`), so the React app and the
API always agree: "plumbing", "electrical", "carpentry".
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Trade:
    id: str
    name: str


TRADES: tuple[Trade, ...] = (
    Trade(id="plumbing", name="Plumbing"),
    Trade(id="electrical", name="Electrical"),
    Trade(id="carpentry", name="Carpentry"),
)

_TRADES_BY_ID = {trade.id: trade for trade in TRADES}

SUPPORTED_TRADE_IDS: tuple[str, ...] = tuple(_TRADES_BY_ID)


def list_trades() -> list[Trade]:
    return list(TRADES)


def get_trade(trade_id: str) -> Trade | None:
    """Return the trade for this ID, or None if it isn't supported."""
    return _TRADES_BY_ID.get(trade_id)
