# Random Forest Signal Filter - Implementation Plan

## Overview

Add a machine learning filter that predicts the probability of a trading signal being profitable. The Random Forest classifier is trained on historical backtest data and used to filter out low-probability signals during live trading.

**Goal:** Improve win rate by only taking signals with high predicted probability of success.

## How It Works

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Trading Signal │ ──► │  RF Classifier  │ ──► │  Take Trade?    │
│  (from strategy)│     │  P(profitable)  │     │  P > threshold  │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                               │
                               │ trained on
                               ▼
                        ┌─────────────────┐
                        │ Historical      │
                        │ Backtest Trades │
                        │ (features +     │
                        │  outcomes)      │
                        └─────────────────┘
```

## Training Pipeline

```
1. Run backtest on historical data
         │
         ▼
2. Extract features at each signal
         │
         ▼
3. Label each signal (win=1, loss=0)
         │
         ▼
4. Train RandomForest classifier
         │
         ▼
5. Evaluate on held-out test set
         │
         ▼
6. Save model for live use
```

## Feature Engineering

### Price Action Features
| Feature | Description | Rationale |
|---------|-------------|-----------|
| `rsi` | RSI(14) at signal | Overbought/oversold context |
| `rsi_slope` | RSI change over 5 bars | Momentum direction |
| `adx` | ADX(14) at signal | Trend strength |
| `atr_pct` | ATR / close price | Normalized volatility |
| `bb_position` | (close - bb_lower) / (bb_upper - bb_lower) | Position in Bollinger bands |

### Trend Features
| Feature | Description | Rationale |
|---------|-------------|-----------|
| `ema_dist` | (close - EMA20) / close | Distance from trend |
| `trend_aligned` | Signal direction matches EMA trend | Trend alignment |
| `higher_highs` | Count of HH in last 10 swings | Bullish structure |
| `lower_lows` | Count of LL in last 10 swings | Bearish structure |

### Volume Features
| Feature | Description | Rationale |
|---------|-------------|-----------|
| `volume_ratio` | volume / SMA(volume, 20) | Relative volume |
| `volume_trend` | Volume increasing/decreasing | Conviction |

### Signal-Specific Features
| Feature | Description | Rationale |
|---------|-------------|-----------|
| `dist_to_stop` | (entry - stop) / entry | Risk size |
| `dist_to_tp` | (tp - entry) / entry | Reward size |
| `swing_strength` | How strong was the broken swing | Significance |
| `bars_since_swing` | Bars since swing formed | Freshness |

### Time Features
| Feature | Description | Rationale |
|---------|-------------|-----------|
| `hour` | Hour of day (0-23) | Intraday patterns |
| `day_of_week` | Monday=0 to Friday=4 | Weekly patterns |
| `days_to_earnings` | Days until next earnings | Event risk |

## Files to Create

### 1. `src/tradingbot/_components/ml/__init__.py`

```python
"""Machine learning components for trading."""

from .features import FeatureExtractor
from .filter import SignalFilter

__all__ = ["FeatureExtractor", "SignalFilter"]
```

### 2. `src/tradingbot/_components/ml/features.py`

```python
"""Feature extraction for ML models."""

from dataclasses import dataclass
from typing import Final

import polars as pl

# Feature names for consistent ordering
FEATURE_NAMES: Final = [
    # Price action
    "rsi",
    "rsi_slope",
    "adx",
    "atr_pct",
    "bb_position",
    # Trend
    "ema_dist",
    "trend_aligned",
    "higher_highs",
    "lower_lows",
    # Volume
    "volume_ratio",
    "volume_trend",
    # Signal-specific
    "dist_to_stop",
    "dist_to_tp",
    "swing_strength",
    "bars_since_swing",
    # Time
    "hour",
    "day_of_week",
]


