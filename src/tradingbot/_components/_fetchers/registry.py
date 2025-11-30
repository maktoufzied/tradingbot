from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import polars as pl

from .cache import CachedFetcher
from .protocol import DataFetcherProtocol


class FetcherRegistry:
    """Dependency injection registry for data fetchers."""

    _instance: FetcherRegistry | None = None
    _fetchers: dict[str, DataFetcherProtocol]
    _default: str | None

    def __new__(cls) -> FetcherRegistry:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._fetchers = {}
            cls._instance._default = None
        return cls._instance

    def register(self, fetcher: DataFetcherProtocol, default: bool = False) -> None:
        self._fetchers[fetcher.name] = fetcher
        if default or self._default is None:
            self._default = fetcher.name

    def get(self, name: str | None = None) -> DataFetcherProtocol:
        key: str = name or self._default or ""
        if key not in self._fetchers:
            raise KeyError(f"Fetcher '{key}' not registered. Available: {list(self._fetchers.keys())}")
        return self._fetchers[key]

    def list_fetchers(self) -> list[str]:
        return list(self._fetchers.keys())

    @property
    def default_fetcher(self) -> str | None:
        return self._default


class DataFetcher:
    """Facade for fetching data using registered adapters."""

    @staticmethod
    def fetch(
        symbol: str,
        start_date: str | None = None,
        end_date: str | None = None,
        period: str = "2y",
        interval: str = "1d",
        fetcher: str | None = None,
        use_cache: bool = True,
    ) -> pl.DataFrame:
        registry: FetcherRegistry = FetcherRegistry()
        adapter: DataFetcherProtocol = registry.get(fetcher)

        if use_cache:
            cached_adapter = CachedFetcher(adapter)
            return cached_adapter.fetch(symbol, start_date, end_date, period, interval)

        return adapter.fetch(symbol, start_date, end_date, period, interval)

    @staticmethod
    def fetch_multiple(
        symbols: list[str], max_workers: int = 5, fetcher: str | None = None, **kwargs: Any
    ) -> dict[str, pl.DataFrame]:
        data: dict[str, pl.DataFrame] = {}

        def fetch_one(sym: str) -> tuple[str, pl.DataFrame | None]:
            try:
                return sym, DataFetcher.fetch(sym, fetcher=fetcher, **kwargs)
            except Exception as e:
                print(f"Error fetching {sym}: {e}")
                return sym, None

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(fetch_one, sym): sym for sym in symbols}
            for future in as_completed(futures):
                sym, df = future.result()
                if df is not None:
                    data[sym] = df

        return data


def get_registry() -> FetcherRegistry:
    return FetcherRegistry()
