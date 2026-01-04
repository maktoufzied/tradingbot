# Web Dashboard Design System

This document defines the design principles and patterns for the trading bot web dashboard. All UI development should follow these guidelines to maintain consistency.

## Design Philosophy

**Bloomberg Terminal Aesthetic** - Professional, information-dense, dark theme with amber/orange accents. Prioritize readability and quick scanning of financial data.

## Color Palette

### Primary Colors
| Name | Hex | Usage |
|------|-----|-------|
| Primary | `#ffaa00` | Main accent, highlights, active states |
| Primary Dim | `#cc8800` | Hover states, secondary accent |
| Primary Bright | `#ffcc44` | Emphasis, glow effects |

### Semantic Colors
| Name | Hex | Usage |
|------|-----|-------|
| Positive | `#00ff88` | Profits, wins, bullish, long positions |
| Positive Dim | `#00cc6a` | Positive hover states |
| Negative | `#ff3366` | Losses, stops, bearish, short positions |
| Negative Dim | `#cc2952` | Negative hover states |
| Neutral/Accent | `#00d4ff` | Informational, duration, partial exits |
| Warning | `#ffaa00` | Warnings, EOD exits (same as primary) |

### Surface Colors
| Name | Hex | Usage |
|------|-----|-------|
| Background | `#0a0a0f` | Page background |
| Surface | `#12121a` | Cards, panels |
| Surface Dark | `#0f0f18` | Nested containers, inputs |
| Surface Light | `#1a1a24` | Hover states |

### Text Colors
| Name | Hex | Usage |
|------|-----|-------|
| Text | `#ffffff` | Primary text, prices |
| Text Secondary | `#b0b0b8` | Labels, secondary info |
| Text Dim | `#6a6a7a` | Hints, disabled, timestamps |
| Text Muted | `#4a4a5a` | Very subtle text |

### Border Colors
| Name | Hex | Usage |
|------|-----|-------|
| Border | `#2a2a3a` | Card borders, dividers |
| Border Dim | `#1a1a2a` | Subtle separators |
| Border Focus | `#00ff88` | Focus states |

## Typography

### Font Families
- **UI Text**: `Inter`, system-ui, sans-serif
- **Numbers/Data**: `JetBrains Mono`, `Fira Code`, monospace

### Font Usage Rules
1. **All prices and numbers** use monospace font (`font-mono` class)
2. **Labels** use uppercase with letter-spacing (`uppercase tracking-wider`)
3. **Tabular numbers** for alignment (`font-variant-numeric: tabular-nums`)

### Size Scale
| Size | Class | Usage |
|------|-------|-------|
| 4xl | `text-4xl` | Modal main price |
| 2xl | `text-2xl` | Card main price, modal headers |
| xl | `text-xl` | Performance pod values |
| lg | `text-lg` | Symbol names |
| base | `text-base` | P&L values in lists |
| sm | `text-sm` | Secondary prices, stats |
| xs | `text-xs` | Badges, labels, timestamps |
| [10px] | `text-[10px]` | Micro labels (above charts) |

## Component Patterns

### Badges
```html
<!-- Trend/Signal Badge -->
<span class="px-2 py-0.5 text-xs font-medium rounded whitespace-nowrap shrink-0 bg-positive/20 text-positive">
  ▲ BULLISH
</span>

<!-- Position Direction -->
<span class="px-2 py-0.5 text-xs font-bold rounded bg-positive/20 text-positive">
  ▲ LONG
</span>

<!-- Strategy Badge -->
<span class="px-2 py-1 text-xs rounded bg-neutral/20 text-neutral">
  momentum
</span>
```

### Cards
```html
<div class="bg-surface rounded-lg border border-border overflow-hidden hover:border-primary/50 transition-colors">
  <!-- Header -->
  <div class="flex items-center justify-between px-4 py-2 border-b border-border">
    ...
  </div>
  <!-- Content -->
  <div class="px-4 py-3">
    ...
  </div>
</div>
```