@dataclass
class SignalFeatures:
    """Features extracted at signal time."""

    # Price action
    rsi: float
    rsi_slope: float
    adx: float
    atr_pct: float
    bb_position: float

    # Trend
    ema_dist: float
    trend_aligned: int  # 1 if aligned, 0 if not
    higher_highs: int
    lower_lows: int

    # Volume
    volume_ratio: float
    volume_trend: int  # 1 if increasing, -1 if decreasing, 0 if flat

    # Signal-specific
    dist_to_stop: float
    dist_to_tp: float
    swing_strength: float
    bars_since_swing: int

    # Time
    hour: int
    day_of_week: int

    def to_array(self) -> list[float]:
        """Convert to array for model input."""
        return [
            self.rsi,
            self.rsi_slope,
            self.adx,
            self.atr_pct,
            self.bb_position,
            self.ema_dist,
            float(self.trend_aligned),
            float(self.higher_highs),
            float(self.lower_lows),
            self.volume_ratio,
            float(self.volume_trend),
            self.dist_to_stop,
            self.dist_to_tp,
            self.swing_strength,
            float(self.bars_since_swing),
            float(self.hour),
            float(self.day_of_week),
        ]


class FeatureExtractor:
    """Extract ML features from market data at signal time."""

    def __init__(self, df: pl.DataFrame):
        """Initialize with market data DataFrame.

        DataFrame must have columns: timestamp, open, high, low, close, volume
        and indicator columns: rsi, adx, atr, ema_20, bb_upper, bb_lower
        """
        self.df = df

    def extract(
        self,
        idx: int,
        direction: int,  # 1 for long, -1 for short
        entry: float,
        stop: float,
        tp: float,
        swing_idx: int,
    ) -> SignalFeatures:
        """Extract features at signal bar index."""
        row = self.df.row(idx, named=True)
        ts = row["timestamp"]

        # Price action features
        rsi = row.get("rsi", 50.0)
        rsi_prev = self.df["rsi"][max(0, idx - 5)] if "rsi" in self.df.columns else 50.0
        rsi_slope = rsi - rsi_prev

        adx = row.get("adx", 25.0)
        atr = row.get("atr", 1.0)
        atr_pct = atr / row["close"]

        bb_upper = row.get("bb_upper", row["close"] * 1.02)
        bb_lower = row.get("bb_lower", row["close"] * 0.98)
        bb_range = bb_upper - bb_lower
        bb_position = (row["close"] - bb_lower) / bb_range if bb_range > 0 else 0.5

        # Trend features
        ema_20 = row.get("ema_20", row["close"])
        ema_dist = (row["close"] - ema_20) / row["close"]

        # Trend aligned: long signal when price > EMA, short when price < EMA
        price_above_ema = row["close"] > ema_20
        trend_aligned = 1 if (direction == 1 and price_above_ema) or (direction == -1 and not price_above_ema) else 0

        # Count recent swing patterns (simplified)
        higher_highs = self._count_higher_highs(idx)
        lower_lows = self._count_lower_lows(idx)

        # Volume features
        vol = row["volume"]
        vol_ma = self.df["volume"][max(0, idx - 20) : idx].mean() if idx > 0 else vol
        volume_ratio = vol / vol_ma if vol_ma > 0 else 1.0

        vol_recent = self.df["volume"][max(0, idx - 5) : idx].mean() if idx > 5 else vol
        vol_prior = self.df["volume"][max(0, idx - 10) : max(0, idx - 5)].mean() if idx > 10 else vol
        volume_trend = 1 if vol_recent > vol_prior * 1.1 else (-1 if vol_recent < vol_prior * 0.9 else 0)

        # Signal-specific
        dist_to_stop = abs(entry - stop) / entry
        dist_to_tp = abs(tp - entry) / entry

        swing_price = self.df["high" if direction == 1 else "low"][swing_idx]
        swing_strength = abs(swing_price - row["close"]) / row["close"]
        bars_since_swing = idx - swing_idx

        # Time features
        hour = ts.hour if hasattr(ts, "hour") else 12
        day_of_week = ts.weekday() if hasattr(ts, "weekday") else 2

        return SignalFeatures(
            rsi=rsi,
            rsi_slope=rsi_slope,
            adx=adx,
            atr_pct=atr_pct,
            bb_position=bb_position,
            ema_dist=ema_dist,
            trend_aligned=trend_aligned,
            higher_highs=higher_highs,
            lower_lows=lower_lows,
            volume_ratio=volume_ratio,
            volume_trend=volume_trend,
            dist_to_stop=dist_to_stop,
            dist_to_tp=dist_to_tp,
            swing_strength=swing_strength,
            bars_since_swing=bars_since_swing,
            hour=hour,
            day_of_week=day_of_week,
        )

    def _count_higher_highs(self, idx: int, lookback: int = 50) -> int:
        """Count higher highs in recent price action."""
        highs = self.df["high"][max(0, idx - lookback) : idx + 1].to_list()
        if len(highs) < 3:
            return 0

        count = 0
        for i in range(2, len(highs)):
            if highs[i] > highs[i - 1] > highs[i - 2]:
                count += 1
        return min(count, 5)  # Cap at 5

    def _count_lower_lows(self, idx: int, lookback: int = 50) -> int:
        """Count lower lows in recent price action."""
        lows = self.df["low"][max(0, idx - lookback) : idx + 1].to_list()
        if len(lows) < 3:
            return 0

        count = 0
        for i in range(2, len(lows)):
            if lows[i] < lows[i - 1] < lows[i - 2]:
                count += 1
        return min(count, 5)  # Cap at 5
