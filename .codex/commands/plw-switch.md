---
description: "Show or switch the active Helsincy Plan With Files task. /plw-switch"
argument-hint: "[plan-id]"
---

Use `$ARGUMENTS` as the optional plan id.

Run:

```powershell
python .codex\skills\planning-with-files\scripts\plan.py switch $ARGUMENTS
```

If no plan id was provided, report the current active plan. If a plan id was provided, confirm the newly active plan.
