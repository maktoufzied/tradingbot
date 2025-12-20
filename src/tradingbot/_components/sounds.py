"""Cross-platform sound notifications for trading events."""

import subprocess
import sys
from typing import Final

# Sound types
BUY: Final = "buy"
SELL: Final = "sell"
PROFIT: Final = "profit"
LOSS: Final = "loss"


def _play_system_bell() -> None:
    """Play system bell (works on all platforms)."""
    print("\a", end="", flush=True)


def _play_macos_sound(sound_name: str) -> None:
    """Play macOS system sound."""
    sound_path = f"/System/Library/Sounds/{sound_name}.aiff"
    subprocess.Popen(
        ["afplay", sound_path],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def play(sound_type: str) -> None:
    """Play a notification sound.

    Args:
        sound_type: One of 'buy', 'sell', 'profit', 'loss'
    """
    if sys.platform == "darwin":
        # macOS - use system sounds
        sounds = {
            BUY: "Blow",  # Ascending tone for buy
            SELL: "Pop",  # Pop for sell
            PROFIT: "Glass",  # Pleasant chime for profit
            LOSS: "Basso",  # Low tone for loss
        }
        sound_name = sounds.get(sound_type, "Ping")
        _play_macos_sound(sound_name)
    else:
        # Linux/Windows - use system bell
        _play_system_bell()
