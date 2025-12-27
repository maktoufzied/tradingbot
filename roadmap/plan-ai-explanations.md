# AI Trade Explanations - Implementation Plan

## Overview

Add optional AI-generated explanations when trading signals fire, using Ollama (local LLM). The AI explains why the signal was generated based on market structure, helping users understand and learn from the strategy.

## Example Output

```
🔼 BUY SIGNAL: AAPL @ $185.50
  Entry: $185.50  Stop: $182.30  TP: $191.90  Size: 54.0
  AI: Price broke above swing high at $184.80 after forming higher low
      at $182.30. Bullish structure confirmed with HH+HL pattern.
```

## Prerequisites

```bash
# Install Ollama
brew install ollama

# Pull model (2GB download)
ollama pull llama3.2

# Verify it's running
curl http://localhost:11434/api/tags
```

## Files to Create

### 1. `src/tradingbot/_components/ai.py`

```python
"""AI-powered trade signal explanations using local LLM."""

from collections.abc import Sequence
from typing import Final

import httpx

from .models import SwingPoint

OLLAMA_URL: Final = "http://localhost:11434/api/generate"
TIMEOUT_SECONDS: Final = 5.0

PROMPT_TEMPLATE: Final = """You are a trading analyst. Explain this signal in 2 sentences max.

Symbol: {symbol}
Signal: {direction} at ${entry:.2f}
Stop loss: ${stop:.2f}
Recent swing highs: {highs}
Recent swing lows: {lows}
Current trend: {trend}

Focus on price action and market structure. Be concise. No preamble."""


async def explain_signal(
    symbol: str,
    direction: str,
    entry: float,
    stop: float,
    swings: Sequence[SwingPoint],
    trend: str,
    model: str = "llama3.2",
    base_url: str = OLLAMA_URL,
) -> str:
    """Generate AI explanation for a trading signal.

    Returns empty string if Ollama unavailable or timeout.
    """
    highs = [f"${s.price:.2f}" for s in swings if s.is_high][-3:]
    lows = [f"${s.price:.2f}" for s in swings if not s.is_high][-3:]

    prompt = PROMPT_TEMPLATE.format(
        symbol=symbol,
        direction=direction,
        entry=entry,
        stop=stop,
        highs=", ".join(highs) or "N/A",
        lows=", ".join(lows) or "N/A",
        trend=trend,
    )

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                base_url,
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                },
                timeout=TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            return response.json().get("response", "").strip()
    except Exception:
        return ""


def is_ollama_available(base_url: str = "http://localhost:11434") -> bool:
    """Check if Ollama server is running."""
    try:
        response = httpx.get(f"{base_url}/api/tags", timeout=2.0)
        return response.status_code == 200
    except Exception:
        return False
```

## Files to Modify

### 2. `src/tradingbot/_components/config.py`

Add new dataclass and update config loading:

```python
@dataclass
class AIConfig:
    """AI explanation settings."""
    enabled: bool = False
    model: str = "llama3.2"
    url: str = "http://localhost:11434/api/generate"


def get_ai_config() -> AIConfig:
    """Load AI config from tradingbot.toml."""
    data = _load_config()
    ai_data = data.get("tradingbot", {}).get("ai", {})
    return AIConfig(
        enabled=ai_data.get("enabled", False),
        model=ai_data.get("model", "llama3.2"),
        url=ai_data.get("url", "http://localhost:11434/api/generate"),
    )
```

### 3. `tradingbot.toml`

Add AI configuration section:

```toml
[tradingbot.ai]
enabled = false          # Set to true to enable AI explanations
model = "llama3.2"       # Ollama model name
# url = "http://localhost:11434/api/generate"  # Custom Ollama URL
```

### 4. `src/tradingbot/_components/live.py`

In `_open_position()` method, after signal fires and before/after order submission:

