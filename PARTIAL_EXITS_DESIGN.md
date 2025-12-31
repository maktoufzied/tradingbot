# Partial Exits Design - Configuration & Best Practices

**Date:** 2025-01-27  
**Status:** Design proposal for TODO item

---

## Overview

Partial exits allow scaling out of positions at multiple profit targets, locking in profits while letting winners run. This is a standard professional trading technique.

---

## Common Partial Exit Strategies

### 1. **Simple 50/50 Split** (Most Common)
- 50% at 1R (lock in profit)
- 50% at 2R or trailing stop
- **Best for:** Day trading, swing trading
- **Win rate impact:** Locks in profits early, reduces volatility

### 2. **Three-Tier Scaling** (Conservative)
- 33% at 1R
- 33% at 2R  
- 33% at 3R or trailing stop
- **Best for:** Trend-following strategies
- **Win rate impact:** Maximizes winners, smooth equity curve

### 3. **Pyramid Exit** (Aggressive)
- 25% at 1R
- 25% at 2R
- 50% at 3R or trailing stop
- **Best for:** Strong trending markets
- **Win rate impact:** Lets big winners run

### 4. **Quick Lock + Runner**
- 50% at 0.5R (quick profit lock)
- 50% at 2R or trailing stop
- **Best for:** Volatile markets, quick profit taking

---

## Recommended Configuration Design

### Option 1: Simple Configuration (Recommended for MVP)

```toml
[tradingbot.strategy]
# ... existing config ...

# Partial exits
partial_exits_enabled = true
partial_exit_1r_pct = 0.5      # Exit 50% at 1R
partial_exit_2r_pct = 0.0      # Exit 0% at 2R (remaining runs to TP or trail)
```

**Pros:**
- Simple, easy to understand
- Covers 90% of use cases
- Minimal config complexity

**Cons:**
- Only supports 2 exit levels
- Less flexible

---

### Option 2: Flexible Multi-Level Configuration (Recommended for Production)

```toml
[tradingbot.strategy]
# ... existing config ...

# Partial exits - scale out at multiple profit targets
partial_exits_enabled = true

# Define exit levels as R multiples and percentages
[tradingbot.strategy.partial_exits]
# Format: exit_at_1r = 0.5 means "exit 50% of position when price reaches 1R profit"
exit_at_1r = 0.5      # Exit 50% at 1R
exit_at_2r = 0.0      # Exit 0% at 2R (remaining runs to final TP)
exit_at_3r = 0.0      # Optional: exit at 3R
# Remaining position exits at final TP or trailing stop
```

**Or more flexible array format:**

```toml
[tradingbot.strategy.partial_exits]
# Array of [R_multiple, exit_percentage] pairs
# Example: [[1.0, 0.5], [2.0, 0.3]] means:
#   - Exit 50% when price reaches 1R
#   - Exit 30% when price reaches 2R
#   - Remaining 20% runs to final TP or trailing stop
levels = [
    [1.0, 0.5],  # 50% at 1R
    [2.0, 0.0],  # 0% at 2R (can be omitted)
]

# Or use named levels for clarity:
# levels = [
#     {r_multiple = 1.0, exit_pct = 0.5},
#     {r_multiple = 2.0, exit_pct = 0.0},
# ]
```

**Pros:**
- Very flexible
- Supports any number of exit levels
- Can be optimized
- Professional-grade configuration

**Cons:**
- More complex configuration
- Requires validation (sum of percentages ≤ 1.0)

---

### Option 3: Preset-Based (Hybrid Approach)

```toml
[tradingbot.strategy]
partial_exits = "conservative"  # Preset name

# Or define custom:
[tradingbot.strategy.partial_exits]
mode = "custom"
levels = [
    [1.0, 0.5],  # 50% at 1R
]

# Presets:
# - "none" or false: No partial exits (current behavior)
# - "conservative": 50% at 1R, 50% at 2R
# - "aggressive": 25% at 1R, 25% at 2R, 50% at 3R
# - "quick": 50% at 0.5R, 50% at 2R
# - "custom": Use levels array
```

