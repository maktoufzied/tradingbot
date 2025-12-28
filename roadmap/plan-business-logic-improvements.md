# Business Logic Improvements - Implementation Plan

## Review Verification

I reviewed Cursor's analysis against the actual code. Here's my assessment:

| Issue | Cursor's Claim | Verified? | Notes |
|-------|----------------|-----------|-------|
| 1. No slippage/commission | Critical | ✅ YES | `bot.py:204` has no costs |
| 2. Lookahead bias | High risk | ❌ NO | Code uses `df.head(idx+1)` correctly |
| 3. Position sizing | Oversimplified | ✅ YES | `risk.py` is 23 lines, no ATR |
| 4. No partial exits | Missing | ✅ YES | `_check_exit()` is all-or-nothing |
| 5. Limited trailing | Only breakeven | ✅ YES | `_trail_stop()` only moves to entry |
| 6. Optimization | Overfitting risk | ⚠️ PARTIAL | `check_overfitting()` exists but is basic |
| 7. Swing break thresholds | Hard-coded | ✅ YES | `0.98`, `0.6` are magic numbers |
| 8. Swing TP calculation | Too simple | ⚠️ PARTIAL | Works but could be smarter |

**Lookahead Bias - NOT an issue:**
- `signals.py:69` uses `hist = df.head(idx + 1)`
- `bot.py:190` passes `df.head(idx + 1)` to `calc_exit()`
- All swing calculations work on truncated data

---

## Implementation Phases

Each phase is one GitHub issue → one commit → update docs.

---

## Phase 1: Execution Cost Model

### GitHub Issue

**Title:** `feat(backtest): Add slippage and commission modeling for realistic backtests`

**Description:**

Currently, backtests assume perfect execution at exact prices. This overestimates returns by 10-30% and makes small profitable strategies appear viable when they're actually unprofitable after costs.

**Problem:**
```python
# bot.py:204 - No execution costs
pnl = (price - p.entry_price) * p.size
```

**Solution:**
Add `ExecutionModel` class that models:
- Bid-ask spread (default: 2 bps)
- Slippage (default: 5 bps)
- Commission per share (default: $0.005)

**Acceptance Criteria:**
- [ ] Create `ExecutionModel` dataclass with configurable costs
- [ ] Apply costs to entry and exit in `_open()` and `_close()`
- [ ] Add `--no-costs` flag to CLI for comparison
- [ ] Stats should show gross vs net P&L
- [ ] Update docs: README.md (CLI), ARCHITECTURE.md (component)

**Files to modify:**
- `src/tradingbot/_components/execution.py` (new)
- `src/tradingbot/_components/bot.py`
- `src/tradingbot/backtest_cli.py`
- `README.md`
- `ARCHITECTURE.md`

---

## Phase 2: Walk-Forward Optimization

### GitHub Issue

**Title:** `feat(optimize): Add walk-forward analysis to prevent overfitting`

**Description:**

Current optimization tests all parameters on the same dataset used for training. This leads to overfitting - parameters that work on historical data but fail on new data.

**Current behavior:**
- Grid search tests all combinations on full dataset
- `check_overfitting()` exists but only does single train/test split
- No rolling window validation

**Solution:**
Add proper walk-forward analysis:
1. Split data into multiple train/test windows
2. Optimize on each training window
3. Test best params on following out-of-sample window
4. Aggregate results to show true expected performance

**Acceptance Criteria:**
- [ ] Create `WalkForwardOptimizer` class
- [ ] Support configurable train/test ratios
- [ ] Report in-sample vs out-of-sample performance
- [ ] Add `--walk-forward` flag to optimize CLI
- [ ] Update docs: README.md (CLI), guide-strategy.md (optimization)

**Files to modify:**
- `src/tradingbot/_components/walk_forward.py` (new)
- `src/tradingbot/optimize_cli.py`
- `README.md`
- `guide-strategy.md`

---

## Phase 3: Volatility-Adjusted Position Sizing

### GitHub Issue

**Title:** `feat(risk): Add ATR-based volatility adjustment to position sizing`

**Description:**

Current position sizing uses fixed percentage risk regardless of market volatility. A 2% stop on a volatile stock vs a stable stock should result in different position sizes.

**Current behavior:**
```python
# risk.py - No volatility consideration
risk_amt = self.capital * self.risk_pct
size = risk_amt / risk_per_unit
```

**Solution:**
Add volatility-aware position sizing:
1. Calculate ATR at entry time
2. Adjust risk if stop is too tight (< 0.5 ATR) or too wide (> 3 ATR)
3. Optionally reduce size during drawdowns (Kelly-style)

**Acceptance Criteria:**
- [ ] Add `use_atr_adjustment` option to `PositionSizer`
- [ ] Calculate ATR and adjust position size accordingly
- [ ] Add drawdown-based size reduction option
- [ ] Add `--atr-sizing` flag to CLI
- [ ] Update docs: guide-strategy.md (position sizing section)

**Files to modify:**
- `src/tradingbot/_components/risk.py`
- `src/tradingbot/_components/bot.py`
- `src/tradingbot/backtest_cli.py`
- `guide-strategy.md`

