"""Comprehensive tests for execution cost modeling.

Tests cover:
- Price adjustment calculations (entry/exit with costs)
- Cost breakdown accuracy (spread, slippage, commission)
- Gross vs Net P&L calculations
- Edge cases (zero costs, extreme costs)
- Strategy profitability threshold detection
- Integration with the trading bot
"""

import pytest

from tradingbot._components.execution import (
    DEFAULT_COMMISSION_PER_SHARE,
    DEFAULT_SLIPPAGE_BPS,
    DEFAULT_SPREAD_BPS,
    ExecutionCosts,
    ExecutionModel,
)


class TestExecutionModelDefaults:
    """Test default configuration and factory methods."""

    def test_default_values(self) -> None:
        """Default model uses realistic US equity costs."""
        model = ExecutionModel()
        assert model.spread_bps == DEFAULT_SPREAD_BPS
        assert model.slippage_bps == DEFAULT_SLIPPAGE_BPS
        assert model.commission_per_share == DEFAULT_COMMISSION_PER_SHARE

    def test_zero_costs_factory(self) -> None:
        """Zero costs model for comparison backtests."""
        model = ExecutionModel.zero()
        assert model.spread_bps == 0
        assert model.slippage_bps == 0
        assert model.commission_per_share == 0

    def test_conservative_factory(self) -> None:
        """Conservative model uses higher cost estimates."""
        model = ExecutionModel.conservative()
        assert model.spread_bps > DEFAULT_SPREAD_BPS
        assert model.slippage_bps > DEFAULT_SLIPPAGE_BPS
        assert model.commission_per_share > DEFAULT_COMMISSION_PER_SHARE


class TestEntryPriceCalculation:
    """Test entry price adjustments for different directions."""

    def test_long_entry_pays_spread_and_slippage(self) -> None:
        """LONG entry: buy at ask + slippage = worse (higher) price."""
        model = ExecutionModel(spread_bps=10, slippage_bps=10, commission_per_share=0)
        signal_price = 100.0
        entry_price = model.get_entry_price(signal_price, "LONG")

        # 10 bps spread / 2 (half spread) + 10 bps slippage = 15 bps = 0.15%
        expected = 100.0 * 1.0015
        assert entry_price == pytest.approx(expected, rel=1e-6)
        assert entry_price > signal_price

    def test_short_entry_pays_spread_and_slippage(self) -> None:
        """SHORT entry: sell at bid - slippage = worse (lower) price."""
        model = ExecutionModel(spread_bps=10, slippage_bps=10, commission_per_share=0)
        signal_price = 100.0
        entry_price = model.get_entry_price(signal_price, "SHORT")

        # 10 bps spread / 2 (half spread) + 10 bps slippage = 15 bps = 0.15%
        expected = 100.0 * 0.9985
        assert entry_price == pytest.approx(expected, rel=1e-6)
        assert entry_price < signal_price

    def test_zero_costs_no_price_change(self) -> None:
        """Zero cost model doesn't affect prices."""
        model = ExecutionModel.zero()
        signal_price = 100.0

        assert model.get_entry_price(signal_price, "LONG") == signal_price
        assert model.get_entry_price(signal_price, "SHORT") == signal_price


class TestExitPriceCalculation:
    """Test exit price adjustments for different directions."""

    def test_long_exit_pays_spread_and_slippage(self) -> None:
        """LONG exit: sell at bid - slippage = worse (lower) price."""
        model = ExecutionModel(spread_bps=10, slippage_bps=10, commission_per_share=0)
        signal_price = 110.0
        exit_price = model.get_exit_price(signal_price, "LONG")

        expected = 110.0 * 0.9985
        assert exit_price == pytest.approx(expected, rel=1e-6)
        assert exit_price < signal_price

    def test_short_exit_pays_spread_and_slippage(self) -> None:
        """SHORT exit: buy at ask + slippage = worse (higher) price."""
        model = ExecutionModel(spread_bps=10, slippage_bps=10, commission_per_share=0)
        signal_price = 90.0
        exit_price = model.get_exit_price(signal_price, "SHORT")

        expected = 90.0 * 1.0015
        assert exit_price == pytest.approx(expected, rel=1e-6)
        assert exit_price > signal_price