**Pros:**
- Easy for beginners (presets)
- Flexible for advanced users (custom)
- Best of both worlds

**Cons:**
- More code to maintain presets

---

## Recommended Implementation: Option 2 (Flexible Array)

### Configuration Structure

```python
# config.py
@dataclass(frozen=True)
class PartialExitLevel:
    """Single partial exit level."""
    r_multiple: float  # R multiple (1.0 = 1R, 2.0 = 2R, etc.)
    exit_pct: float    # Percentage of position to exit (0.0 to 1.0)

@dataclass(frozen=True)
class PartialExitsConfig:
    """Partial exits configuration."""
    enabled: bool = False
    levels: list[PartialExitLevel] = field(default_factory=list)
    
    def __post_init__(self) -> None:
        """Validate configuration."""
        if not self.enabled:
            return
        
        if not self.levels:
            raise ValueError("partial_exits.enabled=true requires at least one level")
        
        # Validate percentages sum to ≤ 1.0
        total_pct = sum(level.exit_pct for level in self.levels)
        if total_pct > 1.0:
            raise ValueError(
                f"Partial exit percentages sum to {total_pct:.1%}, must be ≤ 100%"
            )
        
        # Validate R multiples are positive and sorted
        r_multiples = [level.r_multiple for level in self.levels]
        if any(r <= 0 for r in r_multiples):
            raise ValueError("R multiples must be positive")
        
        if r_multiples != sorted(r_multiples):
            raise ValueError("R multiples must be in ascending order")

@dataclass(frozen=True)
class StrategyConfig:
    # ... existing fields ...
    partial_exits: PartialExitsConfig = field(default_factory=PartialExitsConfig)
```

### TOML Configuration Examples

```toml
# Example 1: Simple 50% at 1R
[tradingbot.strategy.partial_exits]
enabled = true
levels = [
    {r_multiple = 1.0, exit_pct = 0.5}
]

# Example 2: Three-tier scaling
[tradingbot.strategy.partial_exits]
enabled = true
levels = [
    {r_multiple = 1.0, exit_pct = 0.33},
    {r_multiple = 2.0, exit_pct = 0.33},
    {r_multiple = 3.0, exit_pct = 0.34},  # Remaining
]

# Example 3: Pyramid exit
[tradingbot.strategy.partial_exits]
enabled = true
levels = [
    {r_multiple = 1.0, exit_pct = 0.25},
    {r_multiple = 2.0, exit_pct = 0.25},
    # Remaining 50% runs to final TP or trailing stop
]

# Example 4: Quick lock + runner
[tradingbot.strategy.partial_exits]
enabled = true
levels = [
    {r_multiple = 0.5, exit_pct = 0.5},  # Quick 50% at 0.5R
    # Remaining 50% runs to 2R or trailing stop
]
```

---

## Implementation Details

### Position Data Structure Changes

```python
@dataclass
class Position:
    entry_price: float
    entry_index: int
    entry_time: datetime
    direction: Direction
    size: float
    stop_loss: float
    take_profit: float
    initial_stop_loss: float | None = None
    
    # Partial exit tracking
    partial_exits: list[tuple[float, float, float]] = field(default_factory=list)
    # Format: [(r_multiple, exit_price, exit_size), ...]
    # Example: [(1.0, 105.0, 50.0)] means "exited 50 shares at $105 when price hit 1R"
    
    remaining_size: float | None = None  # Size after partial exits
```

### Exit Logic Changes

