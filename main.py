"""
MARKET STRUCTURE TRADING BOT
============================

SETUP:
------
uv sync

USAGE:
------
uv run main.py

TEST:
-----
uv run pytest
"""

from tradingbot import run_single_backtest

if __name__ == "__main__":
    # Example 1: Single stock backtest
    run_single_backtest(
        symbol="APLD",  # S&P 500 ETF
        period="3mo",  # 2 years of data
        interval="1d",  # Daily candles
        capital=100000,  # Starting capital
        risk=0.01,  # 1% risk per trade
        rr=2.0,  # 2:1 reward-to-risk
    )

    # Example 2: Multiple symbols comparison (uncomment to run)
    # run_multi_backtest(
    #     symbols=["AAPL", "MSFT", "GOOGL", "TSLA",
    #     period="1y",
    #     interval="1d"
    # )

    # Example 3: Crypto backtest (uncomment to run)
    # run_single_backtest("BTC-USD", period="1y", interval="1d")

    # Example 4: Forex backtest (uncomment to run)
    # run_single_backtest("EURUSD=X", period="1y", interval="1d")
