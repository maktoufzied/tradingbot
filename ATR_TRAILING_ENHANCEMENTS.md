# ATR Trailing Stop Enhancements

This document describes three enhancements to the ATR-based trailing stop system, incorporating feedback from Claude:

1. **Dynamic ATR** (Optional) - Recalculate ATR each bar instead of caching at entry

   - **Note**: Cached ATR is intentional - prevents stops from widening during volatility spikes
   - Make configurable but keep cached as default for risk management

2. **Activation R-Multiple** - Only start trailing after reaching a profit target

   - Parameter: `atr_trail_activation_r` (default: 0.0 = immediate)
   - Similar to breakeven trailing logic (waits for 1R)

3. **Time-Based Decay** - Gradually tighten trailing multiplier as trade ages
   - Parameters: `atr_trail_decay_rate` (decay per bar), `atr_trail_min_mult` (minimum floor)
   - Useful for day trading, adds complexity

---

## Summary of Design Decisions (Based on Claude's Feedback)

### 1. Dynamic ATR

- **Current cached approach is intentional** - prevents stops from widening during volatility spikes
- Make it **configurable** but **not recommended by default**
- Parameter: `atr_trail_dynamic` (default: False)

### 2. Activation R-Multiple

- **Good enhancement** - similar to breakeven trailing logic
- Parameter: `atr_trail_activation_r` (default: 0.0 = immediate)
- Common value: 1.0 (wait for 1R profit before trailing)

### 3. Time-Based Decay

- **Useful for day trading** but adds complexity
- Use **decay rate approach** instead of discrete stages (simpler)
- Parameters: `atr_trail_decay_rate` (default: 0.0 = no decay), `atr_trail_min_mult` (default: 1.0)

---

## 1. Dynamic ATR (Recalculate Each Bar) - OPTIONAL

### Current Behavior (Recommended Default)

- ATR is calculated once at entry and cached in `self._current_atr`
- Trailing distance remains constant throughout the trade
- **Rationale**: If volatility spikes mid-trade, you don't want the stop to suddenly widen (bad for risk management)
- The cached approach is **intentional** for consistent risk control

### Optional Dynamic Behavior

- Make dynamic ATR **configurable** for users who want it
- Recalculate ATR each bar using recent price data
- Trailing distance adapts to changing volatility conditions
- **Warning**: Can cause stops to widen during volatility spikes, increasing risk

### Implementation

**Configuration:**

```python
# bot.py __init__
atr_trail: bool = False,
atr_trail_multiplier: float = 2.0,
atr_trail_dynamic: bool = False,  # NEW: Enable dynamic ATR (optional, not recommended by default)
atr_trail_period: int = 14,  # NEW: ATR period for dynamic calculation
```

**Note**: Dynamic ATR is optional and disabled by default. The cached approach is recommended for consistent risk management.

**Code Changes:**

```python
# bot.py - Remove cached ATR, calculate dynamically
def __init__(self, ...):
    # Remove: self._current_atr: float = 0.0
    self.atr_trail_dynamic = atr_trail_dynamic
    self.atr_trail_period = atr_trail_period

def _open(self, ...):
    # Remove: if self.atr_trail: self._current_atr = self._calc_atr(history)
    # No caching needed for dynamic mode

def _trail_stop(self, bar: dict[str, Any], df: pl.DataFrame) -> None:
    """Trail stop loss with optional dynamic ATR."""
    assert self.position is not None
    p: Position = self.position
    if p.initial_stop_loss is None:
        return

    # Update high-water mark
    if p.direction == "LONG":
        current_high = bar["high"]
        if p.high_water_mark is None or current_high > p.high_water_mark:
            p.high_water_mark = current_high
    else:
        current_low = bar["low"]
        if p.high_water_mark is None or current_low < p.high_water_mark:
            p.high_water_mark = current_low

    # ATR-based trailing
    if self.atr_trail:
        # Calculate ATR dynamically or use cached value
        if self.atr_trail_dynamic:
            # Get current bar index from position
            current_idx = p.entry_index + (len(df) - p.entry_index)
            history = df.head(current_idx + 1)
            current_atr = compute_atr(history, self.atr_trail_period) or 0.0
        else:
            # Use cached ATR from entry (existing behavior)
            current_atr = self._current_atr

        if current_atr > 0:
            trail_distance = self.atr_trail_multiplier * current_atr
            if p.direction == "LONG":
                new_stop = p.high_water_mark - trail_distance
                if new_stop > p.stop_loss:
                    p.stop_loss = new_stop
            else:
                new_stop = p.high_water_mark + trail_distance
                if new_stop < p.stop_loss:
                    p.stop_loss = new_stop
            return
```

