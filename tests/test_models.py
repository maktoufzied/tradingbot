"""Tests for data models."""

from tradingbot import Position, Signal, SwingPoint, Trade, Trend


class TestTrend:
    def test_trend_values(self):
        assert Trend.BULLISH.value == "BULLISH"
        assert Trend.BEARISH.value == "BEARISH"
        assert Trend.NEUTRAL.value == "NEUTRAL"

    def test_trend_enum_members(self):
        assert len(Trend) == 3


class TestSignal:
    def test_signal_values(self):
        assert Signal.BUY.value == "BUY"
        assert Signal.SELL.value == "SELL"
        assert Signal.HOLD.value == "HOLD"

    def test_signal_enum_members(self):
        assert len(Signal) == 3


class TestSwingPoint:
    def test_swing_point_creation(self):
        sp = SwingPoint(index=10, price=100.5, is_high=True)
        assert sp.index == 10
        assert sp.price == 100.5
        assert sp.is_high is True
        assert sp.timestamp is None

    def test_swing_point_with_timestamp(self):
        sp = SwingPoint(index=10, price=100.5, is_high=False, timestamp="2024-01-01")
        assert sp.timestamp == "2024-01-01"
        assert sp.is_high is False


class TestPosition:
    def test_position_creation(self):
        pos = Position(
            entry_price=100.0,
            entry_index=5,
            entry_time="2024-01-01",
            direction="LONG",
            size=10.0,
            stop_loss=98.0,
            take_profit=104.0,
        )
        assert pos.entry_price == 100.0
        assert pos.direction == "LONG"
        assert pos.size == 10.0
        assert pos.stop_loss == 98.0
        assert pos.take_profit == 104.0


class TestTrade:
    def test_trade_creation(self):
        trade = Trade(
            symbol="AAPL",
            entry_price=100.0,
            exit_price=105.0,
            entry_time="2024-01-01",
            exit_time="2024-01-05",
            entry_index=0,
            direction="LONG",
            size=10.0,
            pnl=50.0,
            pnl_pct=0.05,
            exit_reason="TAKE_PROFIT",
            holding_period=4,
        )
        assert trade.symbol == "AAPL"
        assert trade.pnl == 50.0
        assert trade.exit_reason == "TAKE_PROFIT"

    def test_trade_short_position(self):
        trade = Trade(
            symbol="SPY",
            entry_price=500.0,
            exit_price=490.0,
            entry_time="2024-01-01",
            exit_time="2024-01-02",
            entry_index=0,
            direction="SHORT",
            size=5.0,
            pnl=50.0,
            pnl_pct=0.01,
            exit_reason="TAKE_PROFIT",
            holding_period=1,
        )
        assert trade.direction == "SHORT"
        assert trade.pnl == 50.0