```python
def _check_exit(self, bar: dict[str, Any]) -> ExitReason | None:
    """Check for exits, including partial profit taking."""
    assert self.position is not None
    p = self.position
    
    # Calculate remaining size (after partial exits)
    remaining = p.remaining_size if p.remaining_size is not None else p.size
    
    if remaining == 0:
        return "FULLY_CLOSED"
    
    # Stop loss - always exit 100% of remaining
    if p.direction == "LONG" and bar["low"] <= p.stop_loss:
        return "STOP_LOSS"
    if p.direction == "SHORT" and bar["high"] >= p.stop_loss:
        return "STOP_LOSS"
    
    # Check partial exit levels
    risk = abs(p.entry_price - (p.initial_stop_loss or p.stop_loss))
    config = get_strategy_config().partial_exits
    
    if config.enabled:
        for level in config.levels:
            # Check if this level has already been executed
            already_exited = any(
                exit_r == level.r_multiple 
                for exit_r, _, _ in p.partial_exits
            )
            
            if already_exited:
                continue
            
            # Calculate target price for this R level
            if p.direction == "LONG":
                target_price = p.entry_price + (risk * level.r_multiple)
                if bar["high"] >= target_price:
                    # Execute partial exit
                    exit_size = remaining * level.exit_pct
                    p.partial_exits.append((level.r_multiple, target_price, exit_size))
                    p.remaining_size = remaining - exit_size
                    
                    # Move stop to breakeven after first partial exit
                    if len(p.partial_exits) == 1 and p.stop_loss != p.entry_price:
                        p.stop_loss = p.entry_price
                    
                    # Record partial exit trade
                    self._record_partial_exit(p, target_price, exit_size, level.r_multiple)
                    
                    # If all position exited, return fully closed
                    if p.remaining_size <= 0:
                        return "FULLY_CLOSED"
                    
                    return f"PARTIAL_EXIT_{level.r_multiple}R"
            else:
                # Similar logic for SHORT
                target_price = p.entry_price - (risk * level.r_multiple)
                if bar["low"] <= target_price:
                    # ... same logic ...
    
    # Final take profit - exit remaining position
    if p.direction == "LONG" and bar["high"] >= p.take_profit:
        return "TAKE_PROFIT"
    if p.direction == "SHORT" and bar["low"] <= p.take_profit:
        return "TAKE_PROFIT"
    
    return None
```

---

## Best Practices & Recommendations

### 1. **Default Configuration: 50% at 1R**

**Recommended default:**
```toml
[tradingbot.strategy.partial_exits]
enabled = false  # Off by default for backward compatibility
levels = [
    {r_multiple = 1.0, exit_pct = 0.5}  # When enabled, default to 50% at 1R
]
```

**Why 50% at 1R?**
- ✅ Locks in profit early (risk-free trade after 1R)
- ✅ Lets winners run (50% can capture bigger moves)
- ✅ Reduces volatility in equity curve
- ✅ Industry standard approach
- ✅ Works well across different market conditions

### 2. **When to Use Different Configurations**

| Strategy Type | Recommended Partial Exit | Reason |
|--------------|-------------------------|--------|
| **Day Trading** | 50% at 1R | Quick profit lock, reduce overnight risk |
| **Swing Trading** | 50% at 1R, 50% at 2R | Multiple profit targets, smooth returns |
| **Trend Following** | 25% at 1R, 25% at 2R, 50% at 3R | Let big winners run |
| **Mean Reversion** | 50% at 0.5R | Quick profit taking, tight stops |
| **Scalping** | 50% at 0.5R | Very quick profit lock |

### 3. **Integration with Trailing Stops**

**Recommended behavior:**
- After first partial exit, move stop to breakeven
- Remaining position can use trailing stop
- Trailing stop applies to remaining position only

**Example:**
```python
# Position: 100 shares, entry $100, stop $98 (2R risk)
# Partial exit: 50% at 1R ($102) → exit 50 shares
# Remaining: 50 shares
# Stop moved to: $100 (breakeven)
# Trailing stop: Applies to remaining 50 shares
```

### 4. **P&L Calculation**

**Each partial exit should:**
- Calculate P&L for that portion
- Update capital immediately
- Record as separate trade or part of same trade
- Track cumulative P&L for the position

**Trade Record Options:**

**Option A: Single Trade with Partial Exits**
```python
@dataclass
class Trade:
    # ... existing fields ...
    partial_exits: list[PartialExit] = field(default_factory=list)
    total_pnl: float  # Sum of all partial exits + final exit
```

