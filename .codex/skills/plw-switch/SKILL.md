---
name: plw-switch
description: Show or switch the active Helsincy Plan With Files task. Invoke with /plw-switch.
user-invocable: true
allowed-tools: "Bash"
---

# /plw-switch

Use any text after `/plw-switch` as the optional plan id.

Run:

```powershell
python .codex\skills\planning-with-files\scripts\plan.py switch <optional plan-id>
```

If no plan id was provided, report the current active plan. If a plan id was provided, confirm the newly active plan.