```

### 3. `src/tradingbot/_components/ml/filter.py`

```python
"""Random Forest signal filter."""

import logging
import pickle
from pathlib import Path
from typing import Final

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import cross_val_score, train_test_split
from sklearn.metrics import classification_report, confusion_matrix

from .features import SignalFeatures, FEATURE_NAMES

logger = logging.getLogger(__name__)

DEFAULT_MODEL_PATH: Final = Path.home() / ".cache" / "tradingbot" / "models" / "signal_filter.pkl"


class SignalFilter:
    """Random Forest classifier for filtering trading signals."""

    def __init__(
        self,
        n_estimators: int = 100,
        max_depth: int = 10,
        min_samples_leaf: int = 20,
        threshold: float = 0.55,
        random_state: int = 42,
    ):
        """Initialize the signal filter.

        Args:
            n_estimators: Number of trees in the forest
            max_depth: Maximum depth of trees (prevents overfitting)
            min_samples_leaf: Minimum samples per leaf (prevents overfitting)
            threshold: Probability threshold for accepting signals
            random_state: Random seed for reproducibility
        """
        self.model = RandomForestClassifier(
            n_estimators=n_estimators,
            max_depth=max_depth,
            min_samples_leaf=min_samples_leaf,
            random_state=random_state,
            n_jobs=-1,
            class_weight="balanced",  # Handle imbalanced win/loss
        )
        self.threshold = threshold
        self.is_fitted = False
        self.feature_names = FEATURE_NAMES

    def train(
        self,
        features: list[SignalFeatures],
        outcomes: list[bool],
        test_size: float = 0.2,
    ) -> dict[str, float]:
        """Train the classifier on historical signals.

        Args:
            features: List of SignalFeatures at each signal
            outcomes: List of outcomes (True=profitable, False=loss)
            test_size: Fraction of data to hold out for testing

        Returns:
            Dictionary of evaluation metrics
        """
        if len(features) < 50:
            raise ValueError(f"Need at least 50 training samples, got {len(features)}")

        # Convert to arrays
        X = np.array([f.to_array() for f in features])
        y = np.array(outcomes, dtype=int)

        logger.info(f"Training on {len(X)} samples ({sum(y)} wins, {len(y) - sum(y)} losses)")

        # Split train/test
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=42, stratify=y
        )

        # Train
        self.model.fit(X_train, y_train)
        self.is_fitted = True

        # Evaluate
        y_pred = self.model.predict(X_test)
        y_proba = self.model.predict_proba(X_test)[:, 1]

        # Metrics
        accuracy = (y_pred == y_test).mean()

        # Precision at threshold
        y_pred_threshold = (y_proba >= self.threshold).astype(int)
        signals_taken = y_pred_threshold.sum()
        if signals_taken > 0:
            precision_at_threshold = y_test[y_pred_threshold == 1].mean()
        else:
            precision_at_threshold = 0.0

        # Cross-validation score
        cv_scores = cross_val_score(self.model, X, y, cv=5, scoring="accuracy")

        metrics = {
            "accuracy": accuracy,
            "cv_accuracy_mean": cv_scores.mean(),
            "cv_accuracy_std": cv_scores.std(),
            "precision_at_threshold": precision_at_threshold,
            "signals_taken_pct": signals_taken / len(y_test),
            "test_samples": len(y_test),
            "train_samples": len(y_train),
        }

        # Log feature importance
        self._log_feature_importance()

        logger.info(f"Training complete: accuracy={accuracy:.3f}, precision@{self.threshold}={precision_at_threshold:.3f}")

        return metrics

    def predict_probability(self, features: SignalFeatures) -> float:
        """Predict probability that a signal will be profitable.

        Args:
            features: Features extracted at signal time

        Returns:
            Probability between 0 and 1
        """
        if not self.is_fitted:
            logger.warning("Model not fitted, returning 0.5")
            return 0.5

        X = np.array([features.to_array()])
        proba = self.model.predict_proba(X)[0][1]
        return float(proba)

    def should_take_signal(self, features: SignalFeatures) -> tuple[bool, float]:
        """Decide whether to take a trading signal.

        Args:
            features: Features extracted at signal time

        Returns:
            Tuple of (should_take, probability)
        """
        proba = self.predict_probability(features)
        return proba >= self.threshold, proba

    def _log_feature_importance(self) -> None:
        """Log feature importance rankings."""
        if not self.is_fitted:
            return

        importances = self.model.feature_importances_
        sorted_idx = np.argsort(importances)[::-1]

        logger.info("Feature importance:")
        for i, idx in enumerate(sorted_idx[:10]):
            logger.info(f"  {i + 1}. {self.feature_names[idx]}: {importances[idx]:.4f}")

    def get_feature_importance(self) -> dict[str, float]:
        """Get feature importance as dictionary."""
        if not self.is_fitted:
            return {}

        return dict(zip(self.feature_names, self.model.feature_importances_))

    def save(self, path: Path | None = None) -> None:
        """Save model to disk."""
        path = path or DEFAULT_MODEL_PATH
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "wb") as f:
            pickle.dump(
                {
                    "model": self.model,
                    "threshold": self.threshold,
                    "feature_names": self.feature_names,
                    "is_fitted": self.is_fitted,
                },
                f,
            )
        logger.info(f"Model saved to {path}")

    @classmethod
    def load(cls, path: Path | None = None) -> "SignalFilter":
        """Load model from disk."""
        path = path or DEFAULT_MODEL_PATH

        if not path.exists():
            logger.warning(f"No model found at {path}, returning untrained filter")
            return cls()

        with open(path, "rb") as f:
            data = pickle.load(f)

        filter = cls(threshold=data["threshold"])
        filter.model = data["model"]
        filter.is_fitted = data["is_fitted"]
        filter.feature_names = data["feature_names"]

        logger.info(f"Model loaded from {path}")
        return filter