**Option B: Multiple Trade Records**
```python
# Record each partial exit as separate trade
# Trade 1: Partial exit at 1R
# Trade 2: Final exit at TP
# Both linked by same entry_index
```

**Recommendation:** Option A (single trade with partial exits list) - cleaner for reporting

---

## Configuration Examples for Different Strategies

### Conservative (Lock Profits Early)
```toml
[tradingbot.strategy.partial_exits]
enabled = true
levels = [
    {r_multiple = 0.75, exit_pct = 0.5},  # 50% at 0.75R
    {r_multiple = 1.5, exit_pct = 0.3},   # 30% at 1.5R
    # Remaining 20% runs to final TP
]
```

### Balanced (Standard)
```toml
[tradingbot.strategy.partial_exits]
enabled = true
levels = [
    {r_multiple = 1.0, exit_pct = 0.5},  # 50% at 1R
    # Remaining 50% runs to 2R or trailing stop
]
```

### Aggressive (Let Winners Run)
```toml
[tradingbot.strategy.partial_exits]
enabled = true
levels = [
    {r_multiple = 1.0, exit_pct = 0.25},  # 25% at 1R
    {r_multiple = 2.0, exit_pct = 0.25},  # 25% at 2R
    # Remaining 50% runs to 3R or trailing stop
]
```

### Quick Scalping
```toml
[tradingbot.strategy.partial_exits]
enabled = true
levels = [
    {r_multiple = 0.5, exit_pct = 0.5},  # 50% at 0.5R (quick lock)
    # Remaining 50% runs to 1R or trailing stop
]
```

---

## CLI Support

```bash
# Enable partial exits with default (50% at 1R)
tradingbot-backtest SPY --partial-exits

# Custom partial exit levels
tradingbot-backtest SPY --partial-exits --exit-levels "1.0:0.5,2.0:0.3"

# Disable partial exits (default)
tradingbot-backtest SPY --no-partial-exits
```

---

## Preset Integration

```toml
[tradingbot.presets.scalping]
# ... other config ...
partial_exits_enabled = true
partial_exit_levels = [
    {r_multiple = 0.5, exit_pct = 0.5}
]

[tradingbot.presets.swing_conservative]
# ... other config ...
partial_exits_enabled = true
partial_exit_levels = [
    {r_multiple = 1.0, exit_pct = 0.5},
    {r_multiple = 2.0, exit_pct = 0.5}
]
```

---

## Answer to Your Question

**"Should partial exits be configured as one at 50%?"**

**Yes, but make it flexible:**

1. **Default:** 50% at 1R is an excellent default
   - Industry standard
   - Works well across strategies
   - Good balance of profit locking and letting winners run

2. **But allow customization:**
   - Some strategies need different levels
   - Some traders prefer different percentages
   - Should support multiple exit levels

3. **Recommended approach:**
   ```toml
   [tradingbot.strategy.partial_exits]
   enabled = true
   levels = [
       {r_multiple = 1.0, exit_pct = 0.5}  # Default: 50% at 1R
   ]
   ```

4. **For presets, use common patterns:**
   - **Scalping:** 50% at 0.5R
   - **Day Trading:** 50% at 1R (default)
   - **Swing Trading:** 50% at 1R, 50% at 2R
   - **Trend Following:** 25% at 1R, 25% at 2R, 50% at 3R

---

## Implementation Priority

1. **Phase 1 (MVP):** Simple 50% at 1R
   - Single config: `partial_exit_1r_pct = 0.5`
   - Quick to implement
   - Covers most use cases

2. **Phase 2 (Full):** Flexible multi-level
   - Array-based configuration
   - Support any number of levels
   - Full validation

**Recommendation:** Start with Phase 1, upgrade to Phase 2 if needed.

---

## Summary

**Answer:** Yes, 50% at 1R is an excellent default, but the system should support flexible configuration for different trading styles and strategies.

**Recommended Configuration:**
- Default: `enabled = false` (backward compatibility)
- When enabled: Default to 50% at 1R
- Allow custom levels via array configuration
- Support in presets for common patterns

This provides the best balance of simplicity and flexibility.

