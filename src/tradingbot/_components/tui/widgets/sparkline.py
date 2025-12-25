"""Sparkline widget - Mini chart using Unicode block characters."""

from rich.text import Text
from textual.reactive import reactive
from textual.widget import Widget

from ..theme import THEME


class Sparkline(Widget):
    """Mini chart using Unicode block characters.

    Displays price history as a single-line sparkline chart.
    Colors based on overall trend (up=green, down=red) or uses
    a specified trend color.
    """

    DEFAULT_CSS = """
    Sparkline {
        height: 1;
        width: 100%;
    }
    """

    BLOCKS = " \u2581\u2582\u2583\u2584\u2585\u2586\u2587\u2588"

    data: reactive[list[float]] = reactive(list, init=False)
    trend_color: reactive[str | None] = reactive(None)

    def __init__(
        self,
        data: list[float] | None = None,
        trend_color: str | None = None,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self.data = data or []
        self.trend_color = trend_color

    def render(self) -> Text:
        """Render the sparkline."""
        if not self.data or len(self.data) < 2:
            width = self.size.width or 40
            return Text("\u2500" * width, style=THEME.text_dim)

        # Normalize data to 0-8 range for block selection
        min_val = min(self.data)
        max_val = max(self.data)
        range_val = max_val - min_val if max_val != min_val else 1.0

        # Sample data to fit width
        width = self.size.width or 40
        if len(self.data) > width:
            # Downsample: take evenly spaced points
            step = len(self.data) / width
            sampled = [self.data[min(int(i * step), len(self.data) - 1)] for i in range(width)]
        else:
            sampled = self.data

        # Determine color based on trend (first vs last price)
        if self.trend_color:
            color = self.trend_color
        else:
            # Auto-detect trend from data
            first_price = self.data[0]
            last_price = self.data[-1]
            if last_price > first_price:
                color = THEME.positive  # Green for uptrend
            elif last_price < first_price:
                color = THEME.negative  # Red for downtrend
            else:
                color = THEME.neutral  # Cyan for flat

        # Build sparkline - all same color for cleaner look
        text = Text()
        for val in sampled:
            # Normalize to 0-1
            normalized = (val - min_val) / range_val

            # Select block character (0-8 index)
            block_idx = int(normalized * 8)
            block_idx = max(0, min(8, block_idx))
            char = self.BLOCKS[block_idx]

            text.append(char, style=color)

        return text

    def watch_data(self) -> None:
        """React to data changes."""
        self.refresh()

    def update_data(self, new_data: list[float]) -> None:
        """Update sparkline data."""
        self.data = new_data

    def append_value(self, value: float, max_points: int = 60) -> None:
        """Append a value, keeping max_points history."""
        current = list(self.data)
        current.append(value)
        if len(current) > max_points:
            current = current[-max_points:]
        self.data = current