```

### 4. `src/tradingbot/_components/ml/trainer.py`

```python
"""Training pipeline for ML models."""

import logging
from collections.abc import Sequence

import polars as pl

from ..bot import MarketStructureBot
from ..feeds import DataFeed
from ..models import Trade, TradeStatus
from .features import FeatureExtractor, SignalFeatures
from .filter import SignalFilter

logger = logging.getLogger(__name__)


def generate_training_data(
    symbols: Sequence[str],
    period: str = "2y",
    interval: str = "1h",
    risk_pct: float = 0.01,
    rr_ratio: float = 2.0,
) -> tuple[list[SignalFeatures], list[bool]]:
    """Generate training data from backtests on multiple symbols.

    Args:
        symbols: List of symbols to backtest
        period: History period
        interval: Bar interval
        risk_pct: Risk per trade
        rr_ratio: Reward/risk ratio

    Returns:
        Tuple of (features_list, outcomes_list)
    """
    all_features: list[SignalFeatures] = []
    all_outcomes: list[bool] = []

    for symbol in symbols:
        logger.info(f"Generating training data for {symbol}")

        try:
            features, outcomes = _generate_for_symbol(
                symbol, period, interval, risk_pct, rr_ratio
            )
            all_features.extend(features)
            all_outcomes.extend(outcomes)
            logger.info(f"  {symbol}: {len(features)} signals ({sum(outcomes)} wins)")
        except Exception as e:
            logger.warning(f"  {symbol}: Failed - {e}")
            continue

    logger.info(f"Total training data: {len(all_features)} signals")
    return all_features, all_outcomes