**Usage:**

```bash
# Static ATR (current behavior)
task backtest -- SPY --atr-trail

# Dynamic ATR (recalculates each bar)
task backtest -- SPY --atr-trail --atr-trail-dynamic
```

**Benefits:**

- Adapts to changing volatility (tightens in low vol, widens in high vol)
- Better for long-term trades where volatility can change significantly
- More responsive to market regime changes

**Trade-offs:**

- **Risk**: If volatility spikes mid-trade, stop can widen, increasing risk exposure
- Slightly more computation (recalculates ATR each bar)
- Trailing distance can change, potentially causing whipsaws in volatile markets
- **Recommended**: Keep cached ATR as default for consistent risk management

---

## 2. Minimum Profit Threshold (Activation R-Multiple)

### Current Behavior

- Trailing starts immediately when ATR trail is enabled
- Stop can move even when position is at a loss

### Proposed Behavior

- Only start trailing after position reaches a minimum profit threshold (e.g., 1R, 0.5R)
- Similar to how breakeven trailing waits for 1R before moving stop to entry
- Prevents premature stop tightening on small moves

### Implementation

**Configuration:**

```python
# bot.py __init__
atr_trail: bool = False,
atr_trail_multiplier: float = 2.0,
atr_trail_activation_r: float = 0.0,  # NEW: Minimum R-multiple before trailing starts (0.0 = immediate)
```

