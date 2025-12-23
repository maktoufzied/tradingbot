"""Tests for Alpaca broker integration."""

import os
from unittest.mock import MagicMock, patch

import pytest

from tradingbot._components.brokers.plugins.alpaca import AlpacaBroker
from tradingbot.types import Order


@pytest.fixture
def mock_env():
    """Set up mock environment variables."""
    with patch.dict(
        os.environ,
        {
            "ALPACA_API_KEY": "test_key",
            "ALPACA_SECRET_KEY": "test_secret",
            "ALPACA_PAPER": "true",
        },
    ):
        yield


@pytest.fixture
def mock_trading_client():
    """Create a mock TradingClient."""
    with patch("tradingbot._components.brokers.plugins.alpaca.TradingClient") as mock:
        client = MagicMock()
        mock.return_value = client
        yield client


class TestAlpacaBrokerInit:
    def test_raises_without_credentials(self):
        """Missing credentials should raise ValueError on first use."""
        with patch.dict(os.environ, {}, clear=True), pytest.raises(ValueError, match="credentials not found"):
            broker = AlpacaBroker()
            broker.get_account()  # Trigger lazy initialization

    def test_raises_without_api_key(self):
        """Missing API key should raise ValueError on first use."""
        with (
            patch.dict(os.environ, {"ALPACA_SECRET_KEY": "secret"}, clear=True),
            pytest.raises(ValueError, match="credentials not found"),
        ):
            broker = AlpacaBroker()
            broker.get_account()  # Trigger lazy initialization

    def test_raises_without_secret_key(self):
        """Missing secret key should raise ValueError on first use."""
        with (
            patch.dict(os.environ, {"ALPACA_API_KEY": "key"}, clear=True),
            pytest.raises(ValueError, match="credentials not found"),
        ):
            broker = AlpacaBroker()
            broker.get_account()  # Trigger lazy initialization

    def test_initializes_with_credentials(self, mock_env, mock_trading_client):
        """Successful initialization with credentials."""
        broker = AlpacaBroker()
        assert broker.name == "alpaca"


class TestAlpacaBrokerOrders:
    def test_submit_market_order_long(self, mock_env, mock_trading_client):
        """Submit a long market order successfully."""
        mock_order = MagicMock()
        mock_order.id = "order-123"
        mock_order.status.value = "filled"
        mock_order.filled_avg_price = 150.50
        mock_order.filled_qty = 10
        mock_trading_client.submit_order.return_value = mock_order

        broker = AlpacaBroker()
        order = Order(symbol="MSFT", direction="LONG", size=10, order_type="MARKET")
        result = broker.submit_order(order)

        assert result.order_id == "order-123"
        assert result.status == "FILLED"
        assert result.filled_price == 150.50
        assert result.filled_size == 10

    def test_submit_market_order_short(self, mock_env, mock_trading_client):
        """Submit a short market order successfully."""
        mock_order = MagicMock()
        mock_order.id = "order-456"
        mock_order.status.value = "filled"
        mock_order.filled_avg_price = 450.00
        mock_order.filled_qty = 5
        mock_trading_client.submit_order.return_value = mock_order

        broker = AlpacaBroker()
        order = Order(symbol="QQQ", direction="SHORT", size=5, order_type="MARKET")
        result = broker.submit_order(order)

        assert result.order_id == "order-456"
        assert result.status == "FILLED"
        assert result.filled_price == 450.00
        assert result.filled_size == 5

    def test_submit_order_pending(self, mock_env, mock_trading_client):
        """Handle pending order status."""
        mock_order = MagicMock()
        mock_order.id = "order-789"
        mock_order.status.value = "new"
        mock_order.filled_avg_price = None
        mock_order.filled_qty = None
        mock_trading_client.submit_order.return_value = mock_order

        broker = AlpacaBroker()
        order = Order(symbol="MSFT", direction="LONG", size=10, order_type="MARKET")
        result = broker.submit_order(order)

        assert result.order_id == "order-789"
        assert result.status == "PENDING"
        assert result.filled_price is None
        assert result.filled_size == 0

    def test_submit_order_rejected(self, mock_env, mock_trading_client):
        """Handle rejected order (API error)."""
        from alpaca.common.exceptions import APIError

        mock_trading_client.submit_order.side_effect = APIError("Insufficient funds")

        broker = AlpacaBroker()
        order = Order(symbol="MSFT", direction="LONG", size=10, order_type="MARKET")
        result = broker.submit_order(order)

        assert result.status == "REJECTED"
        assert result.order_id == ""
        assert "Insufficient funds" in str(result.message)

    def test_cancel_order_success(self, mock_env, mock_trading_client):
        """Cancel order successfully."""
        broker = AlpacaBroker()
        result = broker.cancel_order("order-123")
        assert result is True
        mock_trading_client.cancel_order_by_id.assert_called_once_with("order-123")

    def test_cancel_order_failure(self, mock_env, mock_trading_client):
        """Handle cancel order failure."""
        from alpaca.common.exceptions import APIError

        mock_trading_client.cancel_order_by_id.side_effect = APIError("Order not found")

        broker = AlpacaBroker()
        result = broker.cancel_order("order-123")
        assert result is False