def _generate_for_symbol(
    symbol: str,
    period: str,
    interval: str,
    risk_pct: float,
    rr_ratio: float,
) -> tuple[list[SignalFeatures], list[bool]]:
    """Generate training data for a single symbol."""
    # Fetch data
    df = DataFeed.history(symbol, period=period, interval=interval)
    if df.is_empty() or len(df) < 100:
        raise ValueError(f"Insufficient data for {symbol}")

    # Add indicators needed for features
    df = _add_indicators(df)

    # Run backtest
    bot = MarketStructureBot(
        capital=100000,
        risk_pct=risk_pct,
        rr_ratio=rr_ratio,
    )
    bot.backtest(df, symbol)

    if not bot.trades:
        raise ValueError(f"No trades generated for {symbol}")

    # Extract features for each trade
    extractor = FeatureExtractor(df)
    features: list[SignalFeatures] = []
    outcomes: list[bool] = []

    for trade in bot.trades:
        if trade.status not in (TradeStatus.WIN, TradeStatus.LOSS):
            continue  # Skip open trades

        # Find bar index for trade entry
        entry_idx = _find_bar_index(df, trade.entry_time)
        if entry_idx is None:
            continue

        # Find swing index (approximate)
        swing_idx = max(0, entry_idx - 5)  # Simplified

        direction = 1 if trade.direction.value == "LONG" else -1

        try:
            signal_features = extractor.extract(
                idx=entry_idx,
                direction=direction,
                entry=trade.entry,
                stop=trade.stop,
                tp=trade.tp,
                swing_idx=swing_idx,
            )
            features.append(signal_features)
            outcomes.append(trade.status == TradeStatus.WIN)
        except Exception as e:
            logger.debug(f"Failed to extract features for trade: {e}")
            continue

    return features, outcomes


def _add_indicators(df: pl.DataFrame) -> pl.DataFrame:
    """Add technical indicators needed for feature extraction."""
    # RSI
    delta = df["close"].diff()
    gain = delta.clip(lower_bound=0).rolling_mean(14)
    loss = (-delta.clip(upper_bound=0)).rolling_mean(14)
    rs = gain / loss.replace(0, 1e-10)
    rsi = 100 - (100 / (1 + rs))

    # EMA 20
    ema_20 = df["close"].ewm_mean(span=20)

    # ATR
    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift(1)).abs()
    low_close = (df["low"] - df["close"].shift(1)).abs()
    tr = pl.concat([high_low, high_close, low_close], how="horizontal").max_horizontal()
    atr = tr.rolling_mean(14)

    # Bollinger Bands
    sma_20 = df["close"].rolling_mean(20)
    std_20 = df["close"].rolling_std(20)
    bb_upper = sma_20 + (std_20 * 2)
    bb_lower = sma_20 - (std_20 * 2)

    # ADX (simplified)
    adx = pl.Series([25.0] * len(df))  # Placeholder - use proper ADX calculation

    return df.with_columns([
        rsi.alias("rsi"),
        ema_20.alias("ema_20"),
        atr.alias("atr"),
        bb_upper.alias("bb_upper"),
        bb_lower.alias("bb_lower"),
        adx.alias("adx"),
    ])


def _find_bar_index(df: pl.DataFrame, timestamp) -> int | None:
    """Find the bar index closest to a timestamp."""
    for i, ts in enumerate(df["timestamp"]):
        if ts >= timestamp:
            return max(0, i - 1)
    return len(df) - 1


def train_signal_filter(
    symbols: Sequence[str],
    period: str = "2y",
    interval: str = "1h",
    threshold: float = 0.55,
    save_model: bool = True,
) -> tuple[SignalFilter, dict[str, float]]:
    """Train a signal filter on multiple symbols.

    Args:
        symbols: Symbols to train on
        period: History period
        interval: Bar interval
        threshold: Probability threshold for taking signals
        save_model: Whether to save the model to disk

    Returns:
        Tuple of (trained_filter, metrics)
    """
    # Generate training data
    features, outcomes = generate_training_data(symbols, period, interval)

    if len(features) < 50:
        raise ValueError(f"Insufficient training data: {len(features)} samples")

    # Train filter
    filter = SignalFilter(threshold=threshold)
    metrics = filter.train(features, outcomes)

    if save_model:
        filter.save()

    return filter, metrics
```

## Files to Modify

### 1. `src/tradingbot/_components/bot.py`

Add ML filter integration:

```python
from .ml import SignalFilter, FeatureExtractor

