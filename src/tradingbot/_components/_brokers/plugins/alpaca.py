"""Alpaca broker implementation for paper and live trading."""

import os
from typing import Any, Final

from alpaca.common.exceptions import APIError
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import MarketOrderRequest

from ...config import get_live_config
from ...models import AccountInfo, BrokerPosition, Direction, Order, OrderResult, OrderStatus
from ..protocol import BrokerProtocol

ALPACA_API_KEY_ENV: Final = "ALPACA_API_KEY"
ALPACA_SECRET_KEY_ENV: Final = "ALPACA_SECRET_KEY"
ALPACA_PAPER_ENV: Final = "ALPACA_PAPER"


class AlpacaBroker(BrokerProtocol):
    """Alpaca broker for paper and live trading."""

    def __init__(self) -> None:
        config = get_live_config().alpaca

        # Environment variables take priority over config file
        api_key = os.environ.get(ALPACA_API_KEY_ENV) or config.api_key
        secret_key = os.environ.get(ALPACA_SECRET_KEY_ENV) or config.secret_key
        paper_env = os.environ.get(ALPACA_PAPER_ENV)
        paper = paper_env.lower() == "true" if paper_env else config.paper

        if not api_key or not secret_key:
            raise ValueError(
                f"Alpaca API credentials not found. "
                f"Set {ALPACA_API_KEY_ENV} and {ALPACA_SECRET_KEY_ENV} environment variables, "
                f"or configure in tradingbot.toml under [tradingbot.live.alpaca]."
            )

        self._client = TradingClient(api_key, secret_key, paper=paper)
        self._paper = paper

    @property
    def name(self) -> str:
        return "alpaca"

    def submit_order(self, order: Order) -> OrderResult:
        """Submit a market order to Alpaca."""
        try:
            side = OrderSide.BUY if order.direction == "LONG" else OrderSide.SELL

            order_request = MarketOrderRequest(
                symbol=order.symbol,
                qty=order.size,
                side=side,
                time_in_force=TimeInForce.DAY,
                client_order_id=order.client_id,
            )

            alpaca_order: Any = self._client.submit_order(order_data=order_request)

            filled_price: float | None = None
            if alpaca_order.filled_avg_price is not None:
                filled_price = float(alpaca_order.filled_avg_price)

            filled_size = float(alpaca_order.filled_qty) if alpaca_order.filled_qty else 0

            return OrderResult(
                order_id=str(alpaca_order.id),
                status=self._map_order_status(str(alpaca_order.status.value)),
                filled_price=filled_price,
                filled_size=filled_size,
            )
        except APIError as e:
            return OrderResult(
                order_id="",
                status="REJECTED",
                filled_price=None,
                filled_size=0,
                message=str(e),
            )

    def cancel_order(self, order_id: str) -> bool:
        """Cancel a pending order."""
        try:
            self._client.cancel_order_by_id(order_id)
            return True
        except APIError:
            return False

    def get_position(self, symbol: str) -> BrokerPosition | None:
        """Get current position for a symbol."""
        try:
            pos = self._client.get_open_position(symbol)
            return self._map_position(pos)
        except APIError:
            return None

    def get_positions(self) -> list[BrokerPosition]:
        """Get all current positions."""
        try:
            positions = self._client.get_all_positions()
            return [self._map_position(p) for p in positions]
        except APIError:
            return []

    def get_account(self) -> AccountInfo:
        """Get account information."""
        account: Any = self._client.get_account()
        return AccountInfo(
            equity=float(account.equity),
            buying_power=float(account.buying_power),
            cash=float(account.cash),
        )

    def _map_order_status(self, alpaca_status: str) -> OrderStatus:
        """Map Alpaca order status to internal status."""
        status_map: dict[str, OrderStatus] = {
            "new": "PENDING",
            "partially_filled": "PARTIAL",
            "filled": "FILLED",
            "done_for_day": "FILLED",
            "canceled": "CANCELLED",
            "expired": "CANCELLED",
            "replaced": "CANCELLED",
            "pending_cancel": "PENDING",
            "pending_replace": "PENDING",
            "accepted": "PENDING",
            "pending_new": "PENDING",
            "accepted_for_bidding": "PENDING",
            "stopped": "CANCELLED",
            "rejected": "REJECTED",
            "suspended": "REJECTED",
            "calculated": "PENDING",
        }
        return status_map.get(alpaca_status.lower(), "PENDING")

    def _map_position(self, alpaca_pos: Any) -> BrokerPosition:
        """Map Alpaca position to internal BrokerPosition."""
        qty = float(alpaca_pos.qty)
        direction: Direction = "LONG" if qty > 0 else "SHORT"
        return BrokerPosition(
            symbol=str(alpaca_pos.symbol),
            direction=direction,
            size=abs(qty),
            avg_entry_price=float(alpaca_pos.avg_entry_price),
            market_value=float(alpaca_pos.market_value),
            unrealized_pnl=float(alpaca_pos.unrealized_pl),
        )
