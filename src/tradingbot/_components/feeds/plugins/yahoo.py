"""Yahoo Finance historical data feed."""

from collections.abc import Collection

import pandas as pd
import polars as pl
import yfinance as yf

from tradingbot.interfaces import DataFeedProtocol


class YahooFeed(DataFeedProtocol):
    """Yahoo Finance feed for historical data only.

    Yahoo Finance does not provide real-time streaming data.
    Use AlpacaFeed for live trading, or ReplayFeed to simulate
    live trading with Yahoo's historical data.
    """

    @property
    def name(self) -> str:
        return "yahoo"

    @property
    def is_connected(self) -> bool:
        return False

    async def subscribe(self, symbols: Collection[str], on_bar: object) -> None:
        raise NotImplementedError("YahooFeed does not support real-time streaming. Use AlpacaFeed or ReplayFeed.")

    async def unsubscribe(self, symbols: Collection[str]) -> None:
        pass

    async def start(self) -> None:
        raise NotImplementedError("YahooFeed does not support real-time streaming. Use AlpacaFeed or ReplayFeed.")

    async def stop(self) -> None:
        pass

    def history(
        self,
        symbol: str,
        start_date: str | None = None,
        end_date: str | None = None,
        period: str = "2y",
        interval: str = "1d",
    ) -> pl.DataFrame:
        """Fetch historical bar data from Yahoo Finance."""
        ticker: yf.Ticker = yf.Ticker(symbol)
        pdf: pd.DataFrame

        if start_date and end_date:
            pdf = ticker.history(start=start_date, end=end_date, interval=interval)
        else:
            pdf = ticker.history(period=period, interval=interval)

        if pdf.empty:
            raise ValueError(f"No data found for {symbol}")

        pdf.columns = pdf.columns.str.lower()
        pdf = pdf[["open", "high", "low", "close", "volume"]].copy()
        pdf.dropna(inplace=True)

        # Convert pandas index to datetime column for polars
        pdf = pdf.reset_index()
        pdf.columns = ["datetime", "open", "high", "low", "close", "volume"]
        # Remove timezone info for consistency
        pdf["datetime"] = pd.to_datetime(pdf["datetime"]).dt.tz_localize(None)

        return pl.from_pandas(pdf)