class MarketStructureBot:
    def __init__(
        self,
        # ... existing params ...
        ml_filter: SignalFilter | None = None,
        ml_threshold: float = 0.55,
    ):
        # ... existing init ...
        self._ml_filter = ml_filter
        self._ml_threshold = ml_threshold
        self._filtered_signals = 0
        self._total_signals = 0

    def _should_take_signal(
        self,
        df: pl.DataFrame,
        idx: int,
        direction: int,
        entry: float,
        stop: float,
        tp: float,
        swing_idx: int,
    ) -> tuple[bool, float]:
        """Check if signal passes ML filter."""
        self._total_signals += 1

        if self._ml_filter is None:
            return True, 1.0

        extractor = FeatureExtractor(df)
        features = extractor.extract(idx, direction, entry, stop, tp, swing_idx)
        should_take, proba = self._ml_filter.should_take_signal(features)

        if not should_take:
            self._filtered_signals += 1

        return should_take, proba
```

### 2. `src/tradingbot/_components/live.py`

Add ML filter to live trading:

```python
from .ml import SignalFilter

class LiveTrader:
    def __init__(self, ...):
        # ... existing ...
        self._ml_filter = SignalFilter.load() if use_ml_filter else None

    async def _on_signal(self, ...):
        # Before taking trade, check ML filter
        if self._ml_filter:
            should_take, proba = self._ml_filter.should_take_signal(features)
            if not should_take:
                logger.info(f"Signal filtered by ML (P={proba:.2f} < {threshold})")
                return
```

### 3. `src/tradingbot/__init__.py`

Export ML components:

```python
from ._components.ml import SignalFilter, train_signal_filter

__all__ = [
    # ... existing ...
    "SignalFilter",
    "train_signal_filter",
]
```

### 4. `pyproject.toml`

Add scikit-learn dependency:

```toml
dependencies = [
    # ... existing ...
    "scikit-learn>=1.4.0",
]
```

## CLI Commands

### 1. `src/tradingbot/ml_cli.py`

```python
"""CLI for ML model training and evaluation."""

import argparse
import logging

from tradingbot._components.ml.trainer import train_signal_filter
from tradingbot._components.ml.filter import SignalFilter

logging.basicConfig(level=logging.INFO)


def main() -> None:
    parser = argparse.ArgumentParser(description="Train ML signal filter")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Train command
    train_parser = subparsers.add_parser("train", help="Train signal filter")
    train_parser.add_argument(
        "symbols",
        nargs="+",
        help="Symbols to train on (e.g., AAPL MSFT GOOGL)",
    )
    train_parser.add_argument(
        "--period",
        default="2y",
        help="History period (default: 2y)",
    )
    train_parser.add_argument(
        "--interval",
        default="1h",
        help="Bar interval (default: 1h)",
    )
    train_parser.add_argument(
        "--threshold",
        type=float,
        default=0.55,
        help="Probability threshold (default: 0.55)",
    )

    # Evaluate command
    eval_parser = subparsers.add_parser("eval", help="Evaluate trained model")
    eval_parser.add_argument("symbol", help="Symbol to evaluate on")

    # Info command
    subparsers.add_parser("info", help="Show model info and feature importance")

    args = parser.parse_args()

    if args.command == "train":
        print(f"Training on {len(args.symbols)} symbols: {', '.join(args.symbols)}")
        filter, metrics = train_signal_filter(
            symbols=args.symbols,
            period=args.period,
            interval=args.interval,
            threshold=args.threshold,
        )
        print("\nTraining Results:")
        print(f"  Accuracy: {metrics['accuracy']:.1%}")
        print(f"  CV Accuracy: {metrics['cv_accuracy_mean']:.1%} ± {metrics['cv_accuracy_std']:.1%}")
        print(f"  Precision @ {args.threshold}: {metrics['precision_at_threshold']:.1%}")
        print(f"  Signals taken: {metrics['signals_taken_pct']:.1%}")
        print(f"\nModel saved to ~/.cache/tradingbot/models/signal_filter.pkl")

    elif args.command == "info":
        filter = SignalFilter.load()
        if not filter.is_fitted:
            print("No trained model found")
            return

        print("Feature Importance:")
        importance = filter.get_feature_importance()
        sorted_features = sorted(importance.items(), key=lambda x: x[1], reverse=True)
        for name, imp in sorted_features:
            bar = "█" * int(imp * 50)
            print(f"  {name:20} {imp:.4f} {bar}")


