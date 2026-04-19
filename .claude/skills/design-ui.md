---
name: design-ui
description: Design a UI component for TUI or Web dashboard. Usage: /design-ui position tracker panel
user_invocable: true
---

Design a UI component using the ux-designer agent.

Parse the component description and target platform:
- **TUI**: Textual framework (terminal-based)
- **Web**: React + Tailwind (Bloomberg Terminal aesthetic)

The agent will provide:
1. ASCII mockup or wireframe
2. Component hierarchy
3. State requirements
4. User interaction flows
5. Design rationale

Example inputs:
- `/design-ui risk meter widget` → design risk visualization
- `/design-ui trade history panel for TUI` → design terminal panel
- `/design-ui alert configuration modal` → design web modal