---

## Phase 4: Partial Profit Taking

### GitHub Issue

**Title:** `feat(exits): Add partial profit taking at intermediate targets`

**Description:**

Current exits are all-or-nothing: 100% at stop or 100% at target. This leaves money on the table when targets are hit early and increases equity volatility.

**Current behavior:**
```python
# bot.py - Full exit only
if bar["high"] >= p.take_profit:
    return "TAKE_PROFIT"  # Exits 100%
```

**Solution:**
Add partial exit support:
1. Exit 50% at 1R profit
2. Move stop to breakeven on remaining 50%
3. Exit remaining at original target or trailing stop

**Acceptance Criteria:**
- [ ] Add `partial_exits` tracking to `Position`
- [ ] Implement 50% exit at 1R
- [ ] Track remaining position size
- [ ] Report partial exits in trade log
- [ ] Add `--partial-exits` flag to CLI
- [ ] Update docs: guide-strategy.md (exit strategies)

**Files to modify:**
- `src/tradingbot/types.py` (Position dataclass)
- `src/tradingbot/_components/bot.py`
- `src/tradingbot/backtest_cli.py`
- `guide-strategy.md`

---

## Phase 5: ATR-Based Trailing Stops

### GitHub Issue

**Title:** `feat(exits): Add ATR-based trailing stop with high-water mark`

**Description:**

Current trailing stop only moves to breakeven after 1R profit. It doesn't continue trailing as the trade moves further into profit.

**Current behavior:**
```python
# bot.py - Only moves to breakeven
if bar["high"] >= p.entry_price + risk and p.stop_loss < p.entry_price:
    p.stop_loss = p.entry_price  # Stops here
```

**Solution:**
Add ATR-based trailing:
1. Track high-water mark (highest price since entry)
2. Trail stop at `high_water - (N * ATR)`
3. Only move stop up, never down

**Acceptance Criteria:**
- [ ] Calculate ATR for trailing distance
- [ ] Track high-water mark per position
- [ ] Trail stop progressively as price moves
- [ ] Make trailing multiplier configurable
- [ ] Add `--atr-trail` flag to CLI
- [ ] Update docs: guide-strategy.md (trailing stops)

**Files to modify:**
- `src/tradingbot/_components/bot.py`
- `src/tradingbot/backtest_cli.py`
- `guide-strategy.md`

---

## Phase 6: Strategy Parameter Cleanup

### GitHub Issue

**Title:** `refactor(strategies): Replace magic numbers with configurable parameters`

**Description:**

Entry strategies have hard-coded thresholds that should be configurable:
- `swing_break.py:76`: `0.98` (2% pullback threshold)
- `swing_break.py:79`: `0.6` (60% candle strength)

**Solution:**
Move magic numbers to strategy config or make them class parameters.

**Acceptance Criteria:**
- [ ] Extract magic numbers to named constants
- [ ] Make key thresholds configurable via `__init__`
- [ ] Document thresholds in docstrings
- [ ] Update docs: guide-strategy.md (strategy parameters)

**Files to modify:**
- `src/tradingbot/_components/strategies/entry/swing_break.py`
- `guide-strategy.md`

---

## Implementation Order

| Phase | Priority | Effort | Impact |
|-------|----------|--------|--------|
| 1. Execution costs | 🔴 Critical | Medium | High - all backtests affected |
| 2. Walk-forward | 🟡 High | Medium | High - prevents overfitting |
| 3. ATR sizing | 🟡 High | Low | Medium - better risk mgmt |
| 4. Partial exits | 🟡 Medium | Medium | Medium - better profit capture |
| 5. ATR trailing | 🟡 Medium | Low | Medium - better exit mgmt |
| 6. Magic numbers | 🟢 Low | Low | Low - code quality |

---

## Commit Format

Each phase should follow this commit format:

```
feat(component): Short description

- Bullet point of changes
- Another change

Closes #XX

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
```

---

## Documentation Updates Per Phase

| Phase | README.md | ARCHITECTURE.md | guide-strategy.md | glossary.md |
|-------|-----------|-----------------|-------------------|-------------|
| 1 | CLI flags | ExecutionModel | - | Slippage, Commission |
| 2 | CLI flags | WalkForward | Optimization section | Walk-Forward |
| 3 | CLI flags | - | Position sizing | ATR Sizing |
| 4 | CLI flags | - | Exit strategies | Partial Exit |
| 5 | CLI flags | - | Trailing stops | ATR Trail |
| 6 | - | - | Strategy params | - |

---

## Issues NOT Implemented (and why)

| Cursor's Issue | Decision | Reason |
|----------------|----------|--------|
| Lookahead bias | Skip | Code is already correct |
| VWAP z-score | Skip | Edge case, strategy works |
| Daily reset timezone | Skip | Live trading concern, not backtest |
| Position rounding | Skip | Minor, current behavior is safe |
| Monte Carlo | Defer | Nice-to-have, not critical |
| Regime detection | Defer | Separate feature, not a fix |