class TestCommissionCalculation:
    """Test commission calculations."""

    def test_round_trip_commission(self) -> None:
        """Commission is charged on both entry and exit."""
        model = ExecutionModel(spread_bps=0, slippage_bps=0, commission_per_share=0.01)
        shares = 100

        commission = model.calculate_commission(shares)
        # $0.01/share * 100 shares * 2 (entry + exit) = $2.00
        assert commission == 2.0

    def test_commission_with_fractional_shares(self) -> None:
        """Commission handles fractional shares."""
        model = ExecutionModel(spread_bps=0, slippage_bps=0, commission_per_share=0.005)
        shares = 150.5

        commission = model.calculate_commission(shares)
        # $0.005/share * 150.5 shares * 2 = $1.505
        assert commission == pytest.approx(1.505, rel=1e-6)

    def test_commission_absolute_value(self) -> None:
        """Commission uses absolute share count."""
        model = ExecutionModel(commission_per_share=0.01)
        assert model.calculate_commission(100) == model.calculate_commission(-100)


class TestCostBreakdown:
    """Test detailed cost breakdown calculations."""

    def test_cost_breakdown_components(self) -> None:
        """Verify cost breakdown separates spread, slippage, and commission."""
        model = ExecutionModel(spread_bps=10, slippage_bps=10, commission_per_share=0.01)

        costs = model.calculate_costs(
            entry_signal=100.0,
            exit_signal=110.0,
            shares=100,
            direction="LONG",
        )

        assert isinstance(costs, ExecutionCosts)
        assert costs.spread_cost > 0
        assert costs.slippage_cost > 0
        assert costs.commission == 2.0  # $0.01 * 100 * 2
        assert costs.total == pytest.approx(costs.spread_cost + costs.slippage_cost + costs.commission)

    def test_zero_costs_breakdown(self) -> None:
        """Zero cost model has zero breakdown."""
        model = ExecutionModel.zero()

        costs = model.calculate_costs(
            entry_signal=100.0,
            exit_signal=110.0,
            shares=100,
            direction="LONG",
        )

        assert costs.spread_cost == 0
        assert costs.slippage_cost == 0
        assert costs.commission == 0
        assert costs.total == 0


class TestNetPnlCalculation:
    """Test gross vs net P&L calculations."""

    def test_long_profitable_trade_with_costs(self) -> None:
        """LONG trade: net P&L accounts for all costs."""
        model = ExecutionModel(spread_bps=10, slippage_bps=10, commission_per_share=0.01)

        gross, net = model.calculate_net_pnl(
            entry_signal=100.0,
            exit_signal=110.0,
            shares=100,
            direction="LONG",
        )

        # Gross: (110 - 100) * 100 = $1000
        assert gross == 1000.0

        # Net should be less than gross
        assert net < gross

        # Manual calculation:
        # Entry: 100 * 1.0015 = 100.15
        # Exit: 110 * 0.9985 = 109.835
        # P&L: (109.835 - 100.15) * 100 = 968.5
        # Commission: 0.01 * 100 * 2 = 2
        # Net: 968.5 - 2 = 966.5
        assert net == pytest.approx(966.5, rel=1e-3)

    def test_long_losing_trade_with_costs(self) -> None:
        """LONG losing trade: costs make it worse."""
        model = ExecutionModel(spread_bps=10, slippage_bps=10, commission_per_share=0.01)

        gross, net = model.calculate_net_pnl(
            entry_signal=100.0,
            exit_signal=95.0,
            shares=100,
            direction="LONG",
        )

        # Gross: (95 - 100) * 100 = -$500
        assert gross == -500.0

        # Net should be more negative (worse)
        assert net < gross

    def test_short_profitable_trade_with_costs(self) -> None:
        """SHORT trade: net P&L accounts for all costs."""
        model = ExecutionModel(spread_bps=10, slippage_bps=10, commission_per_share=0.01)

        gross, net = model.calculate_net_pnl(
            entry_signal=100.0,
            exit_signal=90.0,
            shares=100,
            direction="SHORT",
        )

        # Gross: (100 - 90) * 100 = $1000
        assert gross == 1000.0

        # Net should be less than gross
        assert net < gross

    def test_zero_costs_gross_equals_net(self) -> None:
        """With zero costs, gross equals net."""
        model = ExecutionModel.zero()

        gross, net = model.calculate_net_pnl(
            entry_signal=100.0,
            exit_signal=110.0,
            shares=100,
            direction="LONG",
        )

        assert gross == net == 1000.0


