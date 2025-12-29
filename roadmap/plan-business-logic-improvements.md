# Business Logic Improvements - Implementation Plan

## Review Verification

I reviewed Cursor's analysis against the actual code. Here's my assessment:

| Issue | Cursor's Claim | Verified? | Notes |
|-------|----------------|-----------|-------|
| 1. No slippage/commission | Critical | ✅ YES | `bot.py:204` has no costs |
| 2. Lookahead bias | High risk | ❌ NO | Code uses `df.head(idx+1)` correctly |
| 3. Position sizing | Oversimplified | ✅ FIXED | Phase 3 complete: ATR-based sizing |
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

## Phase 3: Volatility-Adjusted Position Sizing ✅ COMPLETE

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
2. Compare current ATR to baseline ATR (50-period average)
3. Scale position size inversely with volatility (high vol → smaller positions)
4. Clamp scaling factor between 0.25x and 1.5x for safety

**Acceptance Criteria:**
- [x] Add `use_atr_sizing` option to `PositionSizer`
- [x] Calculate ATR and adjust position size accordingly
- [x] Add volatility-based size scaling (baseline ATR / current ATR)
- [x] Add `--atr-sizing` flag to backtest and live CLI
- [x] Add `atr_sizing` config option in `tradingbot.toml`
- [x] Add `atr_sizing` to preset system (`Preset` dataclass)
- [x] Add `atr_sizing` as optimizable parameter in Optuna
- [x] Update docs: guide-strategy.md (position sizing section)
- [x] Update docs: README.md (CLI flags, config)
- [x] Add 11 tests for ATR sizing in `test_risk.py`

**Files modified:**
- `src/tradingbot/_components/risk.py` - Core ATR sizing logic
- `src/tradingbot/_components/bot.py` - Pass DataFrame to calc_size()
- `src/tradingbot/_components/runner.py` - Backtest params, preset support
- `src/tradingbot/_components/presets.py` - Preset dataclass, save_preset()
- `src/tradingbot/_components/tuner.py` - Optuna optimization
- `src/tradingbot/backtest_cli.py` - CLI flag
- `src/tradingbot/cli.py` - Live CLI flag
- `src/tradingbot/optuna_cli.py` - Save preset with atr_sizing
- `src/tradingbot/config.py` - Config support
- `tradingbot.toml` - Config example
- `guide-strategy.md`
- `README.md`
- `tests/test_risk.py` - 11 new tests

---

## Phase 4: Partial Profit Taking ✅ COMPLETE

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
Add configurable partial exit levels as a list of {r_multiple, exit_pct} pairs:

```toml
[tradingbot.strategy]
partial_exit_levels = [
    {r_multiple = 1.0, exit_pct = 0.5},   # Exit 50% at 1R
    {r_multiple = 2.0, exit_pct = 0.25},  # Exit 25% at 2R
    # Remaining 25% runs to final TP or trailing stop
]
```

**Example strategies:**
| Style | Configuration |
|-------|---------------|
| Conservative | `[{r=1.0, pct=0.5}]` - 50% at 1R, rest to TP |
| Scaled | `[{r=1.0, pct=0.33}, {r=2.0, pct=0.33}]` - 33% at each R |
| Runner | `[{r=1.0, pct=0.25}]` - 25% at 1R, let 75% run |
| All-or-nothing | `[]` - empty list = current behavior |

**Behavior:**
1. At each r_multiple level, exit the specified percentage
2. Move stop to breakeven after first partial exit
3. Remaining position runs to final TP or trailing stop
4. Empty list = current all-or-nothing behavior

**Acceptance Criteria:**
- [x] Add `PartialExitLevel` dataclass with `r_multiple` and `exit_pct`
- [x] Add `partial_exit_levels` to `StrategyConfig` (list of levels)
- [x] Add `partial_exit_levels` to `Preset` dataclass
- [x] Update `Position` to track `remaining_size` and `partial_exits` list
- [x] Implement partial exit logic in `_process_partial_exits()`
- [x] Move stop to breakeven after first partial exit
- [x] Track partial exits in trade log with P&L per exit
- [x] Add `--partial-exits` CLI flag (uses default levels: 50% at 1R)
- [x] Add Optuna optimization (empty vs predefined patterns)
- [x] Update docs: guide-strategy.md (exit strategies), README.md (config)
- [x] Add `__post_init__` validation in dataclass (r_multiple > 0, exit_pct in (0,1])
- [x] Add 15 tests for partial exits in `test_bot.py`

**Files to modify:**
- `src/tradingbot/types.py` (Position dataclass, PartialExitLevel)
- `src/tradingbot/config.py` (StrategyConfig)
- `src/tradingbot/_components/presets.py` (Preset dataclass)
- `src/tradingbot/_components/bot.py` (exit logic)
- `src/tradingbot/_components/tuner.py` (Optuna)
- `src/tradingbot/backtest_cli.py`
- `src/tradingbot/cli.py` (live)
- `guide-strategy.md`
- `README.md`

---

## Phase 5: ATR-Based Trailing Stops ✅ COMPLETE

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
- [x] Calculate ATR for trailing distance
- [x] Track high-water mark per position
- [x] Trail stop progressively as price moves
- [x] Make trailing multiplier configurable
- [x] Add `--atr-trail` flag to CLI
- [x] Update docs: guide-strategy.md (trailing stops)
- [x] Add 8 tests for ATR trailing in `test_bot.py`

**Files modified:**
- `src/tradingbot/types.py` - Added `high_water_mark` field to Position
- `src/tradingbot/_components/bot.py` - Added `_calc_atr()` and updated `_trail_stop()`
- `src/tradingbot/_components/runner.py` - Added `atr_trail` support
- `src/tradingbot/_components/presets.py` - Added `atr_trail` to Preset dataclass
- `src/tradingbot/config.py` - Added `atr_trail` and `atr_trail_multiplier`
- `src/tradingbot/backtest_cli.py` - Added `--atr-trail` and `--atr-trail-mult` flags
- `guide-strategy.md` - Added ATR trailing documentation
- `README.md` - Added CLI flags documentation
- `glossary.md` - Added ATR Trail and High-Water Mark definitions
- `tests/test_bot.py` - Added 8 tests for ATR trailing

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

| Phase | Priority | Effort | Impact | Status |
|-------|----------|--------|--------|--------|
| 1. Execution costs | 🔴 Critical | Medium | High - all backtests affected | ✅ Complete |
| 2. Walk-forward | 🟡 High | Medium | High - prevents overfitting | ✅ Complete |
| 3. ATR sizing | 🟡 High | Low | Medium - better risk mgmt | ✅ Complete |
| 4. Partial exits | 🟡 Medium | Medium | Medium - better profit capture | ✅ Complete |
| 5. ATR trailing | 🟡 Medium | Low | Medium - better exit mgmt | ✅ Complete |
| 6. Magic numbers | 🟢 Low | Low | Low - code quality | ⏳ Pending |

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

| Phase | README.md | ARCHITECTURE.md | guide-strategy.md | glossary.md | Status |
|-------|-----------|-----------------|-------------------|-------------|--------|
| 1 | CLI flags | ExecutionModel | - | Slippage, Commission | ✅ |
| 2 | CLI flags | WalkForward | Optimization section | Walk-Forward | ✅ |
| 3 | CLI flags, config | - | Position sizing | ATR Sizing | ✅ |
| 4 | CLI flags, config | - | Exit strategies | Partial Exit | ✅ |
| 5 | CLI flags | - | Trailing stops | ATR Trail | ✅ |
| 6 | - | - | Strategy params | - | ⏳ |

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
