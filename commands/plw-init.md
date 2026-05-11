---
description: "Create a new Helsincy Plan With Files task. /plw-init"
argument-hint: "<task name> [--legacy] [--force]"
---

Use `$ARGUMENTS` as the task name and options.

If no task name was provided, ask the user for the task name. Otherwise run:

```powershell
python .codex\skills\planning-with-files\scripts\plan.py init $ARGUMENTS
```

After it completes, summarize the active plan path and the created planning files.