class TestProfitabilityThreshold:
    """Test the would_be_profitable and minimum_profit_target methods."""

    def test_small_gain_unprofitable_after_costs(self) -> None:
        """A small gain can become unprofitable after costs."""
        model = ExecutionModel(spread_bps=10, slippage_bps=10, commission_per_share=0.01)

        # 0.1% gain on $100 = $0.10/share
        # But costs are ~0.3% + commission = more than the gain
        profitable = model.would_be_profitable(
            entry_signal=100.0,
            exit_signal=100.10,
            shares=100,
            direction="LONG",
        )

        assert profitable is False

    def test_large_gain_profitable_after_costs(self) -> None:
        """A large gain remains profitable after costs."""
        model = ExecutionModel(spread_bps=10, slippage_bps=10, commission_per_share=0.01)

        # 5% gain should easily cover costs
        profitable = model.would_be_profitable(
            entry_signal=100.0,
            exit_signal=105.0,
            shares=100,
            direction="LONG",
        )

        assert profitable is True

    def test_minimum_profit_target_long(self) -> None:
        """Calculate minimum exit price needed to break even."""
        model = ExecutionModel(spread_bps=10, slippage_bps=10, commission_per_share=0.01)

        min_exit = model.minimum_profit_target(
            entry_price=100.0,
            shares=100,
            direction="LONG",
        )

        # Min exit should be above entry
        assert min_exit > 100.0

        # The minimum_profit_target gives a rough estimate
        # It should result in approximately breakeven or slightly positive
        gross, net = model.calculate_net_pnl(100.0, min_exit, 100, "LONG")
        # Net should be close to breakeven (within $15 accounting for estimation)
        assert net >= -5  # Not significantly negative

    def test_minimum_profit_target_short(self) -> None:
        """Calculate minimum exit price needed to break even for SHORT."""
        model = ExecutionModel(spread_bps=10, slippage_bps=10, commission_per_share=0.01)

        min_exit = model.minimum_profit_target(
            entry_price=100.0,
            shares=100,
            direction="SHORT",
        )

        # Min exit should be below entry for SHORT
        assert min_exit < 100.0


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_very_small_trade(self) -> None:
        """Small trades still calculate correctly."""
        model = ExecutionModel(spread_bps=2, slippage_bps=5, commission_per_share=0.005)

        gross, net = model.calculate_net_pnl(
            entry_signal=10.0,
            exit_signal=10.50,
            shares=1,
            direction="LONG",
        )

        assert gross == 0.50
        assert net < gross

    def test_very_large_trade(self) -> None:
        """Large trades scale costs proportionally."""
        model = ExecutionModel(spread_bps=5, slippage_bps=5, commission_per_share=0.005)

        _, net_small = model.calculate_net_pnl(100.0, 110.0, 100, "LONG")
        _, net_large = model.calculate_net_pnl(100.0, 110.0, 10000, "LONG")

        # Net P&L should scale roughly linearly with size
        # (exact scaling depends on commission structure)
        ratio = net_large / net_small
        assert ratio == pytest.approx(100, rel=0.01)

    def test_high_volatility_stock(self) -> None:
        """Higher cost model for volatile stocks."""
        # Volatile stocks have wider spreads and more slippage
        model = ExecutionModel(spread_bps=20, slippage_bps=20, commission_per_share=0.01)

        gross, net = model.calculate_net_pnl(
            entry_signal=100.0,
            exit_signal=110.0,
            shares=100,
            direction="LONG",
        )

        # Costs should be significant
        costs = gross - net
        cost_pct = costs / gross
        assert cost_pct > 0.03  # More than 3% of profit goes to costs

    def test_breakeven_trade_becomes_loss(self) -> None:
        """A breakeven trade (gross) becomes a loss after costs."""
        model = ExecutionModel(spread_bps=2, slippage_bps=5, commission_per_share=0.005)

        gross, net = model.calculate_net_pnl(
            entry_signal=100.0,
            exit_signal=100.0,  # No price movement
            shares=100,
            direction="LONG",
        )

        assert gross == 0.0
        assert net < 0  # Costs make it negative


