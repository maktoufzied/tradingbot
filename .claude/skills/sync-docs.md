---
name: sync-docs
description: Check which documentation needs updating after code changes
user_invocable: true
---

Analyze recent code changes and identify documentation that needs updating.

1. Run `git diff --name-only` to get changed files
2. Use the Task tool to launch the `docs-sync` agent
3. The agent will report which docs need updates:
   - README.md (CLI, config, user-facing)
   - ARCHITECTURE.md (components, patterns)
   - guide-strategy.md (strategies, parameters)
   - glossary.md (new terms)

Call this skill after completing significant code changes.