### Modals
```html
<!-- Backdrop -->
<div class="fixed inset-0 z-50 flex items-center justify-center p-4"
     style="background: rgba(0,0,0,0.85); backdrop-filter: blur(4px);">
  <!-- Modal Container -->
  <div class="bg-surface rounded-xl border border-border w-full max-w-5xl h-[85vh] overflow-hidden flex flex-col">
    <!-- Header -->
    <div class="flex items-center justify-between px-6 py-4 border-b border-border shrink-0">
      ...
    </div>
    <!-- Content -->
    <div class="flex-1 min-h-0 overflow-hidden p-6">
      ...
    </div>
  </div>
</div>
```

### Tabs
```html
<div class="flex gap-1 px-6 border-b border-border">
  <button class="px-4 py-3 text-sm font-medium text-primary relative">
    Active Tab
    <div class="absolute bottom-0 left-0 right-0 h-0.5 bg-primary" />
  </button>
  <button class="px-4 py-3 text-sm font-medium text-text-dim hover:text-text transition">
    Inactive Tab
  </button>
</div>
```

### Performance Pods
```html
<div class="bg-surface border border-border rounded-lg p-3 hover:border-primary/50 transition-all cursor-pointer group">
  <div class="flex items-center justify-between mb-2">
    <span class="text-xs uppercase tracking-wider text-text-dim font-mono">Daily</span>
  </div>
  <div class="font-mono text-xl font-bold text-positive mb-1">+$523</div>
  <div class="flex items-center justify-between text-xs">
    <div class="flex items-center gap-1">
      <div class="w-1.5 h-1.5 rounded-full bg-positive"></div>
      <span class="text-text-secondary">3W</span>
      <span class="text-text-dim">·</span>
      <div class="w-1.5 h-1.5 rounded-full bg-negative"></div>
      <span class="text-text-secondary">0L</span>
    </div>
    <span class="font-mono text-positive font-medium">100%</span>
  </div>
  <!-- Win rate bar -->
  <div class="mt-2 h-1 bg-border rounded-full overflow-hidden">
    <div class="h-full bg-gradient-to-r from-positive to-primary" style="width: 100%;"></div>
  </div>
</div>
```

### Trade Timeline Item
```html
<div class="group bg-surface border border-border rounded-lg hover:border-positive/50 transition-all">
  <div class="flex items-center gap-3 p-3">
    <!-- Time Badge -->
    <div class="flex flex-col items-center bg-surface-dark rounded px-2 py-1 min-w-[56px]">
      <span class="text-[10px] text-text-dim font-mono">Jan 2</span>
      <span class="text-xs text-text font-mono font-bold">10:34</span>
    </div>
    <!-- Direction + Details -->
    <div class="flex-1">
      <div class="flex items-center gap-2 mb-0.5">
        <span class="text-xs font-medium text-positive">▲ LONG</span>
        <span class="text-text-dim">·</span>
        <span class="text-xs text-text-secondary">75 sh</span>
      </div>
      <div class="flex items-center gap-2 text-xs font-mono">
        <span class="text-text-secondary">$449.20</span>
        <span class="text-text-dim">→</span>
        <span class="text-text">$451.85</span>
      </div>
    </div>
    <!-- P&L -->
    <div class="flex flex-col items-end">
      <span class="text-base font-mono font-bold text-positive">+$198.75</span>
      <span class="text-xs font-mono text-positive">+0.59%</span>
    </div>
    <!-- Result Badge -->
    <span class="px-2 py-1 bg-positive/20 text-positive rounded text-xs font-medium">TP</span>
  </div>
</div>
```