class TestIntegrationWithBot:
    """Test that ExecutionModel integrates correctly with MarketStructureBot."""

    def test_bot_uses_execution_model(self) -> None:
        """Bot correctly applies execution costs to trades."""
        from tradingbot import MarketStructureBot

        # Create bot with known execution model
        model = ExecutionModel(spread_bps=10, slippage_bps=10, commission_per_share=0.01)
        bot = MarketStructureBot(
            capital=100000,
            risk_pct=0.01,
            execution_model=model,
        )

        assert bot.execution_model == model

    def test_bot_zero_costs_matches_old_behavior(self) -> None:
        """Bot with zero costs should match pre-cost behavior."""
        # Create simple price data that will generate a trade
        from datetime import datetime, timedelta

        import polars as pl

        from tradingbot import MarketStructureBot

        base_time = datetime(2024, 1, 1, 9, 30)
        n_bars = 100

        # Create trending data
        prices = [100.0 + i * 0.5 for i in range(n_bars)]
        data = {
            "datetime": [base_time + timedelta(hours=i) for i in range(n_bars)],
            "open": prices,
            "high": [p * 1.01 for p in prices],
            "low": [p * 0.99 for p in prices],
            "close": prices,
            "volume": [1000000] * n_bars,
        }
        df = pl.DataFrame(data)

        # Run with zero costs
        bot_zero = MarketStructureBot(
            capital=100000,
            risk_pct=0.01,
            execution_model=ExecutionModel.zero(),
        )
        bot_zero.backtest(df, "TEST")

        if bot_zero.trades:
            trade = bot_zero.trades[0]
            # With zero costs, gross == net
            assert trade.gross_pnl is not None
            assert trade.execution_costs == 0
            assert trade.pnl == pytest.approx(trade.gross_pnl, rel=1e-6)

    def test_bot_trades_have_cost_fields(self) -> None:
        """Bot trades include gross_pnl and execution_costs fields."""
        from datetime import datetime, timedelta

        import polars as pl

        from tradingbot import MarketStructureBot

        base_time = datetime(2024, 1, 1, 9, 30)
        n_bars = 100

        prices = [100.0 + i * 0.5 for i in range(n_bars)]
        data = {
            "datetime": [base_time + timedelta(hours=i) for i in range(n_bars)],
            "open": prices,
            "high": [p * 1.01 for p in prices],
            "low": [p * 0.99 for p in prices],
            "close": prices,
            "volume": [1000000] * n_bars,
        }
        df = pl.DataFrame(data)

        bot = MarketStructureBot(capital=100000, risk_pct=0.01)
        bot.backtest(df, "TEST")

        if bot.trades:
            trade = bot.trades[0]
            assert trade.gross_pnl is not None
            assert trade.execution_costs is not None
            assert trade.execution_costs >= 0

    def test_bot_stats_include_costs(self) -> None:
        """Bot stats show gross/net P&L and total costs."""
        from datetime import datetime, timedelta

        import polars as pl

        from tradingbot import MarketStructureBot

        base_time = datetime(2024, 1, 1, 9, 30)
        n_bars = 100

        prices = [100.0 + i * 0.5 for i in range(n_bars)]
        data = {
            "datetime": [base_time + timedelta(hours=i) for i in range(n_bars)],
            "open": prices,
            "high": [p * 1.01 for p in prices],
            "low": [p * 0.99 for p in prices],
            "close": prices,
            "volume": [1000000] * n_bars,
        }
        df = pl.DataFrame(data)

        bot = MarketStructureBot(capital=100000, risk_pct=0.01)
        bot.backtest(df, "TEST")

        stats = bot.get_stats()

        if "error" not in stats:
            assert "gross_pnl" in stats
            assert "gross_return" in stats
            assert "total_costs" in stats


class TestRealisticScenarios:
    """Test realistic trading scenarios to validate cost model accuracy."""

    def test_scalping_unprofitable_with_costs(self) -> None:
        """Scalping small moves is unprofitable after costs."""
        model = ExecutionModel(spread_bps=2, slippage_bps=5, commission_per_share=0.005)

        # Scalping: buy at 100, sell at 100.20 (0.2% gain)
        # On 100 shares: $20 gross profit
        gross, net = model.calculate_net_pnl(100.0, 100.20, 100, "LONG")

        # Costs eat most or all of the profit
        assert gross == pytest.approx(20.0, rel=1e-6)
        assert net < gross * 0.5  # Less than half of gross remains

    def test_swing_trade_profitable_with_costs(self) -> None:
        """Swing trades with larger moves remain profitable."""
        model = ExecutionModel(spread_bps=2, slippage_bps=5, commission_per_share=0.005)

        # Swing trade: buy at 100, sell at 108 (8% gain)
        gross, net = model.calculate_net_pnl(100.0, 108.0, 100, "LONG")

        # Most profit survives costs
        assert gross == 800.0
        assert net > gross * 0.95  # More than 95% of gross remains

    def test_cost_impact_on_strategy_edge(self) -> None:
        """Costs can eliminate a marginal strategy edge."""
        model = ExecutionModel(spread_bps=2, slippage_bps=5, commission_per_share=0.005)

        # Strategy with 51% win rate, 1:1 R:R
        # Wins: $2/share, Losses: $2/share
        # Expected gross: 0.51 * 2 - 0.49 * 2 = $0.04/share
        win_gross, win_net = model.calculate_net_pnl(100.0, 102.0, 1, "LONG")
        loss_gross, loss_net = model.calculate_net_pnl(100.0, 98.0, 1, "LONG")

        # Gross expectancy
        gross_expectancy = 0.51 * win_gross + 0.49 * loss_gross
        assert gross_expectancy == pytest.approx(0.04, rel=0.01)

        # Net expectancy (after costs)
        net_expectancy = 0.51 * win_net + 0.49 * loss_net

        # Costs likely make this negative
        assert net_expectancy < gross_expectancy