```python
from . import ai
from .config import get_ai_config

# At class init or start:
self._ai_config = get_ai_config()
self._ai_available = ai.is_ollama_available() if self._ai_config.enabled else False

# In _open_position(), after calculating swings and before logging:
explanation = ""
if self._ai_available:
    explanation = await ai.explain_signal(
        symbol=bar.symbol,
        direction=direction,
        entry=price,
        stop=stop,
        swings=swings,
        trend=str(details.get("trend", "N/A")),
        model=self._ai_config.model,
        base_url=self._ai_config.url,
    )

# Pass explanation to logging
if self._tui:
    self._tui.log_signal(..., explanation=explanation)
else:
    console.print(f"  Entry: ${price:.2f}  Stop: ${stop:.2f}  TP: ${tp:.2f}  Size: {size:.2f}")
    if explanation:
        console.print(f"  [dim italic]AI: {explanation}[/dim italic]")
```

### 5. `src/tradingbot/_components/tui.py`

Update `log_signal()` method to accept and display explanation:

```python
def log_signal(
    self,
    direction: Direction,
    symbol: str,
    entry: float,
    stop: float,
    tp: float,
    size: float,
    blocked: bool = False,
    reason: str = "",
    was_capped: bool = False,
    explanation: str = "",  # New parameter
) -> None:
    """Log a trading signal."""
    # ... existing code ...

    if not blocked and explanation:
        self._signal_log.write(f"  [dim italic]AI: {explanation}[/dim italic]")
```

## Error Handling

1. **Ollama not running**: Check once at startup with `is_ollama_available()`. If not available, set `self._ai_available = False` and skip all AI calls.

2. **Timeout**: `explain_signal()` has 5 second timeout. Returns empty string on timeout - trade execution is not blocked.

3. **Model not found**: Ollama returns error, caught by exception handler, returns empty string.

4. **Network errors**: All exceptions caught, logged once, returns empty string.

## Testing

```python
# tests/test_ai.py

import pytest
from tradingbot._components.ai import explain_signal, is_ollama_available
from tradingbot._components.models import SwingPoint
from datetime import datetime

@pytest.mark.asyncio
async def test_explain_signal_returns_string():
    """Test that explain_signal returns a non-empty string when Ollama is available."""
    if not is_ollama_available():
        pytest.skip("Ollama not running")

    swings = [
        SwingPoint(datetime.now(), 100.0, True, 0),
        SwingPoint(datetime.now(), 95.0, False, 1),
    ]

    result = await explain_signal(
        symbol="TEST",
        direction="LONG",
        entry=98.0,
        stop=94.0,
        swings=swings,
        trend="BULLISH",
    )

    assert isinstance(result, str)
    assert len(result) > 0


@pytest.mark.asyncio
async def test_explain_signal_handles_unavailable_ollama():
    """Test graceful handling when Ollama is not available."""
    result = await explain_signal(
        symbol="TEST",
        direction="LONG",
        entry=98.0,
        stop=94.0,
        swings=[],
        trend="BULLISH",
        base_url="http://localhost:99999/api/generate",  # Invalid URL
    )

    assert result == ""
```

## Dependencies

Add to `pyproject.toml`:

```toml
dependencies = [
    # ... existing ...
    "httpx>=0.27.0",
]
```

Note: httpx may already be installed as a transitive dependency.

## CLI Flag (Optional Enhancement)

Add `--ai` flag to enable AI explanations from command line:

```python
parser.add_argument(
    "--ai",
    action="store_true",
    help="Enable AI-powered signal explanations (requires Ollama)",
)
```

This would override the config file setting for quick testing.

## Future Enhancements

1. **Caching**: Cache explanations for identical market conditions to reduce API calls
2. **Multiple models**: Support different models for different use cases
3. **Confidence scoring**: Ask AI to rate signal confidence 1-10
4. **Post-trade analysis**: Generate explanation after trade closes on why it won/lost
5. **Batch analysis**: End-of-day summary of all signals and patterns