**Parameter Name**: `atr_trail_activation_r` (following Claude's suggestion)

**Code Changes:**

```python
def _trail_stop(self, bar: dict[str, Any], df: pl.DataFrame) -> None:
    """Trail stop loss with minimum profit threshold."""
    assert self.position is not None
    p: Position = self.position
    if p.initial_stop_loss is None:
        return

    # Calculate current profit in R-multiples
    risk = abs(p.entry_price - p.initial_stop_loss)
    if risk == 0:
        return

    if p.direction == "LONG":
        current_price = bar["high"]
        profit = current_price - p.entry_price
    else:
        current_price = bar["low"]
        profit = p.entry_price - current_price

    current_r = profit / risk

    # Check activation threshold (similar to breakeven trailing logic)
    if self.atr_trail and current_r < self.atr_trail_activation_r:
        # Not enough profit yet, don't trail
        return

    # Update high-water mark
    if p.direction == "LONG":
        current_high = bar["high"]
        if p.high_water_mark is None or current_high > p.high_water_mark:
            p.high_water_mark = current_high
    else:
        current_low = bar["low"]
        if p.high_water_mark is None or current_low < p.high_water_mark:
            p.high_water_mark = current_low

    # ATR-based trailing (only if profit threshold met)
    if self.atr_trail:
        current_atr = self._current_atr if not self.atr_trail_dynamic else compute_atr(df, self.atr_trail_period) or 0.0
        if current_atr > 0:
            trail_distance = self.atr_trail_multiplier * current_atr
            if p.direction == "LONG":
                new_stop = p.high_water_mark - trail_distance
                if new_stop > p.stop_loss:
                    p.stop_loss = new_stop
            else:
                new_stop = p.high_water_mark + trail_distance
                if new_stop < p.stop_loss:
                    p.stop_loss = new_stop
            return
```

**Usage:**

```bash
# Start trailing immediately (current behavior, default)
task backtest -- SPY --atr-trail

# Only trail after 1R profit (similar to breakeven trailing)
task backtest -- SPY --atr-trail --atr-trail-activation-r 1.0

# Only trail after 0.5R profit
task backtest -- SPY --atr-trail --atr-trail-activation-r 0.5
```

**Benefits:**

- Prevents premature stop tightening on small moves
- Gives trades room to develop before trailing starts
- Reduces whipsaws in choppy markets

**Common Thresholds:**

- `0.0` = Immediate trailing (current behavior, default)
- `0.5` = Trail after 0.5R profit (conservative)
- `1.0` = Trail after 1R profit (common, similar to breakeven trailing)
- `1.5` = Trail after 1.5R profit (aggressive, let winners run)

---

## 3. Time-Based Decay (Tighten Over Time)

### Current Behavior

- Trailing distance (ATR multiplier) remains constant throughout trade
- No consideration for how long the trade has been open

### Proposed Behavior

- Gradually decay (tighten) trailing multiplier as trade ages
- Uses decay rate approach instead of discrete stages (simpler, more flexible)
- Useful for day trading where you want to protect profits as trade ages

### Implementation

**Configuration:**

```python
# bot.py __init__
atr_trail: bool = False,
atr_trail_multiplier: float = 2.0,
atr_trail_decay_rate: float = 0.0,  # NEW: Decay rate per bar (0.0 = no decay)
atr_trail_min_mult: float = 1.0,  # NEW: Minimum multiplier (floor)
```

**Parameter Names**: Following Claude's suggestion:

- `atr_trail_decay_rate`: How much to reduce multiplier per bar (e.g., 0.01 = 1% per bar)
- `atr_trail_min_mult`: Minimum multiplier floor (prevents going too tight)

**Code Changes:**

```python
def _trail_stop(self, bar: dict[str, Any], df: pl.DataFrame, current_idx: int) -> None:
    """Trail stop loss with optional time-based tightening."""
    assert self.position is not None
    p: Position = self.position
    if p.initial_stop_loss is None:
        return

    # Calculate current profit in R-multiples
    risk = abs(p.entry_price - p.initial_stop_loss)
    if risk == 0:
        return

    if p.direction == "LONG":
        current_price = bar["high"]
        profit = current_price - p.entry_price
    else:
        current_price = bar["low"]
        profit = p.entry_price - current_price

    current_r = profit / risk

    # Check minimum profit threshold
    if self.atr_trail and current_r < self.atr_trail_min_profit_r:
        return

    # Update high-water mark
    if p.direction == "LONG":
        current_high = bar["high"]
        if p.high_water_mark is None or current_high > p.high_water_mark:
            p.high_water_mark = current_high
    else:
        current_low = bar["low"]
        if p.high_water_mark is None or current_low < p.high_water_mark:
            p.high_water_mark = current_low

    # ATR-based trailing
    if self.atr_trail:
        # Calculate effective multiplier (with optional time-based decay)
        effective_multiplier = self.atr_trail_multiplier

        if self.atr_trail_decay_rate > 0:
            bars_held = current_idx - p.entry_index
            # Decay: reduce multiplier by decay_rate per bar
            decayed_mult = self.atr_trail_multiplier - (self.atr_trail_decay_rate * bars_held)
            # Apply minimum floor
            effective_multiplier = max(decayed_mult, self.atr_trail_min_mult)

        current_atr = self._current_atr if not self.atr_trail_dynamic else compute_atr(df, self.atr_trail_period) or 0.0
        if current_atr > 0:
            trail_distance = effective_multiplier * current_atr
            if p.direction == "LONG":
                new_stop = p.high_water_mark - trail_distance
                if new_stop > p.stop_loss:
                    p.stop_loss = new_stop
            else:
                new_stop = p.high_water_mark + trail_distance
                if new_stop < p.stop_loss:
                    p.stop_loss = new_stop
            return
```

**Usage:**

```bash
# Static multiplier (current behavior, default)
task backtest -- SPY --atr-trail --atr-trail-mult 2.0

# Time-based decay: reduce by 0.01 (1%) per bar, minimum 1.0×
task backtest -- SPY --atr-trail --atr-trail-mult 2.0 \
  --atr-trail-decay-rate 0.01 --atr-trail-min-mult 1.0

# Faster decay: reduce by 0.02 (2%) per bar, minimum 1.5×
task backtest -- SPY --atr-trail --atr-trail-mult 2.0 \
  --atr-trail-decay-rate 0.02 --atr-trail-min-mult 1.5
```

**Configuration File:**

```toml
[tradingbot.strategy]
atr_trail = true
atr_trail_multiplier = 2.0
atr_trail_decay_rate = 0.01  # Reduce by 1% per bar
atr_trail_min_mult = 1.0     # Minimum multiplier floor
```

**Example Calculation:**

- Start: 2.0× ATR
- After 20 bars: 2.0 - (0.01 × 20) = 1.8× ATR
- After 50 bars: 2.0 - (0.01 × 50) = 1.5× ATR
- After 100 bars: 2.0 - (0.01 × 100) = 1.0× ATR (hits floor)

**Benefits:**

- Protects profits more aggressively as trade ages
- Useful for day trading where you want to protect profits as trade ages
- Simpler than stage-based approach (continuous decay vs discrete stages)
- More flexible: can fine-tune decay rate

**Common Patterns:**

- **Day Trading (Fast Decay)**: `decay_rate=0.02, min_mult=1.0` - Tighten quickly
- **Swing Trading (Moderate)**: `decay_rate=0.01, min_mult=1.0` - Standard progression
- **Position Trading (Slow Decay)**: `decay_rate=0.005, min_mult=1.5` - Let winners run longer

**Note**: Adds complexity but useful for specific trading styles (especially day trading)

---

## Combined Example

All three enhancements can work together:

```bash
task backtest -- SPY \
  --atr-trail \
  --atr-trail-mult 2.0 \
  --atr-trail-dynamic \
  --atr-trail-activation-r 1.0 \
  --atr-trail-decay-rate 0.01 \
  --atr-trail-min-mult 1.0
```

**Behavior:**

1. Wait until 1R profit before trailing starts (`activation_r=1.0`)
2. Use dynamic ATR (recalculates each bar) - **optional, not recommended by default**
3. Start with 2.0× ATR distance
4. Decay by 0.01 (1%) per bar, minimum 1.0× ATR
5. After 50 bars: 2.0 - (0.01 × 50) = 1.5× ATR
6. After 100 bars: 2.0 - (0.01 × 100) = 1.0× ATR (hits floor)

---

## Implementation Priority

### Phase 1: Minimum Profit Threshold (Easiest, High Value)

- Simple R-multiple check
- Prevents premature trailing
- Low risk of breaking existing behavior

### Phase 2: Dynamic ATR (Medium Complexity, Medium Value)

- Requires passing DataFrame to `_trail_stop()`
- More computation but better adaptation
- Can combine with static mode

### Phase 3: Time-Based Trailing (Most Complex, Nice-to-Have)

- Requires tracking bars held
- More configuration complexity
- Useful for specific trading styles

---

## Testing Considerations

Each enhancement should have tests:

1. **Dynamic ATR:**

   - Verify ATR recalculates each bar
   - Compare static vs dynamic in volatile market
   - Ensure works with insufficient data

2. **Minimum Profit Threshold:**

   - Verify trailing doesn't start before threshold
   - Verify trailing starts after threshold
   - Test with different R-multiple thresholds

3. **Time-Based Decay:**
   - Verify multiplier decays correctly per bar
   - Test minimum multiplier floor
   - Test edge cases (very short/long trades)
   - Verify decay stops at minimum floor

---

## Backward Compatibility

All enhancements are **opt-in**:

- Default behavior unchanged (static ATR, no threshold, no time-based)
- Existing configs continue to work
- New parameters have safe defaults