class TestAlpacaBrokerPositions:
    def test_get_position_long(self, mock_env, mock_trading_client):
        """Get an existing long position."""
        mock_pos = MagicMock()
        mock_pos.symbol = "MSFT"
        mock_pos.qty = 10
        mock_pos.avg_entry_price = 450.00
        mock_pos.market_value = 4600.00
        mock_pos.unrealized_pl = 100.00
        mock_trading_client.get_open_position.return_value = mock_pos

        broker = AlpacaBroker()
        position = broker.get_position("MSFT")

        assert position is not None
        assert position.symbol == "MSFT"
        assert position.direction == "LONG"
        assert position.size == 10
        assert position.avg_entry_price == 450.00
        assert position.market_value == 4600.00
        assert position.unrealized_pnl == 100.00

    def test_get_position_short(self, mock_env, mock_trading_client):
        """Get an existing short position."""
        mock_pos = MagicMock()
        mock_pos.symbol = "QQQ"
        mock_pos.qty = -5
        mock_pos.avg_entry_price = 380.00
        mock_pos.market_value = -1850.00
        mock_pos.unrealized_pl = 50.00
        mock_trading_client.get_open_position.return_value = mock_pos

        broker = AlpacaBroker()
        position = broker.get_position("QQQ")

        assert position is not None
        assert position.symbol == "QQQ"
        assert position.direction == "SHORT"
        assert position.size == 5

    def test_get_position_not_exists(self, mock_env, mock_trading_client):
        """Handle non-existent position."""
        from alpaca.common.exceptions import APIError

        mock_trading_client.get_open_position.side_effect = APIError("Position not found")

        broker = AlpacaBroker()
        position = broker.get_position("MSFT")
        assert position is None

    def test_get_all_positions(self, mock_env, mock_trading_client):
        """Get all positions."""
        mock_pos1 = MagicMock()
        mock_pos1.symbol = "MSFT"
        mock_pos1.qty = 10
        mock_pos1.avg_entry_price = 450.00
        mock_pos1.market_value = 4600.00
        mock_pos1.unrealized_pl = 100.00

        mock_pos2 = MagicMock()
        mock_pos2.symbol = "QQQ"
        mock_pos2.qty = 5
        mock_pos2.avg_entry_price = 380.00
        mock_pos2.market_value = 1950.00
        mock_pos2.unrealized_pl = 50.00

        mock_trading_client.get_all_positions.return_value = [mock_pos1, mock_pos2]

        broker = AlpacaBroker()
        positions = broker.get_positions()

        assert len(positions) == 2
        assert positions[0].symbol == "MSFT"
        assert positions[1].symbol == "QQQ"

    def test_get_all_positions_empty(self, mock_env, mock_trading_client):
        """Handle no positions."""
        mock_trading_client.get_all_positions.return_value = []

        broker = AlpacaBroker()
        positions = broker.get_positions()
        assert positions == []


class TestAlpacaBrokerAccount:
    def test_get_account(self, mock_env, mock_trading_client):
        """Get account info."""
        mock_account = MagicMock()
        mock_account.equity = 100000.00
        mock_account.buying_power = 200000.00
        mock_account.cash = 50000.00
        mock_trading_client.get_account.return_value = mock_account

        broker = AlpacaBroker()
        account = broker.get_account()

        assert account.equity == 100000.00
        assert account.buying_power == 200000.00
        assert account.cash == 50000.00


class TestAlpacaBrokerStatusMapping:
    @pytest.mark.parametrize(
        "alpaca_status,expected",
        [
            ("filled", "FILLED"),
            ("new", "PENDING"),
            ("partially_filled", "PARTIAL"),
            ("canceled", "CANCELLED"),
            ("rejected", "REJECTED"),
            ("expired", "CANCELLED"),
            ("pending_new", "PENDING"),
            ("accepted", "PENDING"),
        ],
    )
    def test_status_mapping(self, mock_env, mock_trading_client, alpaca_status, expected):
        """Test various order status mappings."""
        broker = AlpacaBroker()
        assert broker._map_order_status(alpaca_status) == expected
