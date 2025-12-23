"""CLI for cache management."""

import argparse
from datetime import UTC, datetime
from typing import TypedDict

from rich.console import Console
from rich.table import Table

from ._components.cache import CachedFeed, delete_bars, get_db_path, get_storage_stats
from ._components.cache.db import db_connection

console = Console()


class IntervalStats(TypedDict):
    count: int
    earliest: datetime | None
    latest: datetime | None


def get_symbol_stats() -> dict[str, dict[str, IntervalStats]]:
    """Get per-symbol statistics."""
    with db_connection() as conn:
        rows = conn.execute("""
            SELECT symbol, interval, COUNT(*) as count,
                   MIN(datetime) as earliest,
                   MAX(datetime) as latest
            FROM bars
            GROUP BY symbol, interval
            ORDER BY symbol, interval
        """).fetchall()

        stats: dict[str, dict[str, IntervalStats]] = {}
        for row in rows:
            symbol, interval, count, earliest, latest = row
            if symbol not in stats:
                stats[symbol] = {}
            stats[symbol][interval] = {
                "count": count,
                "earliest": earliest,
                "latest": latest,
            }
        return stats


def _utc_to_local(dt: datetime) -> datetime:
    """Convert UTC datetime to local time for display."""
    if dt.tzinfo is None:
        # Assume naive datetime is UTC
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone().replace(tzinfo=None)


def _format_datetime(dt: datetime | None, interval: str) -> str:
    """Format datetime based on interval (show time for intraday).

    Converts UTC stored time to local time for display.
    """
    if dt is None:
        return "-"
    # Convert UTC to local time for display
    local_dt = _utc_to_local(dt)
    # Intraday intervals: show date and time
    if interval in ("1m", "5m", "15m", "30m", "1h"):
        return local_dt.strftime("%Y-%m-%d %H:%M")
    # Daily and above: show date only
    return local_dt.strftime("%Y-%m-%d")


def cmd_stats(args: argparse.Namespace) -> None:
    """Show cache statistics."""
    symbol_stats = get_symbol_stats()

    if not symbol_stats:
        console.print("[dim]Cache is empty[/dim]")
        return

    table = Table(title="Cache Statistics")
    table.add_column("Symbol")
    table.add_column("Interval")
    table.add_column("Bars", justify="right")
    table.add_column("Earliest")
    table.add_column("Latest")

    for symbol in sorted(symbol_stats.keys()):
        for interval, data in sorted(symbol_stats[symbol].items()):
            earliest = data["earliest"]
            latest = data["latest"]
            table.add_row(
                symbol,
                interval,
                str(data["count"]),
                _format_datetime(earliest, interval),
                _format_datetime(latest, interval),
            )

    console.print(table)

    # Summary
    stats = get_storage_stats()
    console.print(f"\nTotal: {stats['total_rows']:,} bars ({stats.get('file_size_mb', 0):.1f} MB)")
    console.print(f"Location: {get_db_path()}")


def cmd_fetch(args: argparse.Namespace) -> None:
    """Fetch and cache data for symbols."""
    if not args.symbols:
        console.print("[red]Error: symbols required[/red]")
        return

    feed = CachedFeed()

    for symbol in args.symbols:
        symbol = symbol.upper()
        console.print(f"[cyan]Fetching {symbol}...[/cyan]")

        if args.refresh:
            deleted = delete_bars(symbol, args.interval)
            if deleted > 0:
                console.print(f"  [dim]Cleared {deleted} cached bars[/dim]")

        df = feed.history(symbol, period=args.period, interval=args.interval, refresh=args.refresh, debug=args.debug)

        # Get updated stats for this symbol
        symbol_stats = get_symbol_stats()
        if symbol in symbol_stats and args.interval in symbol_stats[symbol]:
            data = symbol_stats[symbol][args.interval]
            earliest = data["earliest"]
            latest = data["latest"]
            console.print(
                f"  [green]✓[/green] {len(df)} bars "
                f"({_format_datetime(earliest, args.interval)} → "
                f"{_format_datetime(latest, args.interval)})"
            )
        else:
            console.print(f"  [green]✓[/green] {len(df)} bars")


def cmd_clear(args: argparse.Namespace) -> None:
    """Clear cache for symbol(s)."""
    if not args.symbols:
        console.print("[red]Error: symbols required[/red]")
        return

    for symbol in args.symbols:
        symbol = symbol.upper()
        deleted = delete_bars(symbol, args.interval if args.interval != "all" else None)
        interval_str = args.interval if args.interval != "all" else "all intervals"
        console.print(f"Cleared {deleted} bars for {symbol} ({interval_str})")


def main() -> None:
    """CLI entry point for cache management."""
    parser = argparse.ArgumentParser(
        description="Cache management for market data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # stats command
    stats_parser = subparsers.add_parser("stats", help="Show cache statistics")
    stats_parser.set_defaults(func=cmd_stats)

    # fetch command
    fetch_parser = subparsers.add_parser(
        "fetch",
        help="Fetch and cache data",
        epilog="""
Examples:
  tradingbot-cache fetch AAPL
  tradingbot-cache fetch AAPL QQQ
  tradingbot-cache fetch AAPL --period 5y
  tradingbot-cache fetch AAPL --refresh
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    fetch_parser.add_argument("symbols", nargs="*", help="Symbols to fetch")
    fetch_parser.add_argument("--period", default="1y", help="Data period (default: 1y)")
    fetch_parser.add_argument("--interval", default="1d", help="Data interval (default: 1d)")
    fetch_parser.add_argument("--refresh", action="store_true", help="Force re-fetch from API")
    fetch_parser.add_argument("--debug", action="store_true", help="Show debug info from API")
    fetch_parser.set_defaults(func=cmd_fetch)

    # clear command
    clear_parser = subparsers.add_parser("clear", help="Clear cached data")
    clear_parser.add_argument("symbols", nargs="*", help="Symbols to clear")
    clear_parser.add_argument("--interval", default="all", help="Interval to clear (default: all)")
    clear_parser.set_defaults(func=cmd_clear)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    args.func(args)