if __name__ == "__main__":
    main()
```

Add to `pyproject.toml`:

```toml
[project.scripts]
# ... existing ...
tradingbot-ml = "tradingbot.ml_cli:main"
```

## Configuration

Add to `tradingbot.toml`:

```toml
[tradingbot.ml]
enabled = false              # Enable ML signal filter
threshold = 0.55             # Probability threshold (0.5-0.7 recommended)
model_path = ""              # Custom model path (default: ~/.cache/tradingbot/models/)
```

## Usage Examples

### Training

```bash
# Train on multiple symbols
tradingbot-ml train AAPL MSFT GOOGL AMZN NVDA META

# Train with custom parameters
tradingbot-ml train SPY QQQ IWM --period 3y --threshold 0.60

# View model info
tradingbot-ml info
```

### Using in Backtest

```bash
# Backtest with ML filter
tradingbot-backtest AAPL --ml-filter

# Compare with/without filter
tradingbot-backtest AAPL                 # Without filter
tradingbot-backtest AAPL --ml-filter     # With filter
```

### Using in Live Trading

```bash
# Live trading with ML filter
tradingbot-live AAPL --ml-filter --threshold 0.60
```

## Preventing Overfitting

1. **Diverse training symbols**: Train on 10+ diverse symbols (tech, finance, energy, etc.)
2. **Long history**: Use 2+ years of data
3. **Regularization**: max_depth=10, min_samples_leaf=20
4. **Cross-validation**: 5-fold CV during training
5. **Out-of-sample testing**: Hold out recent 20% of data
6. **Walk-forward validation**: Retrain monthly on rolling window

## Testing

```python
# tests/test_ml_filter.py

import pytest
from tradingbot._components.ml.features import SignalFeatures, FeatureExtractor
from tradingbot._components.ml.filter import SignalFilter


def test_signal_features_to_array():
    """Test feature array conversion."""
    features = SignalFeatures(
        rsi=50.0, rsi_slope=2.0, adx=25.0, atr_pct=0.02, bb_position=0.5,
        ema_dist=0.01, trend_aligned=1, higher_highs=2, lower_lows=1,
        volume_ratio=1.2, volume_trend=1,
        dist_to_stop=0.02, dist_to_tp=0.04, swing_strength=0.01, bars_since_swing=5,
        hour=10, day_of_week=2,
    )
    arr = features.to_array()
    assert len(arr) == 17
    assert arr[0] == 50.0  # rsi


def test_signal_filter_untrained():
    """Test untrained filter returns 0.5."""
    filter = SignalFilter()
    features = SignalFeatures(
        rsi=50.0, rsi_slope=0.0, adx=25.0, atr_pct=0.02, bb_position=0.5,
        ema_dist=0.0, trend_aligned=1, higher_highs=0, lower_lows=0,
        volume_ratio=1.0, volume_trend=0,
        dist_to_stop=0.02, dist_to_tp=0.04, swing_strength=0.01, bars_since_swing=5,
        hour=12, day_of_week=2,
    )
    proba = filter.predict_probability(features)
    assert proba == 0.5


def test_signal_filter_save_load(tmp_path):
    """Test model save/load."""
    filter = SignalFilter(threshold=0.60)
    path = tmp_path / "model.pkl"
    filter.save(path)

    loaded = SignalFilter.load(path)
    assert loaded.threshold == 0.60
```

## Evaluation Metrics

When evaluating the ML filter, track:

| Metric | Target | Description |
|--------|--------|-------------|
| Precision @ threshold | > 55% | Win rate of signals taken |
| Signal retention | 40-70% | % of signals passing filter |
| Net improvement | > 0 | Return(with filter) - Return(without) |
| Sharpe improvement | > 0 | Sharpe(with) - Sharpe(without) |

## Future Enhancements

1. **Ensemble models**: Combine RF with XGBoost, LightGBM
2. **Online learning**: Update model with new trades
3. **Symbol-specific models**: Train separate models per symbol/sector
4. **Feature selection**: Use SHAP values to prune features
5. **Confidence calibration**: Ensure predicted probabilities are well-calibrated
6. **A/B testing**: Compare filter vs no-filter in paper trading
