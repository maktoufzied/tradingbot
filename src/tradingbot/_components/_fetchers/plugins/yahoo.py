import pandas as pd
import polars as pl
import yfinance as yf

from ..protocol import DataFetcherProtocol


class YahooFinanceFetcher(DataFetcherProtocol):
    """Yahoo Finance data fetcher.

    Supported symbols: Stocks (AAPL), ETFs (SPY), Crypto (BTC-USD), Forex (EURUSD=X), Indices (^GSPC)
    """

    INTERVALS: dict[str, str] = {
        "1m": "1m",  # Last 7 days only
        "5m": "5m",  # Last 60 days only
        "15m": "15m",  # Last 60 days only
        "30m": "30m",  # Last 60 days only
        "1h": "1h",  # Last 730 days
        "1d": "1d",  # Full history
        "1wk": "1wk",  # Full history
    }

    @property
    def name(self) -> str:
        return "yahoo"

    def fetch(
        self,
        symbol: str,
        start_date: str | None = None,
        end_date: str | None = None,
        period: str = "2y",
        interval: str = "1d",
    ) -> pl.DataFrame:
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
        pdf["datetime"] = pdf["datetime"].dt.tz_localize(None)

        df: pl.DataFrame = pl.from_pandas(pdf)
        print(f"[YAHOO] {symbol}: Got {len(df)} bars ({df['datetime'][0].date()} to {df['datetime'][-1].date()})")
        return df
