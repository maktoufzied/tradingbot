from abc import ABC, abstractmethod

import polars as pl


class DataFetcherProtocol(ABC):
    """Abstract protocol for data fetchers. Implement this to add new data sources."""

    @abstractmethod
    def fetch(
        self,
        symbol: str,
        start_date: str | None = None,
        end_date: str | None = None,
        period: str = "2y",
        interval: str = "1d",
    ) -> pl.DataFrame:
        """Fetch OHLCV data for a symbol.

        Returns DataFrame with columns: datetime, open, high, low, close, volume
        """
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for this fetcher."""
        ...
