"""Alpaca broker implementation for paper and live trading."""

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final

from alpaca.common.exceptions import APIError
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderClass, OrderSide, QueryOrderStatus, TimeInForce
from alpaca.trading.requests import (
    GetOrdersRequest,
    GetPortfolioHistoryRequest,
    MarketOrderRequest,
    StopLossRequest,
    TakeProfitRequest,
)

from tradingbot._components.exceptions import (
    BrokerConnectionError,
    InsufficientFundsError,
)
from tradingbot._components.logging import get_logger
from tradingbot.config import get_engine_config
from tradingbot.interfaces import BrokerProtocol
from tradingbot.types import AccountInfo, BrokerPosition, Direction, MarketClock, Order, OrderResult, OrderStatus

logger = get_logger(__name__)


@dataclass
class ClosedTrade:
    """A closed trade (entry + exit) from broker history."""

    symbol: str
    direction: Direction
    size: float
    entry_price: float
    exit_price: float
    pnl: float
    entry_time: datetime
    exit_time: datetime


ALPACA_API_KEY_ENV: Final = "ALPACA_API_KEY"
ALPACA_SECRET_KEY_ENV: Final = "ALPACA_SECRET_KEY"
ALPACA_PAPER_ENV: Final = "ALPACA_PAPER"


class AlpacaBroker(BrokerProtocol):
    """Alpaca broker for paper and live trading."""

    def __init__(self) -> None:
        self._client: TradingClient | None = None
        self._paper: bool = False

    def _get_client(self) -> TradingClient:
        """Get or create the Alpaca trading client (lazy initialization)."""
        if self._client is not None:
            return self._client

        config = get_engine_config().alpaca

        # Environment variables take priority over config file
        api_key = os.environ.get(ALPACA_API_KEY_ENV) or config.api_key
        secret_key = os.environ.get(ALPACA_SECRET_KEY_ENV) or config.secret_key
        paper_env = os.environ.get(ALPACA_PAPER_ENV)
        self._paper = paper_env.lower() == "true" if paper_env else config.paper

        if not api_key or not secret_key:
            raise ValueError(
                f"Alpaca API credentials not found. "
                f"Set {ALPACA_API_KEY_ENV} and {ALPACA_SECRET_KEY_ENV} environment variables, "
                f"or configure in tradingbot.toml under [tradingbot.engine.alpaca]."
            )

        self._client = TradingClient(api_key, secret_key, paper=self._paper)
        return self._client

    @property
    def name(self) -> str:
        return "alpaca"

    def submit_order(self, order: Order) -> OrderResult:
        """Submit an order to Alpaca.

        If stop_loss and take_profit are provided, submits a bracket order (OCO).
        Otherwise submits a simple market order.
        """
        try:
            side = OrderSide.BUY if order.direction == "LONG" else OrderSide.SELL

            # Use bracket order if SL/TP provided
            if order.stop_loss is not None and order.take_profit is not None:
                order_request = MarketOrderRequest(
                    symbol=order.symbol,
                    qty=order.size,
                    side=side,
                    time_in_force=TimeInForce.GTC,  # Good-til-canceled for bracket
                    client_order_id=order.client_id,
                    order_class=OrderClass.BRACKET,
                    stop_loss=StopLossRequest(stop_price=order.stop_loss),
                    take_profit=TakeProfitRequest(limit_price=order.take_profit),
                )
            else:
                # Simple market order
                order_request = MarketOrderRequest(
                    symbol=order.symbol,
                    qty=order.size,
                    side=side,
                    time_in_force=TimeInForce.DAY,
                    client_order_id=order.client_id,
                )

            alpaca_order: Any = self._get_client().submit_order(order_data=order_request)

            filled_price: float | None = None
            if alpaca_order.filled_avg_price is not None:
                filled_price = float(alpaca_order.filled_avg_price)

            filled_size = float(alpaca_order.filled_qty) if alpaca_order.filled_qty else 0

            logger.info(
                "Order submitted: %s %s %s @ market (id=%s, status=%s)",
                order.direction,
                order.size,
                order.symbol,
                alpaca_order.id,
                alpaca_order.status.value,
            )

            return OrderResult(
                order_id=str(alpaca_order.id),
                status=self._map_order_status(str(alpaca_order.status.value)),
                filled_price=filled_price,
                filled_size=filled_size,
            )
        except APIError as e:
            error_msg = str(e)
            logger.warning(
                "Order rejected: %s %s %s - %s",
                order.direction,
                order.size,
                order.symbol,
                error_msg,
            )

            # Categorize the error for better handling
            if "insufficient" in error_msg.lower():
                raise InsufficientFundsError(error_msg, {"order": order.symbol}) from e
            if "forbidden" in error_msg.lower() or "unauthorized" in error_msg.lower():
                raise BrokerConnectionError(error_msg) from e

            # Return rejected result for other API errors (normal rejections)
            return OrderResult(
                order_id="",
                status="REJECTED",
                filled_price=None,
                filled_size=0,
                message=error_msg,
            )

    def cancel_order(self, order_id: str) -> bool:
        """Cancel a pending order."""
        try:
            self._get_client().cancel_order_by_id(order_id)
            return True
        except APIError:
            return False

    def get_order(self, order_id: str) -> OrderResult | None:
        """Get current status of an order."""
        try:
            alpaca_order: Any = self._get_client().get_order_by_id(order_id)

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
        except APIError:
            return None

    def get_position(self, symbol: str) -> BrokerPosition | None:
        """Get current position for a symbol."""
        try:
            pos = self._get_client().get_open_position(symbol)
            return self._map_position(pos)
        except APIError:
            return None

    def get_positions(self) -> list[BrokerPosition]:
        """Get all current positions."""
        try:
            positions = self._get_client().get_all_positions()
            return [self._map_position(p) for p in positions]
        except APIError:
            return []

    def get_account(self) -> AccountInfo:
        """Get account information."""
        account: Any = self._get_client().get_account()
        return AccountInfo(
            equity=float(account.equity),
            buying_power=float(account.buying_power),
            cash=float(account.cash),
        )

    def get_clock(self) -> MarketClock | None:
        """Get market clock status."""

        def _to_utc_naive(dt: datetime) -> datetime:
            """Convert timezone-aware datetime to naive UTC."""
            if dt.tzinfo:
                return dt.astimezone(UTC).replace(tzinfo=None)
            return dt

        try:
            clock: Any = self._get_client().get_clock()
            return MarketClock(
                is_open=bool(clock.is_open),
                next_open=_to_utc_naive(clock.next_open),
                next_close=_to_utc_naive(clock.next_close),
            )
        except APIError:
            return None

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

    def get_today_pnl(self) -> float:
        """Get today's realized P&L from portfolio history.

        Returns the total P&L for today (intraday).
        """
        try:
            req = GetPortfolioHistoryRequest(period="1D", timeframe="1Min", intraday_reporting="market_hours")
            history: Any = self._get_client().get_portfolio_history(req)

            # profit_loss is a list of P&L values, last value is current
            if history.profit_loss and len(history.profit_loss) > 0:
                # Return the latest P&L value (total for today)
                return float(history.profit_loss[-1]) if history.profit_loss[-1] is not None else 0.0
            return 0.0
        except APIError:
            return 0.0

    def get_today_trades(self) -> list[ClosedTrade]:
        """Get today's closed trades (matched buy/sell pairs).

        Returns list of ClosedTrade objects representing completed round-trips.
        """
        try:
            today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
            req = GetOrdersRequest(status=QueryOrderStatus.CLOSED, after=today, limit=100)
            orders: Any = self._get_client().get_orders(req)

            # Filter to filled orders only and sort by fill time
            filled: list[Any] = [o for o in orders if o.status.value == "filled" and o.filled_avg_price and o.filled_at]
            filled.sort(key=lambda o: o.filled_at)

            # Match buy/sell pairs by symbol to create trades
            trades: list[ClosedTrade] = []
            pending_entries: dict[str, Any] = {}  # symbol -> entry order

            for order in filled:
                symbol = str(order.symbol)
                qty = float(order.filled_qty)
                price = float(order.filled_avg_price)
                fill_time: datetime = order.filled_at

                if symbol not in pending_entries:
                    # First order for this symbol = entry
                    pending_entries[symbol] = order
                else:
                    # Second order = exit, create trade
                    entry = pending_entries.pop(symbol)
                    entry_side = entry.side.value
                    entry_price = float(entry.filled_avg_price)
                    entry_time: datetime = entry.filled_at

                    # Determine direction and P&L
                    direction: Direction = "LONG" if entry_side == "buy" else "SHORT"
                    pnl = (price - entry_price) * qty if direction == "LONG" else (entry_price - price) * qty

                    trades.append(
                        ClosedTrade(
                            symbol=symbol,
                            direction=direction,
                            size=qty,
                            entry_price=entry_price,
                            exit_price=price,
                            pnl=pnl,
                            entry_time=entry_time,
                            exit_time=fill_time,
                        )
                    )

            return trades
        except APIError:
            return []
