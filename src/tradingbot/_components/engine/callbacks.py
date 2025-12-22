"""Callback system for engine events."""

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TypeVar

from .events import (
    BarEvent,
    EngineStartedEvent,
    EngineStoppedEvent,
    MessageEvent,
    SignalEvent,
    StatsUpdatedEvent,
    TradeClosedEvent,
)

T = TypeVar("T")
EventCallback = Callable[[T], None] | Callable[[T], Awaitable[None]]


@dataclass
class EngineCallbacks:
    """Container for engine event callbacks.

    Supports multiple callbacks per event. Callbacks can be sync or async.

    Example:
        callbacks = EngineCallbacks()

        @callbacks.on_bar
        def handle_bar(event: BarEvent):
            print(f"{event.bar.symbol} @ {event.bar.close}")

        @callbacks.on_signal
        async def handle_signal(event: SignalEvent):
            await log_to_db(event)

        engine = TradingEngine(..., callbacks=callbacks)
    """

    _on_started: list[EventCallback[EngineStartedEvent]] = field(default_factory=list)
    _on_stopped: list[EventCallback[EngineStoppedEvent]] = field(default_factory=list)
    _on_message: list[EventCallback[MessageEvent]] = field(default_factory=list)
    _on_bar: list[EventCallback[BarEvent]] = field(default_factory=list)
    _on_signal: list[EventCallback[SignalEvent]] = field(default_factory=list)
    _on_trade_closed: list[EventCallback[TradeClosedEvent]] = field(default_factory=list)
    _on_stats_updated: list[EventCallback[StatsUpdatedEvent]] = field(default_factory=list)

    def on_started[C: EventCallback[EngineStartedEvent]](self, cb: C) -> C:
        self._on_started.append(cb)
        return cb

    def on_stopped[C: EventCallback[EngineStoppedEvent]](self, cb: C) -> C:
        self._on_stopped.append(cb)
        return cb

    def on_message[C: EventCallback[MessageEvent]](self, cb: C) -> C:
        self._on_message.append(cb)
        return cb

    def on_bar[C: EventCallback[BarEvent]](self, cb: C) -> C:
        self._on_bar.append(cb)
        return cb

    def on_signal[C: EventCallback[SignalEvent]](self, cb: C) -> C:
        self._on_signal.append(cb)
        return cb

    def on_trade_closed[C: EventCallback[TradeClosedEvent]](self, cb: C) -> C:
        self._on_trade_closed.append(cb)
        return cb

    def on_stats_updated[C: EventCallback[StatsUpdatedEvent]](self, cb: C) -> C:
        self._on_stats_updated.append(cb)
        return cb

    async def emit_started(self, event: EngineStartedEvent) -> None:
        await self._emit(self._on_started, event)

    async def emit_stopped(self, event: EngineStoppedEvent) -> None:
        await self._emit(self._on_stopped, event)

    async def emit_message(self, event: MessageEvent) -> None:
        await self._emit(self._on_message, event)

    async def emit_bar(self, event: BarEvent) -> None:
        await self._emit(self._on_bar, event)

    async def emit_signal(self, event: SignalEvent) -> None:
        await self._emit(self._on_signal, event)

    async def emit_trade_closed(self, event: TradeClosedEvent) -> None:
        await self._emit(self._on_trade_closed, event)

    async def emit_stats_updated(self, event: StatsUpdatedEvent) -> None:
        await self._emit(self._on_stats_updated, event)

    async def _emit[E](self, callbacks: list[EventCallback[E]], event: E) -> None:
        """Emit an event to all registered callbacks."""
        for cb in callbacks:
            result = cb(event)
            if inspect.isawaitable(result):
                await result