### Risk Ladder
```html
<div class="flex items-center gap-3 flex-1">
  <span class="text-xs font-mono text-negative font-medium">SL $184.00</span>
  <div class="flex-1 relative">
    <!-- Bar -->
    <div class="relative h-6 bg-surface rounded border-2 border-border overflow-hidden">
      <!-- Gradient background -->
      <div class="absolute inset-0 bg-gradient-to-r from-negative/30 via-neutral/20 to-positive/30"></div>
      <!-- Progress fill -->
      <div class="absolute inset-y-0 left-0 bg-gradient-to-r from-negative/50 via-primary/30 to-positive/50"
           style="width: 64%"></div>
      <!-- Entry marker (orange) -->
      <div class="absolute top-0 bottom-0 w-0.5 bg-primary z-10" style="left: 25%"></div>
      <!-- Partial exit markers (cyan) -->
      <div class="absolute top-0 bottom-0 w-0.5 bg-neutral z-10" style="left: 50%"></div>
      <!-- Current price dot -->
      <div class="absolute top-1/2 -translate-y-1/2 w-4 h-4 bg-text rounded-full border-2 border-surface-dark shadow-lg z-20"
           style="left: calc(64% - 8px)"></div>
    </div>
    <!-- Labels -->
    <div class="absolute -top-5 left-0 right-0 text-[10px] font-mono">
      <div class="absolute text-primary" style="left: 25%; transform: translateX(-50%)">Entry</div>
      <div class="absolute text-neutral" style="left: 50%; transform: translateX(-50%)">1R</div>
    </div>
  </div>
  <span class="text-xs font-mono text-positive font-medium">TP $188.00</span>
</div>
```

## Sparklines

```html
<svg viewBox="0 0 100 70" preserveAspectRatio="none" class="w-full h-[70px]">
  <defs>
    <linearGradient id="gradient" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#00ff88" stop-opacity="0.4" />
      <stop offset="100%" stop-color="#00ff88" stop-opacity="0.05" />
    </linearGradient>
  </defs>
  <!-- Area fill -->
  <path d="M0,50 Q25,45 50,40 T100,30 L100,70 L0,70 Z" fill="url(#gradient)" />
  <!-- Line -->
  <path d="M0,50 Q25,45 50,40 T100,30" fill="none" stroke="#00ff88" stroke-width="0.8" />
</svg>
```

## Spacing

Use Tailwind's default spacing scale:
- `gap-1` / `gap-1.5` - Between badges
- `gap-2` - Between related items
- `gap-3` - Between sections within a card
- `gap-4` - Between cards/major sections
- `p-3` - Card padding (compact)
- `p-4` - Card padding (normal)
- `p-6` - Modal padding

## Interactions

### Hover States
- Cards: `hover:border-primary/50`
- Buttons: `hover:bg-surface-light`
- Trade items: `hover:border-positive/50` (win) or `hover:border-negative/50` (loss)

### Transitions
- Always use `transition` or `transition-all` for smooth state changes
- Duration: default (150ms) for most, longer for modals

### Scrollbars
```css
.custom-scrollbar::-webkit-scrollbar { width: 4px; }
.custom-scrollbar::-webkit-scrollbar-track { background: #0a0a0f; }
.custom-scrollbar::-webkit-scrollbar-thumb { background: #ffaa00; border-radius: 2px; }
```

## Responsive Considerations

- Modal: `max-w-5xl` with `p-4` margin
- Cards: Use CSS Grid with responsive columns (`grid-cols-1 md:grid-cols-2 lg:grid-cols-3`)
- Performance pods: `grid-cols-4` (consider `grid-cols-2` on mobile)

## Do's and Don'ts

### Do
- Use monospace font for all numbers
- Use semantic colors (positive/negative) for P&L
- Add `whitespace-nowrap shrink-0` to badges
- Use gradients sparingly for depth
- Maintain high contrast for readability

### Don't
- Use blue as primary (we're Bloomberg-style, not generic)
- Mix different badge styles
- Use colored text without matching background tint
- Forget to handle loading/empty states
- Use light backgrounds
